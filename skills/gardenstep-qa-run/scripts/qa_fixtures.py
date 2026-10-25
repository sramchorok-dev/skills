#!/usr/bin/env python3
"""Private run-owned lease client for the existing loopback-only test fixture API.

Never starts an application, changes its configuration, or exposes the API on DEV.
Secrets are written only to a mode-0600 private lease file, never to stdout.
"""
import argparse
from contextlib import contextmanager
import fcntl
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import secrets
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler
from urllib.error import HTTPError, URLError


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def validate_origin(origin):
    p=urlsplit(origin)
    if p.scheme!='http' or p.hostname!='127.0.0.1' or not p.port or p.username or p.password or p.path or p.query or p.fragment:
        raise ValueError('fixture provider requires exact http://127.0.0.1:PORT origin; public DEV/prod unsupported')
    return origin


def private_write(path, value, exclusive=False):
    path=Path(path)
    if path.is_symlink(): raise ValueError('symlink lease files are not allowed')
    target=path if exclusive else path.with_name(path.name+'.'+secrets.token_hex(8)+'.tmp')
    flags=os.O_WRONLY|os.O_CREAT|(os.O_EXCL if exclusive else os.O_TRUNC)
    if hasattr(os,'O_NOFOLLOW'): flags |= os.O_NOFOLLOW
    fd=os.open(target,flags,0o600)
    with os.fdopen(fd,'w') as stream:
        os.fchmod(stream.fileno(),0o600)
        json.dump(value,stream,ensure_ascii=False,indent=2)
        stream.flush();os.fsync(stream.fileno())
    if not exclusive: os.replace(target,path)


def request(origin, part, method, token):
    validate_origin(origin)
    if not token: raise ValueError('E2E_FIXTURE_TOKEN required')
    opener=build_opener(ProxyHandler({}),NoRedirect())
    req=Request(origin+'/__e2e/leases/'+part,method=method,headers={'X-E2E-Token':token})
    try:
        with opener.open(req,timeout=15) as response:
            return json.loads(response.read(1024*1024))
    except HTTPError as exc:
        raise ValueError(f'fixture HTTP {exc.code}; inspect ledger, never print response secrets') from None
    except (URLError,TimeoutError,json.JSONDecodeError) as exc:
        raise ValueError('fixture response unavailable; mutation outcome may be unknown, reconcile this lease before retry') from None


def load(path):
    path=Path(path)
    if path.is_symlink() or path.stat().st_mode & 0o077:
        raise ValueError('lease file must be private mode 0600 and not a symlink')
    state=json.loads(path.read_text())
    validate_origin(state['origin'])
    if not re.fullmatch(r'QA-\d{8}-\d{2,3}-[0-9a-f]{16}',state['lease_key']):
        raise ValueError('invalid generated lease key')
    if not state['lease_key'].startswith(state['run_id']+'-'):
        raise ValueError('lease/run ownership mismatch')
    return state


def event(path,state,operation,status,**fields):
    state['events'].append({'at':datetime.now(timezone.utc).isoformat(),'operation':operation,'status':status,**fields})
    private_write(path,state)


@contextmanager
def lease_lock(path):
    fd=os.open(str(path)+'.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as stream:
        try: fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise ValueError('lease operation already running') from None
        yield


def prepare(path, origin, run_id, token, ttl=1800):
    validate_origin(origin)
    with lease_lock(path):
        return _prepare(path,origin,run_id,token,ttl)


def _prepare(path, origin, run_id, token, ttl=1800):
    validate_origin(origin)
    if not re.fullmatch(r'QA-\d{8}-\d{2,3}',run_id): raise ValueError('invalid run ID')
    if not 1<=ttl<=3600: raise ValueError('TTL must be 1..3600 seconds')
    if not token: raise ValueError('E2E_FIXTURE_TOKEN required before creating intent')
    state={'schema_version':1,'run_id':run_id,'origin':origin,'lease_key':run_id+'-'+secrets.token_hex(8),
           'status':'prepare-unknown','ttl_seconds':ttl,'events':[]}
    private_write(path,state,exclusive=True)
    event(path,state,'prepare','intent')
    result=request(origin,state['lease_key']+'?ttlSeconds='+str(ttl),'POST',token)
    if not isinstance(result,dict) or result.get('leaseKey')!=state['lease_key']:
        raise ValueError('prepare ownership response mismatch; preserve ledger for reconciliation')
    state['credentials']=result;state['status']='prepared'
    event(path,state,'prepare','verified')
    return public_status(state)


def operate(path,operation,token):
    with lease_lock(path):
        return _operate(path,operation,token)


def _operate(path,operation,token):
    state=load(path)
    if operation=='remaining':
        result=request(state['origin'],state['lease_key']+'/remaining','GET',token)
        if type(result) is not int or result<0: raise ValueError('invalid remaining count')
        event(path,state,'remaining','observed',remaining=result)
        return {**public_status(state),'remaining':result}
    if operation=='paid-order':
        if state['status']!='prepared': raise ValueError('paid-order requires prepared lease; unknown/previous mutations cannot be retried')
        state['status']='order-unknown';event(path,state,operation,'intent')
        result=request(state['origin'],state['lease_key']+'/paid-order','POST',token)
        if not isinstance(result,dict) or not result.get('orderNo'): raise ValueError('invalid order receipt; reconcile lease')
        state['order']=result;state['status']='order-prepared';event(path,state,operation,'verified')
        return public_status(state)
    if operation=='cleanup':
        if state['status']=='cleaned': return public_status(state)
        # A generated key is persisted before prepare, allowing reconciliation after timeout.
        state['status']='cleanup-unknown';event(path,state,operation,'intent')
        result=request(state['origin'],state['lease_key'],'DELETE',token)
        if not isinstance(result,dict) or type(result.get('remaining')) is not int or result['remaining']!=0:
            raise ValueError('cleanup not confirmed: remaining must be zero')
        remaining=request(state['origin'],state['lease_key']+'/remaining','GET',token)
        if type(remaining) is not int or remaining!=0: raise ValueError('cleanup readback failed')
        state['status']='cleaned';state.pop('credentials',None);state.pop('order',None)
        event(path,state,operation,'verified',remaining=0)
        return public_status(state)
    raise ValueError('unsupported operation')


def public_status(state):
    return {'run_id':state['run_id'],'provider':'loopback-lease','status':state['status'],
            'events':state['events'],'note':'Setup only, no browser/login/payment acceptance PASS. Credentials stay in private lease file.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=['prepare','paid-order','remaining','cleanup'])
    parser.add_argument('--lease-file',required=True)
    parser.add_argument('--origin');parser.add_argument('--run-id');parser.add_argument('--ttl',type=int,default=1800)
    args=parser.parse_args()
    try:
        token=os.environ.get('E2E_FIXTURE_TOKEN','')
        if args.operation=='prepare':
            if not args.origin or not args.run_id: raise ValueError('prepare requires origin and run-id')
            result=prepare(args.lease_file,args.origin,args.run_id,token,args.ttl)
        else: result=operate(args.lease_file,args.operation,token)
        print(json.dumps(result,ensure_ascii=False,indent=2))
    except (ValueError,OSError,KeyError) as exc:
        parser.exit(2,str(exc)+'\n')


if __name__=='__main__': main()
