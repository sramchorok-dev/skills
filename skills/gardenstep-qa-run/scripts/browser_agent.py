#!/usr/bin/env python3
"""Versioned browser-agent cards and evidence receipts. Never operates the browser or calls services."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))


class ContractError(ValueError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def require(condition, message):
    if not condition:
        raise ContractError(message)


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def unique(items, key, label):
    values = [item.get(key) for item in items]
    require(all(nonempty(v) for v in values) and len(values) == len(set(values)), f'{label}: missing/duplicate {key}')


def validate_catalog(cat):
    require(cat.get('schema_version') == 1, 'unsupported catalog schema_version')
    for field in ('sources', 'cards', 'routes', 'fixtures', 'exclusions'):
        require(isinstance(cat.get(field), list), f'{field} must be a list')
    unique(cat['sources'], 'id', 'sources')
    unique(cat['cards'], 'id', 'cards')
    source_ids = {s['id'] for s in cat['sources']}
    require(isinstance(cat.get('viewports'), dict) and cat['viewports'], 'viewports required')
    for source in cat['sources']:
        require(re.fullmatch(r'[0-9a-f]{64}', source.get('fingerprint', '')), 'source fingerprint required')
        if 'payload' in source: require(digest(source['payload']) == source['fingerprint'], 'source payload fingerprint mismatch')
    for c in cat['cards']:
        require(re.fullmatch(r'[A-Za-z0-9_-]+', c['id']), 'unsafe card id')
        require(isinstance(c.get('version'), int) and c['version'] > 0, 'card version must be positive integer')
        for key in ('title', 'priority', 'journey', 'role'):
            require(nonempty(c.get(key)), f'{c["id"]}: {key} required')
        for key in ('sources', 'profiles', 'viewports', 'environment', 'steps', 'checks', 'cleanup'):
            require(isinstance(c.get(key), list) and c[key], f'{c["id"]}: nonempty {key} required')
        for key in ('fixtures', 'spec_gaps', 'side_effects'):
            require(isinstance(c.get(key), list), f'{c["id"]}: {key} list required')
        require(isinstance(c.get('read_only'), bool), 'read_only must be explicit')
        require(set(c['sources']) <= source_ids, f'{c["id"]}: unknown source')
        require(set(c['fixtures']) <= set(cat['fixtures']), f'{c["id"]}: unknown fixture')
        require(set(c['viewports']) <= set(cat['viewports']), f'{c["id"]}: unknown viewport')
        unique(c['steps'], 'id', c['id'] + ' steps')
        unique(c['checks'], 'id', c['id'] + ' checks')
        for step in c['steps']:
            require(nonempty(step.get('action')), 'empty UI action')
        for check in c['checks']:
            require(nonempty(check.get('expected')) and check.get('oracle') in source_ids, 'expected value and independent oracle required')
            if 'grader' in check:
                from qa_reliability import grade
                try: grade(check['grader'], check['grader'].get('value'))
                except (ValueError, AttributeError) as exc: raise ContractError(str(exc)) from exc
    card_ids = {c['id'] for c in cat['cards']}
    for route in cat['routes']:
        require(nonempty(route.get('path')) and nonempty(route.get('classification')), 'route classification required')
        require(route.get('cards') and set(route['cards']) <= card_ids, 'route needs mapped cards, including blocked cards')
    mapped = {s for c in cat['cards'] for s in c['sources']}
    excluded = {e['source'] for e in cat['exclusions'] if e.get('decision') and e.get('decided_by')}
    return {'cards': len(cat['cards']), 'sources': len(source_ids), 'unmapped_sources': sorted(source_ids - mapped - excluded),
            'spec_gap_cards': sum(bool(c['spec_gaps']) for c in cat['cards']), 'routes':len(cat['routes'])}


def validate_environment(env):
    for field in ('environment', 'runner', 'tool', 'checked_at', 'verification'):
        require(nonempty(env.get(field)), f'environment.{field} required')
    require(env['environment'] in ('dev', 'prod-readonly'), 'only dev/prod-readonly environments supported')
    require(isinstance(env.get('revisions'), dict) and env['revisions'], 'observed revisions required')
    for service, revision in env['revisions'].items():
        require(re.fullmatch(r'[0-9a-f]{7,40}', str(revision)), f'{service}: unavailable revision must block init, never invent it')
    require(isinstance(env.get('urls'), dict) and env['urls'], 'verified URLs required')
    for url in env['urls'].values():
        parsed = urlparse(url)
        require(parsed.scheme == 'https' and parsed.hostname and not parsed.username and not parsed.query, 'URLs must be HTTPS origins without credentials/query')
        if env['environment'] == 'dev':
            require(any(x in parsed.hostname.split('.') for x in ('dev', 'test', 'localhost')) or parsed.hostname.startswith('dev-') or '-dev.' in parsed.hostname, 'DEV hostname not recognized; resolve environment before running')
    require(isinstance(env.get('fixtures'), dict), 'fixture readiness map required')


def select_cells(cat, profile, ids=None, journey=None, viewports=None):
    known = {p for c in cat['cards'] for p in c['profiles']} | {'full'}
    require(profile in known, f'unknown profile {profile}')
    requested = set(ids or [])
    require(requested <= {c['id'] for c in cat['cards']}, 'unknown card ID')
    selected = []
    for c in cat['cards']:
        if profile != 'full' and profile not in c['profiles']: continue
        if requested and c['id'] not in requested: continue
        if journey and c['journey'] != journey: continue
        for viewport in c['viewports']:
            if viewports and viewport not in viewports: continue
            selected.append({'cell_id': c['id'] + '@' + viewport, 'card_id': c['id'], 'viewport': viewport,
                             'card_fingerprint': digest(c)})
    require(selected, 'selection is empty; no run created')
    return selected


def fixture_readiness(cat, env, profile, proof_root, ids=None, journey=None, viewports=None):
    """Inspect already prepared fixture receipts only. No seed/login/payment/network side effects."""
    require(not validate_catalog(cat)['unmapped_sources'], 'unmapped source definitions')
    validate_environment(env)
    cells=select_cells(cat,profile,ids,journey,viewports);cards={c['id']:c for c in cat['cards']}
    needed=sorted({f for cell in cells for f in cards[cell['card_id']]['fixtures']})
    fixtures={}
    for alias in needed:
        receipt=env.get('fixture_receipts',{}).get(alias,{})
        status=env['fixtures'].get(alias,'missing');problems=[];hashes={}
        if status!='available':problems.append('fixture status '+status)
        for field in ('owner','source_contract','checked_at'):
            if not nonempty(receipt.get(field)):problems.append('missing receipt '+field)
        if not receipt.get('evidence'):problems.append('missing fixture proof')
        for path in receipt.get('evidence',[]):
            try:hashes[path]=safe_evidence(proof_root,path)
            except ContractError as error:problems.append(str(error))
        fixtures[alias]={'available':not problems,'problems':problems,'evidence_hashes':hashes}
    blocked=[];runnable=[]
    for cell in cells:
        card=cards[cell['card_id']]
        missing=[f for f in card['fixtures'] if not fixtures[f]['available']]
        missing_revisions=sorted(set(card.get('services',[]))-set(env['revisions']))
        allowed=env['environment'] in card['environment'] and (env['environment']!='prod-readonly' or profile=='prod-readonly' and card['read_only'] and not card['side_effects'])
        if missing or card['spec_gaps'] or missing_revisions or not allowed:
            blocked.append({'cell_id':cell['cell_id'],'missing_fixtures':missing,'spec_gaps':card['spec_gaps'],'missing_revisions':missing_revisions,'environment_allowed':allowed})
        else:runnable.append(cell['cell_id'])
    return {'fixtures':fixtures,'runnable_cells':runnable,'blocked_cells':blocked,'ready':not blocked}


def init_run(cat, env, out, run_id, profile, ids=None, journey=None, viewports=None, proof_root=None):
    validation=validate_catalog(cat)
    require(not validation['unmapped_sources'], 'unmapped source definitions: '+', '.join(validation['unmapped_sources']))
    validate_environment(env)
    require(re.fullmatch(r'QA-\d{8}-\d{2,3}', run_id), 'Run ID must be QA-YYYYMMDD-NN')
    selected = select_cells(cat, profile, ids, journey, viewports)
    cards = {c['id']:c for c in cat['cards']}
    for cell in selected:
        card = cards[cell['card_id']]
        require(set(card.get('services', [])) <= set(env['revisions']), f'{card["id"]}: required service revisions missing')
        require(env['environment'] in card['environment'], f'{card["id"]}: not allowed in environment')
        if env['environment'] == 'prod-readonly':
            require(profile == 'prod-readonly' and card['read_only'] and not card['side_effects'], 'production only allows explicit read-only cells')
    out = Path(out)
    proof_root=Path(proof_root or out.parent)
    readiness=fixture_readiness(cat,env,profile,proof_root,ids,journey,viewports)
    for alias,proof in readiness['fixtures'].items():
        require(env['fixtures'].get(alias)!='available' or proof['available'], f'{alias}: available requires actual fixture receipt proof; use unverified to record BLOCKED')
    require(not out.exists(), 'run exists; use resume or a new run ID')
    out.mkdir(parents=True)
    for folder in ('results', 'screenshots', 'evidence'): (out/folder).mkdir()
    for alias,proof in readiness['fixtures'].items():
        frozen_hashes={}
        for index,(relative,sha) in enumerate(proof['evidence_hashes'].items()):
            filename=f'evidence/fixture-{digest(alias)[:12]}-{index}.proof'
            (out/filename).write_bytes((proof_root/relative).read_bytes());frozen_hashes[filename]=sha
        proof['evidence_hashes']=frozen_hashes
    write_json(out/'fixture-readiness.json',readiness)
    write_json(out/'catalog.json', cat)
    write_json(out/'manifest.json', {'schema_version':1, 'run_id':run_id, 'profile':profile, 'catalog_fingerprint':digest(cat),
        'environment':env, 'cells':selected, 'fixture_fingerprint':digest(readiness), 'created_at':datetime.now(timezone.utc).isoformat(),
        'critical_cells_total':len(select_cells(cat,'critical')) if any('critical' in c['profiles'] for c in cat['cards']) else 0,
        'note':'No results implied by initialization. TaskSpace alone is not session isolation.'})
    write_json(out/'created-resources.json', [])
    return summary(out)


def load_run(run):
    run = Path(run)
    manifest, cat = read_json(run/'manifest.json'), read_json(run/'catalog.json')
    require(manifest.get('schema_version') == 1, 'unsupported manifest')
    require(digest(cat) == manifest['catalog_fingerprint'], 'frozen catalog changed; use new run')
    validate_catalog(cat)
    require(digest(read_json(run/'fixture-readiness.json')) == manifest['fixture_fingerprint'], 'frozen fixture readiness changed; use new run')
    cards = {c['id']:c for c in cat['cards']}
    for cell in manifest['cells']:
        require(cell['card_id'] in cards and cell['card_fingerprint'] == digest(cards[cell['card_id']]), 'cell snapshot mismatch')
    return manifest, cat, cards


def resume(run, cat, env):
    manifest, frozen, _ = load_run(run)
    validate_environment(env)
    require(digest(cat) == digest(frozen), 'source/card catalog changed: create a new run')
    old = manifest['environment']
    for key in ('environment', 'urls', 'revisions'):
        require(env[key] == old[key], f'{key} changed: create a new run; never combine prior PASS')
    write_json(Path(run)/'resume-check.json', {'checked_at':env['checked_at'], 'verification':env['verification'], 'environment':env})
    return summary(run)


def result_template(run, cell_id):
    manifest, _, cards = load_run(run)
    cell = next((c for c in manifest['cells'] if c['cell_id'] == cell_id), None)
    require(cell is not None, 'cell not selected')
    card = cards[cell['card_id']]
    return {'schema_version':1, 'run_id':manifest['run_id'], 'cell_id':cell_id, 'card_fingerprint':cell['card_fingerprint'],
        'catalog_fingerprint':manifest['catalog_fingerprint'], 'revisions':manifest['environment']['revisions'],
        'preconditions_met':False, 'blocked_reason':'', 'mode':'live-browser', 'session':{'context_id':'','role_alias':'','isolation_verified':False,'proof':''},
        'started_at':'', 'finished_at':'', 'steps_completed':[], 'ui_observation':'',
        'checks':[{'id':c['id'], 'status':'UNKNOWN', 'observed':'', 'evidence':[]} for c in card['checks']],
        'resources':[], 'no_resource_reason':'', 'note':''}


def safe_evidence(run, relative):
    require(nonempty(relative), 'evidence path required')
    base=Path(run).resolve(); path=(base/relative).resolve()
    require(path.is_relative_to(base) and Path(relative).parts[0] in ('screenshots','evidence'), 'evidence must be under run screenshots/ or evidence/')
    require(path.is_file() and path.stat().st_size > 0, f'missing/empty evidence: {relative}')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_result(run, result):
    manifest, _, cards = load_run(run)
    require(result.get('schema_version') == 1, 'unsupported result schema')
    require(result.get('run_id') == manifest['run_id'], 'wrong run_id')
    cell = next((c for c in manifest['cells'] if c['cell_id'] == result.get('cell_id')), None)
    require(cell is not None, 'unselected cell')
    card = cards[cell['card_id']]
    require(result.get('card_fingerprint') == cell['card_fingerprint'] and result.get('catalog_fingerprint') == manifest['catalog_fingerprint'], 'snapshot fingerprint mismatch')
    require(result.get('revisions') == manifest['environment']['revisions'], 'revision mismatch')
    require(isinstance(result.get('preconditions_met'), bool), 'preconditions_met must be boolean')
    if result.get('not_run_reason'):
        require(not result.get('checks') or all(c.get('status')=='UNKNOWN' for c in result['checks']), 'NOT_RUN cannot hide observations')
        return 'NOT_RUN', {}
    if result.get('na_reason'):
        require(not any(c.get('status') in ('MATCH','MISMATCH') for c in result.get('checks',[])), 'N/A cannot hide observed checks')
        require(card.get('na_decision') and result.get('na_decision') == card['na_decision'], 'N/A requires catalog-approved decision')
        return 'N/A', {}
    if not result['preconditions_met']:
        require(nonempty(result.get('blocked_reason')), 'blocked_reason required')
        require(not any(c.get('status') in ('MATCH','MISMATCH') for c in result.get('checks',[])), 'precondition BLOCKED cannot hide observed results')
        return 'BLOCKED', {}
    session = result.get('session', {})
    require(session.get('isolation_verified') is True and all(nonempty(session.get(k)) for k in ('context_id','role_alias','proof')), 'verified isolated session required; task space is not isolation')
    readiness=read_json(Path(run)/'fixture-readiness.json')
    for fixture in card['fixtures']:
        proof=readiness['fixtures'].get(fixture,{})
        require(proof.get('available') is True, 'required fixture lacks prepared receipt')
        require(proof.get('evidence_hashes') and all(safe_evidence(run,p)==h for p,h in proof['evidence_hashes'].items()), 'fixture evidence changed')
    require(result.get('mode') in ('live-browser','fault-injection'), 'API substitution cannot prove a browser cell')
    require(result.get('mode') != 'fault-injection' or card.get('fault_injection'), 'fault injection must be explicit in card')
    completed=set(result.get('steps_completed',[])); required_steps={s['id'] for s in card['steps']}
    require(completed <= required_steps, 'unknown completed UI step')
    require(nonempty(result.get('ui_observation')), 'UI observation required')
    for field in ('started_at','finished_at'):
        try: datetime.fromisoformat(result[field].replace('Z','+00:00'))
        except (KeyError,ValueError,TypeError): raise ContractError(f'{field}: ISO timestamp required')
    start=datetime.fromisoformat(result['started_at'].replace('Z','+00:00')); end=datetime.fromisoformat(result['finished_at'].replace('Z','+00:00'))
    require(start.tzinfo is not None and end.tzinfo is not None and end >= start, 'timestamps require timezone and ordered start/end')
    checks = result.get('checks',[])
    unique(checks, 'id', 'result checks')
    require({c['id'] for c in checks} == {c['id'] for c in card['checks']}, 'missing/extra criterion IDs')
    hashes = {}
    definitions={c['id']:c for c in card['checks']}
    for check in checks:
        if card['spec_gaps'] and not definitions[check['id']].get('resolved', False):
            require(check.get('status') == 'UNKNOWN', 'unresolved oracle must remain UNKNOWN')
        require(check.get('status') in ('MATCH','MISMATCH','UNKNOWN'), 'unknown check status')
        rule=definitions[check['id']].get('grader')
        if rule and check['status'] != 'UNKNOWN':
            from qa_reliability import grade
            require('observed_value' in check, 'deterministic grader requires captured observed_value')
            try: computed=grade(rule,check['observed_value'])
            except ValueError as exc: raise ContractError(str(exc)) from exc
            require(check['status']==computed, 'declared status disagrees with source-backed grader')
        require(nonempty(check.get('observed')) and check['observed'].strip().lower() not in ('ok','pass','정상','일치'), 'concrete observed value required')
        require(isinstance(check.get('evidence'),list), 'evidence must be a list')
        if check['status'] != 'UNKNOWN': require(check['evidence'], 'MATCH/MISMATCH requires evidence')
        for path in check['evidence']: hashes[path] = safe_evidence(run,path)
    verdict = 'FAIL' if any(c['status']=='MISMATCH' for c in checks) else 'BLOCKED' if any(c['status']=='UNKNOWN' for c in checks) or completed != required_steps or card['spec_gaps'] else 'PASS'
    if card['side_effects']:
        require(isinstance(result.get('resources'),list), 'resources must be a list')
        require(result.get('resources') or nonempty(result.get('no_resource_reason')), 'declare created resources or explain why none were created')
        ledger=read_json(Path(run)/'created-resources.json')
        require(set(result['resources']) <= {r['id'] for r in ledger}, 'created resources must be in cleanup ledger before recording')
    if verdict == 'PASS':
        require(completed == required_steps, 'all UI steps required for PASS')
    return verdict, hashes


def record(run, result):
    verdict, hashes = validate_result(run,result)
    # Existing qa_record privacy checks are shared; internal snapshots themselves stay in the private repo.
    from qa_record import check_sensitive
    check_sensitive(json.dumps(result, ensure_ascii=False), 'browser result')
    path=Path(run)/'results'
    attempt=len(list(path.glob(result['cell_id']+'--*.json')))+1
    payload={**result,'verdict':verdict,'evidence_hashes':hashes,'attempt':attempt,'recorded_at':datetime.now(timezone.utc).isoformat()}
    target=path/f'{result["cell_id"]}--{attempt:03d}.json'
    with target.open('x',encoding='utf-8') as f: json.dump(payload,f,ensure_ascii=False,indent=2)
    return payload


def summary(run):
    manifest, cat, cards = load_run(run)
    results = {}; historical_failures=set()
    for path in sorted((Path(run)/'results').glob('*.json')):
        result=read_json(path)
        verdict, hashes = validate_result(run,result)
        require(verdict == result['verdict'] and hashes == result['evidence_hashes'], 'result/evidence changed since recording')
        results[result['cell_id']]=result
        if verdict=='FAIL': historical_failures.add(result['cell_id'])
    counts=dict.fromkeys(('PASS','FAIL','BLOCKED','NOT_RUN','N/A'),0)
    groups={}; rows=[]
    for cell in manifest['cells']:
        card=cards[cell['card_id']]; result=results.get(cell['cell_id']); verdict=result['verdict'] if result else 'NOT_RUN'
        counts[verdict]+=1
        for axis,value in [('journey',card['journey']),('viewport',cell['viewport']),('priority',card['priority'])]+[('participant_role',role) for role in card.get('roles',[card['role']])]:
            group=groups.setdefault(axis,{}).setdefault(value,dict.fromkeys(counts,0));group[verdict]+=1
        rows.append({'cell_id':cell['cell_id'],'verdict':verdict,'reason':(result or {}).get('blocked_reason','') or '; '.join(card['spec_gaps'])})
    applicable=len(rows)-counts['N/A']
    coverage=validate_catalog(cat)
    resources=read_json(Path(run)/'created-resources.json')
    for resource in resources:
        require(validate_resource(run,resource)==resource.get('evidence_hashes',{}), 'cleanup evidence changed since recording')
    pending=[r for r in resources if r['status'] not in ('cleaned','retained-approved')]
    return {'run_id':manifest['run_id'],'profile':manifest['profile'],'selected':len(rows),'applicable':applicable,'counts':counts,
        'definition_mapping_coverage':(coverage['sources']-len(coverage['unmapped_sources']))/max(coverage['sources'],1),
        'source_definition_coverage':sum(any(s['id'] in c['sources'] for c in cat['cards']) and all(not c['spec_gaps'] for c in cat['cards'] if s['id'] in c['sources']) for s in cat['sources'] if s.get('kind')=='sheet-row')/max(sum(s.get('kind')=='sheet-row' for s in cat['sources']),1),
        'executable_definition_cards':coverage['cards']-coverage['spec_gap_cards'],'spec_gap_cards':coverage['spec_gap_cards'],
        'execution_coverage':(counts['PASS']+counts['FAIL'])/max(applicable,1),'pass_coverage':counts['PASS']/max(applicable,1),
        'historical_failures':sorted(historical_failures),'groups':groups,'cells':rows,'pending_cleanup':pending,
        'selected_scope_complete':bool(applicable) and counts['PASS']==applicable and not pending,
        'whole_critical_complete':manifest['profile']=='critical' and len(rows)==manifest['critical_cells_total'] and bool(applicable) and counts['PASS']==applicable and not pending}


def validate_resource(run, entry):
    manifest,_,_=load_run(run)
    for field in ('id','kind','owner','created_by_cell','cleanup','status'):
        require(nonempty(entry.get(field)), f'resource.{field} required')
    require(entry['owner']==manifest['run_id'],'only resources owned by this run may be tracked for cleanup')
    require(entry['created_by_cell'] in {c['cell_id'] for c in manifest['cells']},'resource must name selected cell')
    require(entry['status'] in ('created','cleanup-blocked','cleaned','retained-approved'),'invalid cleanup status')
    hashes={}
    if entry['status'] in ('cleaned','retained-approved'):
        require(nonempty(entry.get('evidence')),'cleanup evidence path required')
        hashes[entry['evidence']]=safe_evidence(run,entry['evidence'])
    if entry['status']=='retained-approved':
        approval=entry.get('retention_decision',{})
        require(isinstance(approval,dict) and all(nonempty(approval.get(k)) for k in ('decided_by','decision','scope','decided_at')), 'retention requires decider, decision, exact scope, date and evidence')
        require(entry['id'] in approval['scope'], 'retention scope must name this resource alias')
    return hashes


def add_resource(run, entry):
    hashes=validate_resource(run,entry)
    entry={**entry,'evidence_hashes':hashes}
    from qa_record import check_sensitive
    check_sensitive(json.dumps(entry,ensure_ascii=False),'resource ledger')
    path=Path(run)/'created-resources.json'; entries=read_json(path)
    previous=[x for x in entries if x['id']==entry['id']]
    if previous: entry['history']=previous[0].get('history',[])+[{k:v for k,v in previous[0].items() if k!='history'}]
    entries=[x for x in entries if x['id']!=entry['id']]+[entry]
    write_json(path,entries);return entry


def export_report(run):
    result=summary(run);root=Path(run)
    write_json(root/'coverage.json',result)
    with (root/'execution.tsv').open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=['cell_id','verdict','reason'],delimiter='\t');writer.writeheader();writer.writerows(result['cells'])
    text=f'# {result["run_id"]}\n\nProfile: {result["profile"]}\n\n'+', '.join(f'{k} {v}' for k,v in result['counts'].items())
    text+=f'\n\nExecution coverage {result["execution_coverage"]:.1%}; pass coverage {result["pass_coverage"]:.1%}. BLOCKED/NOT_RUN remain in denominator.\n'
    text+='\nHistorical failed cells: '+(', '.join(result['historical_failures']) or 'none')+'\n'
    text+='\nPending cleanup: '+str(len(result['pending_cleanup']))+'\n\n'
    text+='\n'.join(f'- {r["cell_id"]}: {r["verdict"]} {r["reason"]}' for r in result['cells'] if r['verdict']!='PASS')
    (root/'report.md').write_text(text+'\n',encoding='utf-8')
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('diff');p.add_argument('--before',required=True);p.add_argument('--after',required=True)
    for command in ('validate','list','init','resume','fixture-check'):
        p=sub.add_parser(command);p.add_argument('--catalog',required=True)
        if command in ('list','init','fixture-check'): p.add_argument('--profile',default='critical');p.add_argument('--ids');p.add_argument('--journey');p.add_argument('--viewports')
        if command in ('init','resume'): p.add_argument('--environment',required=True);p.add_argument('--run',required=True)
        if command=='fixture-check':p.add_argument('--environment',required=True)
        if command=='init': p.add_argument('--run-id',required=True)
    for command in ('template','record','summary','resource','retest'):
        p=sub.add_parser(command);p.add_argument('--run',required=True)
        if command=='template':p.add_argument('--cell',required=True);p.add_argument('--out',required=True)
        if command in ('record','resource'):p.add_argument('input')
    args=parser.parse_args(argv)
    try:
        cat=read_json(args.catalog) if hasattr(args,'catalog') else None
        env=read_json(args.environment) if hasattr(args,'environment') else None
        filters={k:(getattr(args,k).split(',') if k!='journey' and getattr(args,k) else getattr(args,k)) for k in ('ids','journey','viewports')} if args.command in ('list','init','fixture-check') else {}
        if args.command=='diff':
            old=read_json(args.before);new=read_json(args.after);validate_catalog(old);validate_catalog(new)
            old_sources={s['id']:s['fingerprint'] for s in old['sources']}; new_sources={s['id']:s['fingerprint'] for s in new['sources']}
            changed=sorted(k for k in old_sources.keys()|new_sources.keys() if old_sources.get(k)!=new_sources.get(k))
            old_cards={c['id']:digest(c) for c in old['cards']}; new_cards={c['id']:digest(c) for c in new['cards']}
            result={'changed_sources':changed,'changed_cards':sorted(k for k in old_cards.keys()|new_cards.keys() if old_cards.get(k)!=new_cards.get(k)), 'affected_cards':sorted(c['id'] for c in new['cards'] if set(c['sources'])&set(changed)), 'new_run_required':digest(old)!=digest(new)}
        elif args.command=='validate': result=validate_catalog(cat);require(not result['unmapped_sources'],'unmapped sources: '+','.join(result['unmapped_sources']))
        elif args.command=='list':validate_catalog(cat);result=select_cells(cat,args.profile,**filters)
        elif args.command=='fixture-check':result=fixture_readiness(cat,env,args.profile,Path(args.environment).parent,**filters)
        elif args.command=='init':result=init_run(cat,env,Path(args.run),args.run_id,args.profile,proof_root=Path(args.environment).parent,**filters)
        elif args.command=='resume':result=resume(Path(args.run),cat,env)
        elif args.command=='template':result=result_template(args.run,args.cell);write_json(args.out,result)
        elif args.command=='record':result=record(args.run,read_json(args.input));result={k:result[k] for k in ('cell_id','verdict','attempt')}
        elif args.command=='summary':result=export_report(args.run)
        elif args.command=='resource':result=add_resource(args.run,read_json(args.input))
        else:
            report=summary(args.run); _,_,cards=load_run(args.run)
            failed={c['cell_id'].split('@')[0] for c in report['cells'] if c['verdict'] in ('FAIL','BLOCKED')}
            journeys={cards[i]['journey'] for i in failed}
            result={'new_run_required':True,'ids':sorted(c['id'] for c in cards.values() if c['journey'] in journeys),'reason':'Failed/blocked cells plus related journey cards. No PASS copied.'}
        print(json.dumps(result,ensure_ascii=False,indent=2));return 2 if args.command=='fixture-check' and not result['ready'] else 0
    except (ContractError,OSError,ValueError,KeyError) as error:
        print(f'No receipt accepted: {error}',file=sys.stderr);return 1

if __name__=='__main__':raise SystemExit(main())
