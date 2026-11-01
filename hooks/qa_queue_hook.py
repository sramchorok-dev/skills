#!/usr/bin/env python3
"""Common SessionStart/Stop adapter: enqueue only; agents run QA explicitly."""
import sys
import json
from pathlib import Path
import _common as c
import qa_queue

def main():
    if '--self-test' in sys.argv:
        print(json.dumps({'status':'adapter-ready','python':sys.executable}))
        return
    data = c.read_input()
    root = c.repo_root(data.get('cwd') or '.')
    if not root or not c.is_team_repo(root): return
    try:
        messages = []
        key = qa_queue.enqueue(root)
        if key:
            messages.append(f"[gardenstep QA] 로컬 디자인 QA 대기: {key}. 실제 브라우저/Figma 검증은 gardenstep-qa-run으로 수행하세요. 자동 PASS가 아닙니다. assign으로 담당·기한·공유 링크를 지정하고 handoff를 PR 검증에 남기세요.")
        rows=qa_queue.tasks(root, verify=False)
        pending=[x for x in rows if x['status'] in ('PENDING','RUNNING','BLOCKED','FAIL')]
        if pending:
            overdue=sum(x['overdue'] for x in pending); unassigned=sum(x['needs_assignment'] for x in pending)
            messages.append(f'[gardenstep QA] 미완료 {len(pending)}건 · 담당 미지정 {unassigned}건 · 기한 초과 {overdue}건. handoff로 공유 추적을 갱신하세요. 자동 Telegram 전송은 하지 않습니다.')
        if messages: c.emit({'systemMessage': '\n'.join(messages)})
    except Exception as exc:
        print(f'[gardenstep QA] 대기 등록 실패: {type(exc).__name__}. 수동으로 qa_queue.py enqueue를 실행하세요.', file=sys.stderr)
if __name__ == '__main__': main()
