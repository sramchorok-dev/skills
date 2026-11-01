#!/usr/bin/env python3
"""Local, tool-independent QA request queue. Never treats a request as a pass."""
from __future__ import annotations
import argparse
import hashlib
import fnmatch
import importlib.util
import qa_design_receipt
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import re
from contextlib import closing
from datetime import datetime, timezone
import _common as c

UI_PREFIXES = ('app/', 'src/', 'components/', 'containers/', 'hooks/', 'atoms/', 'store/', 'lib/', 'utils/', 'actions/', 'api/', 'public/', 'styles/', 'docs/design/')
UI_SUFFIXES = ('.ts', '.tsx', '.js', '.jsx', '.mjs', '.css', '.scss', '.json', '.md', '.svg', '.png', '.jpg', '.jpeg', '.webp', '.avif', '.woff', '.woff2', '.ttf')
CONFIG_FILES = ('package.json', 'package-lock.json', 'pnpm-lock.yaml', 'yarn.lock', 'next.config.ts', 'next.config.js', 'next.config.mjs', 'tailwind.config.ts', 'tailwind.config.js', 'postcss.config.js', 'postcss.config.mjs', 'tsconfig.json', 'docs/qa/local-design-map.json')

def affects_ui(path):
    return path in CONFIG_FILES or (path.startswith(UI_PREFIXES) and path.lower().endswith(UI_SUFFIXES))

def db_path():
    return Path(os.environ.get('GARDENSTEP_QA_DB', str(Path.home() / '.local/state/gardenstep-team/qa.sqlite3')))

def connect(path=None):
    path = Path(path or db_path()); path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    db = sqlite3.connect(path, timeout=2)
    os.chmod(path, 0o600)
    db.execute('CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, repo TEXT NOT NULL, root TEXT NOT NULL, fingerprint TEXT NOT NULL, status TEXT NOT NULL, created TEXT NOT NULL)')
    columns = {row[1] for row in db.execute('PRAGMA table_info(tasks)')}
    for name in ('owner', 'due_at', 'tracking_url'):
        if name not in columns: db.execute(f"ALTER TABLE tasks ADD COLUMN {name} TEXT")
    db.execute('CREATE TABLE IF NOT EXISTS runs (task_id TEXT NOT NULL, path TEXT NOT NULL, run_id TEXT NOT NULL, PRIMARY KEY(task_id,path))')
    db.execute('CREATE TABLE IF NOT EXISTS designs (task_id TEXT PRIMARY KEY, path TEXT NOT NULL, receipt TEXT NOT NULL)')
    return db

def snapshot(root):
    """Hash source content, HEAD, paths and all changed files (not source contents in DB)."""
    base = c.merge_base(root)
    if not base:
        raise ValueError('origin/dev 또는 origin/main 기준을 찾을 수 없습니다')
    files = c.changed_files(root)
    ui = [p for p in files if affects_ui(p)]
    if not ui: return None
    digest = hashlib.sha256()
    # Source fingerprint is stable across documentation-only commits; policy/config content participates.
    relevant = sorted(set(ui) | {p for p in CONFIG_FILES if (root / p).is_file()})
    for name in relevant:
        path = root / name
        digest.update(name.encode('utf-8', errors='surrogateescape') + b'\0')
        if path.is_file() and not path.is_symlink():
            with path.open('rb') as fh:
                while data := fh.read(1024 * 1024): digest.update(data)
        else: digest.update(b'<deleted-or-symlink>')
    return digest.hexdigest()

