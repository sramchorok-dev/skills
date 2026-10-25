#!/usr/bin/env python3
"""Measure one GitHub Actions attempt from saved REST run/jobs responses, offline."""
import argparse
from datetime import datetime
import json
from pathlib import Path


def instant(value):
    try:
        result=datetime.fromisoformat(value.replace('Z','+00:00'))
        return result if result.tzinfo else None
    except (ValueError,AttributeError): return None


def duration(start,end):
    a,b=instant(start),instant(end)
    return (b-a).total_seconds() if a and b and b>=a else None


def measure(run, payload):
    jobs=payload.get('jobs',[])
    if not run.get('id') or not run.get('run_attempt'): raise ValueError('REST run id/run_attempt required')
    if len({j['id'] for j in jobs})!=len(jobs): raise ValueError('duplicate jobs')
    if any(j.get('run_id')!=run['id'] or j.get('run_attempt')!=run['run_attempt'] for j in jobs):
        raise ValueError('mixed run or attempt; fetch /runs/ID/attempts/N/jobs')
    complete=len(jobs)>0 and payload.get('total_count')==len(jobs) and run.get('status')=='completed'
    rows=[]; ends=[]; starts=[]
    for job in jobs:
        seconds=duration(job.get('started_at'),job.get('completed_at')) if job.get('status')=='completed' else None
        if job.get('conclusion')=='skipped': seconds=0
        if seconds is None: complete=False
        if instant(job.get('started_at')): starts.append(instant(job['started_at']))
        if instant(job.get('completed_at')): ends.append(instant(job['completed_at']))
        steps=[{'name':s['name'],'conclusion':s.get('conclusion'),
                'seconds':duration(s.get('started_at'),s.get('completed_at')) if s.get('status')=='completed' else None}
               for s in job.get('steps',[])]
        rows.append({'name':job['name'],'conclusion':job.get('conclusion'),'seconds':seconds,'steps':steps})
    retry=run['run_attempt']>1
    created=instant(run.get('run_started_at') if retry else run.get('created_at'))
    return {'run_id':run['id'],'run_attempt':run['run_attempt'],'sha':run.get('head_sha'),
            'event':run.get('event'),'conclusion':run.get('conclusion'),'complete_timing':complete,
            'elapsed_basis':'attempt run_started_at' if retry else 'run created_at',
            'elapsed_to_last_job_seconds':(max(ends)-created).total_seconds() if complete and created and ends and max(ends)>=created else None,
            'initial_wait_seconds':(min(starts)-created).total_seconds() if not retry and complete and created and starts and min(starts)>=created else None,
            'job_seconds_sum':sum(row['seconds'] for row in rows) if complete else None,
            'jobs':rows,'test_counts':None,'reuse_verified':None,
            'note':'Job time sum is not billed cost. First wait is not total DAG queue time. Test counts/reuse need separate artifacts; never inferred from job names. Compare multiple equivalent samples before claiming speedup.'}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run-json',required=True);p.add_argument('--jobs-json',required=True)
    a=p.parse_args()
    try: print(json.dumps(measure(json.loads(Path(a.run_json).read_text()),json.loads(Path(a.jobs_json).read_text())),indent=2))
    except (ValueError,KeyError,OSError) as e: p.exit(2,str(e)+'\n')


if __name__=='__main__':main()
