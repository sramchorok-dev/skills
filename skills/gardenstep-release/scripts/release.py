#!/usr/bin/env python3
"""Read-only release planning and exact-deployment post-QA observation. Never deploys."""
import argparse
import json
import re
import subprocess
import tempfile
from pathlib import Path

REPOS = {'gardenstep': ('fe', ['test-matrix', 'test']), 'gardenstep-server': ('server', ['test']),
         'gardenstep_admin': ('admin', ['test']), 'gardenstep-ai': ('ai', ['test'])}
SHA = re.compile(r'^[0-9a-f]{40}$')


def run(argv):
    return subprocess.run(argv, capture_output=True, text=True, check=True, timeout=60).stdout.strip()


def git(repo, *args):
    return run(['git', '-C', str(repo), *args])


def repo_name(repo):
    remote = git(repo, 'remote', 'get-url', 'origin')
    match = re.fullmatch(r'(?:https://github\.com/|git@github\.com:)sramchorok-dev/([\w-]+?)(?:\.git)?/?', remote)
    if not match or match[1] not in REPOS: raise ValueError('지원하는 팀 저장소 origin이 필요합니다')
    return match[1]


def evidence_for(path, repo, tree, workflow, jobs):
    if path is None: return None
    for line in reversed(Path(path).read_text().splitlines()):
        try: item = json.loads(line)
        except ValueError: continue
        if (item.get('repo') == repo and item.get('tree') == tree and item.get('workflow_blob') == workflow
                and item.get('result') == 'success' and set(jobs).issubset(item.get('jobs', []))):
            return {k: item.get(k) for k in ('sha', 'finished_at', 'run_dir')}
    return None


def plan(repo, target, running_sha=None, executor=None, evidence=None):
    repo = Path(repo).resolve()
    name = repo_name(repo)
    alias, jobs = REPOS[name]
    branch = 'main' if target == 'prod' else 'dev'
    sha = git(repo, 'rev-parse', f'origin/{branch}')
    if not SHA.fullmatch(sha): raise ValueError('유효한 remote SHA가 필요합니다')
    if running_sha is not None and not SHA.fullmatch(running_sha): raise ValueError('running-sha는 실제 확인한 full SHA여야 합니다')
    workflow_path = '.github/workflows/production.yml' if target == 'prod' and alias == 'ai' else '.github/workflows/cicd.yml'
    tree = git(repo, 'rev-parse', f'{sha}^{{tree}}')
    workflow = git(repo, 'rev-parse', f'{sha}:{workflow_path}')
    reusable = evidence_for(evidence, name, tree, workflow, jobs)
    command = None
    if executor is not None:
        executor = Path(executor).expanduser()
        if not executor.is_absolute() or not executor.is_file(): raise ValueError('설치된 gsdeploy 실행 파일의 절대 경로가 필요합니다')
        if target == 'prod' and alias == 'ai': raise ValueError('AI 운영은 production.yml 사용; gsdeploy 운영 경로 미지원')
        command = [str(executor), 'deploy', alias, '--sha', sha, '--dry-run']
        if target == 'prod': command += ['--target', 'prod', '--confirm', 'DEPLOY-PROD-'+sha[:7], '--reuse-tested']
        else: command += ['--skip-tests']
    return {'repository': 'sramchorok-dev/'+name, 'environment': target, 'branch': branch, 'sha': sha,
            'tree': tree, 'workflow': workflow_path, 'workflow_blob': workflow,
            'deployment_need': 'UNCHANGED' if running_sha == sha else 'CHANGED' if running_sha else 'UNKNOWN_CHECK_LIVE_REVISION',
            'test_evidence': reusable, 'reuse_status': 'MATCH_CANDIDATE_RECHECK_BY_EXECUTOR' if reusable else 'NO_MATCH_RUN_REQUIRED_TESTS',
            'local_dry_run_argv': command, 'actual_deploy_executed': False,
            'notes': ['로컬 origin ref를 사용합니다. 실행 직전 fetch와 실제 실행 버전을 확인하세요.',
                      'No test bypass for production. Local executor revalidates evidence and existing gates.',
                      'Do not start local deployment while the same native deployment is active.']}