def design_plan(root):
    """Explicit mappings only. Unknown changed paths are never treated as covered."""
    files = [p for p in c.changed_files(root) if affects_ui(p)]
    map_path = Path(root) / 'docs/qa/local-design-map.json'
    if not map_path.is_file():
        return {'status':'BLOCKED', 'reason':'docs/qa/local-design-map.json 없음', 'unmapped':files, 'cards':[], 'figma_nodes':[]}
    data = json.loads(map_path.read_text(encoding='utf-8'))
    if data.get('schema_version') != 1 or not isinstance(data.get('rules'),list):
        raise ValueError('디자인 매핑 스키마 오류')
    cards, nodes, viewports, checks, unmatched, questions = set(), set(), set(), set(), [], set()
    required_cells, design_cells, exemptions = set(), {}, []
    for path in files:
        matched = [r for r in data['rules'] if any(fnmatch.fnmatchcase(path, pattern) for pattern in r.get('paths', []))]
        if not matched: unmatched.append(path)
        for rule in matched:
            questions.update(rule.get('open_questions', []))
            if not rule.get('cards') or not rule.get('viewports'): unmatched.append(path)
            kind = rule.get('design', 'required')
            if kind == 'not-applicable':
                reason = rule.get('reason', '')
                if not isinstance(reason, str) or not reason.strip(): unmatched.append(path)
                else: exemptions.append({'path': path, 'reason': reason.strip()})
            elif kind == 'required':
                if not rule.get('figma_nodes') or not rule.get('checks'): unmatched.append(path)
                for node in rule.get('figma_nodes', []):
                    for viewport in rule.get('viewports', []):
                        design_cells.setdefault((node, viewport), set()).update(rule.get('checks', []))
                nodes.update(rule.get('figma_nodes', [])); checks.update(rule.get('checks', []))
            else: unmatched.append(path)
            required_cells.update(f'{card}@{viewport}' for card in rule.get('cards', []) for viewport in rule.get('viewports', []))
            cards.update(rule.get('cards', [])); viewports.update(rule.get('viewports', []))
    return {'status':'BLOCKED' if unmatched or questions else 'READY', 'reason':'매핑 누락 또는 미확정 기준' if unmatched or questions else '', 'open_questions':sorted(questions),
            'unmapped':sorted(set(unmatched)), 'cards':sorted(cards), 'figma_nodes':sorted(nodes), 'viewports':sorted(viewports), 'checks':sorted(checks),
            'required_cells': sorted(required_cells), 'design_required': bool(design_cells), 'design_exemptions': exemptions,
            'design_cells': [{'node': n, 'viewport': v, 'checks': sorted(cs)} for (n,v),cs in sorted(design_cells.items())]}

def validate_design(path, plan, head):
    return qa_design_receipt.validate(path, plan['figma_nodes'], plan['viewports'], head, plan['checks'], required_cells=plan.get('design_cells'))


def assess_run(plan, manifest, report, head, dirty, design=None):
    """Never promote missing/partial scope, stale revisions or dirty trees to PASS."""
    if dirty or not head: return 'BLOCKED'
    if plan['status'] != 'READY': return 'BLOCKED'
    revision = manifest.get('environment', {}).get('revisions', {}).get('fe')
    if revision != head: return 'BLOCKED'
    selected = {cell['cell_id'] for cell in manifest.get('cells', [])}
    required = set(plan.get('required_cells', [f'{card}@{viewport}' for card in plan['cards'] for viewport in plan['viewports']]))
    if not required or not required.issubset(selected): return 'BLOCKED'
    if report['counts']['FAIL']: return 'FAIL'
    # PASS describes recorded observations; the receipt cannot prove observer honesty.
    if report['selected_scope_complete'] and (plan.get('design_required') is False or (design and design['verdict']=='PASS')): return 'PASS'
    return 'BLOCKED'

def enqueue(root, path=None):
    root = Path(root).resolve()
    if not c.is_team_repo(root): raise ValueError('팀 레포가 아닙니다')
    fingerprint = snapshot(root)
    if fingerprint is None: return None
    key = hashlib.sha256(f'{root}\0{fingerprint}\0local-design-v1'.encode()).hexdigest()[:24]
    now = datetime.now(timezone.utc).isoformat(timespec='seconds')
    with closing(connect(path)) as db, db:
        db.execute("UPDATE tasks SET status='STALE' WHERE root=? AND fingerprint<>? AND status IN ('PENDING','RUNNING','BLOCKED')", (str(root), fingerprint))
        db.execute('INSERT OR IGNORE INTO tasks (id,repo,root,fingerprint,status,created) VALUES (?, ?, ?, ?, ?, ?)', (key, root.name, str(root), fingerprint, 'PENDING', now))
    return key

