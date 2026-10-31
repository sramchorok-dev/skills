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
    cards, nodes, viewports, checks, unmatched = set(), set(), set(), set(), []
    for path in files:
        matched = [r for r in data['rules'] if any(fnmatch.fnmatchcase(path, pattern) for pattern in r.get('paths', []))]
        if not matched: unmatched.append(path)
        for rule in matched:
            if not rule.get('cards') or not rule.get('figma_nodes') or not rule.get('viewports') or not rule.get('checks'): unmatched.append(path)
            cards.update(rule.get('cards', [])); nodes.update(rule.get('figma_nodes', [])); viewports.update(rule.get('viewports', [])); checks.update(rule.get('checks', []))
    return {'status':'BLOCKED' if unmatched else 'READY', 'reason':'매핑되지 않은 UI 변경' if unmatched else '',
            'unmapped':sorted(set(unmatched)), 'cards':sorted(cards), 'figma_nodes':sorted(nodes), 'viewports':sorted(viewports), 'checks':sorted(checks)}

def assess_run(plan, manifest, report, head, dirty, design=None):
    """Never promote missing/partial scope, stale revisions or dirty trees to PASS."""
    if dirty or not head: return 'BLOCKED'
    if plan['status'] != 'READY': return 'BLOCKED'
    revision = manifest.get('environment', {}).get('revisions', {}).get('fe')
    if revision != head: return 'BLOCKED'
    selected = {cell['cell_id'] for cell in manifest.get('cells', [])}
    required = {f'{card}@{viewport}' for card in plan['cards'] for viewport in plan['viewports']}
    if not required or not required.issubset(selected): return 'BLOCKED'
    if report['counts']['FAIL']: return 'FAIL'
    # Receipt data cannot yet establish independent Figma source or visual equivalence.
    # Never auto-promote to PASS until source verification is implemented.
    if report['selected_scope_complete'] and design and design['verdict']=='PASS': return 'BLOCKED'
    return 'BLOCKED'

def enqueue(root, path=None):
    root = Path(root).resolve()
    if not c.is_team_repo(root): raise ValueError('팀 레포가 아닙니다')
    fingerprint = snapshot(root)
    if fingerprint is None: return None
    key = hashlib.sha256(f'{root}\0{fingerprint}\0local-design-v1'.encode()).hexdigest()[:24]
    now = datetime.now(timezone.utc).isoformat(timespec='seconds')
    with connect(path) as db:
        db.execute("UPDATE tasks SET status='STALE' WHERE root=? AND fingerprint<>? AND status IN ('PENDING','RUNNING','BLOCKED')", (str(root), fingerprint))
        db.execute('INSERT OR IGNORE INTO tasks VALUES (?, ?, ?, ?, ?, ?)', (key, root.name, str(root), fingerprint, 'PENDING', now))
    return key

def tasks(root=None, path=None):
    with connect(path) as db:
        db.row_factory = sqlite3.Row
        if root:
            rows = db.execute('SELECT * FROM tasks WHERE root=? ORDER BY created DESC', (str(Path(root).resolve()),)).fetchall()
        else: rows = db.execute('SELECT * FROM tasks ORDER BY created DESC').fetchall()
        output=[]
        for row in rows:
            item=dict(row)
            if item['status']=='PASS':
                try:
                    repo=Path(item['root'])
                    if snapshot(repo)!=item['fingerprint']: raise ValueError('source changed')
                    dr=db.execute('SELECT path,receipt FROM designs WHERE task_id=?',(item['id'],)).fetchone()
                    rr=db.execute('SELECT path FROM runs WHERE task_id=? ORDER BY rowid DESC LIMIT 1',(item['id'],)).fetchone()
                    if not dr or not rr: raise ValueError('missing receipt')
                    plan=design_plan(repo); head=c.git(repo,'rev-parse','HEAD')
                    design=qa_design_receipt.validate(dr['path'],plan['figma_nodes'],plan['viewports'],head,plan['checks'])
                    if design!=json.loads(dr['receipt']): raise ValueError('design evidence changed')
                    script=Path(__file__).resolve().parents[1]/'skills/gardenstep-qa-run/scripts/browser_agent.py'
                    spec=importlib.util.spec_from_file_location('gardenstep_browser_agent',script)
                    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
                    report=module.summary(Path(rr['path'])); manifest,_,_=module.load_run(Path(rr['path']))
                    state=assess_run(plan,manifest,report,head,bool(c.git(repo,'status','--porcelain')),design)
                    if state!='PASS': raise ValueError('evidence incomplete')
                except Exception:
                    item['status']='BLOCKED'
                    db.execute("UPDATE tasks SET status='BLOCKED' WHERE id=?",(item['id'],))
            output.append(item)
        return output

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['enqueue', 'status', 'start', 'block', 'link-run', 'link-design', 'plan'])
    parser.add_argument('--id', help='QA task ID')
    parser.add_argument('--run', help='existing browser-agent run directory')
    parser.add_argument('--receipt', help='design comparison receipt JSON')
    parser.add_argument('--repo', default='.')
    args = parser.parse_args()
    root = c.repo_root(args.repo)
    if not root: parser.error('git 레포를 찾을 수 없습니다')
    try:
        if args.action == 'plan': print(json.dumps(design_plan(root),ensure_ascii=False,indent=2))
        elif args.action == 'enqueue':
            key = enqueue(root)
            print(json.dumps({'task_id': key, 'status': 'PENDING' if key else 'NOT_APPLICABLE'}, ensure_ascii=False))
        elif args.action == 'status': print(json.dumps(tasks(root), ensure_ascii=False, indent=2))
        else:
            if not args.id: parser.error('--id is required')
            fingerprint = snapshot(root)
            with connect() as db:
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
                    design = qa_design_receipt.validate(args.receipt,plan['figma_nodes'],plan['viewports'],head,plan['checks'])
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
                    if design_row:
                        design=qa_design_receipt.validate(design_row[0],plan['figma_nodes'],plan['viewports'],head,plan['checks'])
                        if design != json.loads(design_row[1]): raise ValueError('Figma 증거가 기록 후 변경됐습니다')
                    state = assess_run(plan, manifest, report, head, bool(c.git(root,'status','--porcelain')), design)
                    db.execute('INSERT OR IGNORE INTO runs VALUES (?, ?, ?)', (args.id, str(Path(args.run).resolve()), report['run_id']))
                    db.execute('UPDATE tasks SET status=? WHERE id=?', (state, args.id))
                    print(json.dumps({'task_id': args.id, 'run_id': report['run_id'], 'counts':report['counts'], 'queue_status':state, 'scope':plan}, ensure_ascii=False))
                    return 0
                state = 'RUNNING' if args.action == 'start' else 'BLOCKED'
                db.execute('UPDATE tasks SET status=? WHERE id=?', (state, args.id))
                print(json.dumps({'task_id': args.id, 'status': state}))
    except (ValueError, OSError, sqlite3.Error) as exc:
        print(f'QA queue error: {exc}', file=sys.stderr); return 1
    return 0
if __name__ == '__main__': sys.exit(main())
