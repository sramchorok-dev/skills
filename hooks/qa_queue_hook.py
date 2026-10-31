#!/usr/bin/env python3
"""Common SessionStart/Stop adapter: enqueue only; agents run QA explicitly."""
import sys
from pathlib import Path
import _common as c
import qa_queue

def main():
    data = c.read_input()
    root = c.repo_root(data.get('cwd') or '.')
    if not root or not c.is_team_repo(root): return
    try:
        key = qa_queue.enqueue(root)
        if key:
            c.emit({"systemMessage": f"[gardenstep QA] 로컬 디자인 QA 대기: {key}. 실제 브라우저/Figma 검증은 gardenstep-qa-run으로 수행하세요. 자동 PASS가 아닙니다."})
    except Exception as exc:
        print(f'[gardenstep QA] 대기 등록 실패: {type(exc).__name__}. 수동으로 qa_queue.py enqueue를 실행하세요.', file=sys.stderr)
if __name__ == '__main__': main()