def tasks(root=None, path=None, verify=True):
    with closing(connect(path)) as db, db:
        db.row_factory = sqlite3.Row
        if root:
            rows = db.execute('SELECT * FROM tasks WHERE root=? ORDER BY created DESC', (str(Path(root).resolve()),)).fetchall()
        else: rows = db.execute('SELECT * FROM tasks ORDER BY created DESC').fetchall()
        output=[]
        for row in rows:
            item=dict(row)
            if verify and item['status']=='PASS':
                try:
                    repo=Path(item['root'])
                    if snapshot(repo)!=item['fingerprint']: raise ValueError('source changed')
                    dr=db.execute('SELECT path,receipt FROM designs WHERE task_id=?',(item['id'],)).fetchone()
                    rr=db.execute('SELECT path FROM runs WHERE task_id=? ORDER BY rowid DESC LIMIT 1',(item['id'],)).fetchone()
                    if not rr: raise ValueError('missing QA receipt')
                    plan=design_plan(repo); head=c.git(repo,'rev-parse','HEAD')
                    design=None
                    if plan.get('design_required', True):
                        if not dr: raise ValueError('missing design receipt')
                        design=validate_design(dr['path'],plan,head)
                        if design!=json.loads(dr['receipt']): raise ValueError('design evidence changed')
                    script=Path(__file__).resolve().parents[1]/'skills/gardenstep-qa-run/scripts/browser_agent.py'
                    spec=importlib.util.spec_from_file_location('gardenstep_browser_agent',script)
                    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
                    report=module.summary(Path(rr['path'])); manifest,_,_=module.load_run(Path(rr['path']))
                    state=assess_run(plan,manifest,report,head,bool(c.git(repo,'status','--porcelain')),design)
                    if state!='PASS': raise ValueError('evidence incomplete')
                except (qa_design_receipt.ReceiptEnvironmentError, ImportError) as exc:
                    item['verification_error'] = str(exc)
                    item['verification_status'] = 'UNVERIFIED'
                except Exception:
                    item['status']='BLOCKED'
                    db.execute("UPDATE tasks SET status='BLOCKED' WHERE id=?",(item['id'],))
            item['needs_assignment'] = not all(item.get(k) for k in ('owner','due_at','tracking_url'))
            item['overdue'] = bool(item.get('due_at') and item['status'] in ('PENDING','RUNNING','BLOCKED','FAIL') and datetime.fromisoformat(item['due_at'].replace('Z','+00:00')) < datetime.now(timezone.utc))
            output.append(item)
        return output

def assign(root, task_id, owner, due_at, tracking_url, path=None):
    if not owner or not owner.strip(): raise ValueError('검수 담당자가 필요합니다')
    due = datetime.fromisoformat(due_at.replace('Z', '+00:00'))
    if due.tzinfo is None: raise ValueError('기한에 시간대가 필요합니다')
    if not re.fullmatch(r'https://github\.com/sramchorok-dev/[A-Za-z0-9_.-]+/(?:issues|pull)/[0-9]+', tracking_url or ''):
        raise ValueError('팀 GitHub issue 또는 PR 링크가 필요합니다')
    with closing(connect(path)) as db, db:
        result = db.execute('UPDATE tasks SET owner=?,due_at=?,tracking_url=? WHERE id=? AND root=?',
                            (owner.strip(), due.isoformat(), tracking_url, task_id, str(Path(root).resolve())))
        if result.rowcount != 1: raise ValueError('QA 작업을 찾을 수 없습니다')