def qa_verdict(runs, deployment_id, deployment_attempt, sha, identity=None):
    title = f'postqa-{deployment_id}-{deployment_attempt}'
    matches = [r for r in runs if r.get('displayTitle') == title]
    if not matches: return {'status': 'MISSING', 'reason': '접수 실행 미관측; 성공이 아님'}
    if len(matches) != 1: return {'status': 'AMBIGUOUS', 'reason': '동일 배포의 QA 실행 중복; 수동 확인'}
    row = matches[0]
    base = {'run_id': row['databaseId'], 'url': row['url']}
    if row['status'] != 'completed': return dict(base, status='PENDING' if row['status'] in ('queued','waiting','requested','pending') else 'RUNNING')
    if row.get('conclusion') != 'success': return dict(base, status='FAIL', conclusion=row.get('conclusion'))
    expected = {'sha': sha, 'deployment_run_id': str(deployment_id), 'deployment_attempt': str(deployment_attempt),
                'qa_run_id': str(row['databaseId']), 'qa_run_attempt': str(row.get('attempt'))}
    if identity != expected: return dict(base, status='UNVERIFIED', reason='성공 실행의 exact deployment identity 미확인')
    return dict(base, status='PASS', scope='해당 revision의 격리 CI 회귀; 실제 DEV 브라우저/Figma 검수는 별도')


def postqa(repo, deployment_id, attempt, sha):
    if repo not in ['sramchorok-dev/'+r for r in REPOS if r != 'gardenstep_admin']: raise ValueError('FE·BE·AI DEV만 지원')
    if not SHA.fullmatch(sha): raise ValueError('full SHA가 필요합니다')
    if not re.fullmatch(r'(?:[0-9]+|local-[0-9a-f-]{36})',deployment_id) or not re.fullmatch(r'[1-9][0-9]*',attempt): raise ValueError('배포 ID/attempt 형식 오류')
    runs = json.loads(run(['gh','run','list','--repo',repo,'--workflow','dev-post-deploy-regression.yml','--limit','1000','--json','databaseId,displayTitle,status,conclusion,url']))
    initial = qa_verdict(runs,deployment_id,attempt,sha)
    if initial['status'] != 'UNVERIFIED': return initial
    row = next(r for r in runs if r['databaseId'] == initial['run_id'])
    row['attempt'] = json.loads(run(['gh','run','view',str(row['databaseId']),'--repo',repo,'--json','attempt']))['attempt']
    try:
        with tempfile.TemporaryDirectory(prefix='gardenstep-qa-identity-') as d:
            run(['gh','run','download',str(row['databaseId']),'--repo',repo,'--name','qa-identity-'+str(row['attempt']),'--dir',d])
            identity=json.loads((Path(d)/'identity.json').read_text())
    except (OSError, ValueError, subprocess.SubprocessError):
        return dict(initial, reason='identity artifact 접근 실패/만료; PASS로 추정하지 않음')
    return qa_verdict(runs,deployment_id,attempt,sha,identity)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='action',required=True)
    p=sub.add_parser('plan');p.add_argument('--repo',required=True);p.add_argument('--target',choices=['dev','prod'],default='dev')
    p.add_argument('--running-sha');p.add_argument('--executor');p.add_argument('--evidence')
    p=sub.add_parser('postqa');p.add_argument('--repo',required=True);p.add_argument('--deployment-id',required=True);p.add_argument('--attempt',required=True);p.add_argument('--sha',required=True)
    args=parser.parse_args()
    try:
        result=plan(args.repo,args.target,args.running_sha,args.executor,args.evidence) if args.action=='plan' else postqa(args.repo,args.deployment_id,args.attempt,args.sha)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0 if args.action=='plan' or result['status']=='PASS' else 2
    except (OSError,ValueError,subprocess.SubprocessError) as exc:
        print(json.dumps({'status':'ERROR','reason':str(exc)},ensure_ascii=False));return 1

if __name__=='__main__': raise SystemExit(main())