def handoff(root, path=None):
    lines = ['# 로컬 QA 인계', '', '| 작업 | 상태 | 담당 | 기한 | 공유 추적 |', '|---|---|---|---|---|']
    for item in tasks(root, path):
        state = item['status']
        if item.get('verification_error'): state += ' / UNVERIFIED'
        if item['needs_assignment']: state += ' / UNASSIGNED'
        if item['overdue']: state += ' / OVERDUE'
        values = [item['id'], state, item.get('owner') or '-', item.get('due_at') or '-', item.get('tracking_url') or '-']
        lines.append('| ' + ' | '.join(str(v).replace('|',r'\|').replace('\n',' ') for v in values) + ' |')
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['enqueue', 'status', 'start', 'block', 'link-run', 'link-design', 'plan', 'assign', 'handoff'])
    parser.add_argument('--id', help='QA task ID')
    parser.add_argument('--run', help='existing browser-agent run directory')
    parser.add_argument('--receipt', help='design comparison receipt JSON')
    parser.add_argument('--repo', default='.')
    parser.add_argument('--owner')
    parser.add_argument('--due-at')
    parser.add_argument('--tracking-url')
    args = parser.parse_args()
    root = c.repo_root(args.repo)
    if not root: parser.error('git 레포를 찾을 수 없습니다')
    try:
        if args.action == 'plan': print(json.dumps(design_plan(root),ensure_ascii=False,indent=2))
        elif args.action == 'enqueue':
            key = enqueue(root)
            print(json.dumps({'task_id': key, 'status': 'PENDING' if key else 'NOT_APPLICABLE'}, ensure_ascii=False))
        elif args.action == 'assign':
            if not all((args.id,args.owner,args.due_at,args.tracking_url)): parser.error('assign requires --id --owner --due-at --tracking-url')
            assign(root,args.id,args.owner,args.due_at,args.tracking_url)
            print(handoff(root))
        elif args.action == 'handoff': print(handoff(root))
        elif args.action == 'status': print(json.dumps(tasks(root), ensure_ascii=False, indent=2))
        else:
            if not args.id: parser.error('--id is required')
            fingerprint = snapshot(root)
            with closing(connect()) as db, db:
                row = db.execute('SELECT fingerprint, status FROM tasks WHERE id=? AND root=?', (args.id, str(root))).fetchone()
                if not row: raise ValueError('QA 작업을 찾을 수 없습니다')
                if row[0] != fingerprint:
                    db.execute("UPDATE tasks SET status='STALE' WHERE id=?", (args.id,))
                    print('작업 버전이 변경되어 STALE 처리했습니다', file=sys.stderr)
                    return 1
                if row[1] not in ('PENDING', 'RUNNING', 'BLOCKED', 'FAIL'): raise ValueError('이미 종료된 작업입니다')
                if args.action == 'link-design':
                    if not args.receipt: parser.error('--receipt is required')
                    plan = design_plan(root)
                    if plan['status'] != 'READY': raise ValueError('디자인 매핑이 불완전합니다')
                    head=c.git(root,'rev-parse','HEAD')
                    design = validate_design(args.receipt,plan,head)
                    db.execute('INSERT OR REPLACE INTO designs VALUES (?, ?, ?)', (args.id, design['receipt'], json.dumps(design)))
                    # Never promote to PASS before linking and revalidating both QA and design receipts.
                    db.execute('UPDATE tasks SET status=? WHERE id=?', ('FAIL' if design['verdict']=='FAIL' else 'BLOCKED', args.id))
                    print(json.dumps({'task_id': args.id, 'design_verdict': design['verdict'], 'queue_status':'FAIL' if design['verdict']=='FAIL' else 'BLOCKED'},ensure_ascii=False))
                    return 0
                if args.action == 'link-run':
                    if not args.run: parser.error('--run is required')
                    script = Path(__file__).resolve().parents[1] / 'skills/gardenstep-qa-run/scripts/browser_agent.py'
                    spec = importlib.util.spec_from_file_location('gardenstep_browser_agent', script)
                    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
                    report = module.summary(Path(args.run))
                    manifest, _, _ = module.load_run(Path(args.run))
                    plan = design_plan(root)
                    head = c.git(root,'rev-parse','HEAD')
                    design_row=db.execute('SELECT path, receipt FROM designs WHERE task_id=?', (args.id,)).fetchone()
                    design=None
                    if design_row and plan.get('design_required', True):
                        design=validate_design(design_row[0],plan,head)
                        if design != json.loads(design_row[1]): raise ValueError('Figma 증거가 기록 후 변경됐습니다')
                    state = assess_run(plan, manifest, report, head, bool(c.git(root,'status','--porcelain')), design)
                    assignment = db.execute('SELECT owner,due_at,tracking_url FROM tasks WHERE id=?', (args.id,)).fetchone()
                    if state == 'PASS' and not all(assignment): state = 'BLOCKED'
                    db.execute('INSERT OR IGNORE INTO runs VALUES (?, ?, ?)', (args.id, str(Path(args.run).resolve()), report['run_id']))
                    db.execute('UPDATE tasks SET status=? WHERE id=?', (state, args.id))
                    print(json.dumps({'task_id': args.id, 'run_id': report['run_id'], 'counts':report['counts'], 'queue_status':state, 'scope':plan}, ensure_ascii=False))
                    return 0
                state = 'RUNNING' if args.action == 'start' else 'BLOCKED'
                db.execute('UPDATE tasks SET status=? WHERE id=?', (state, args.id))
                print(json.dumps({'task_id': args.id, 'status': state}))
    except (ValueError, OSError, sqlite3.Error, qa_design_receipt.ReceiptEnvironmentError) as exc:
        print(f'QA queue error: {exc}', file=sys.stderr); return 1
    return 0
if __name__ == '__main__': sys.exit(main())
