#!/usr/bin/env python3
"""Stop — 코드가 바뀌었는데 테스트 변경이 하나도 없으면 한 번 되돌려 보낸다.

테스트 규칙 v1 §0: 바뀐 동작 하나에 테스트 하나. Stop은 매 응답 끝마다 발생하므로
같은 세션·브랜치에서 **한 번만** 막는다. 에이전트는 테스트를 추가하거나,
필요 없는 이유를 사용자에게 설명하고 끝내면 된다.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import _common as c

STATE_DIR = Path(os.environ.get("GARDENSTEP_TEAM_STATE", Path(tempfile.gettempdir()) / "gardenstep-team"))


def already_nudged(session_id: str, key: str) -> bool:
    path = STATE_DIR / f"stop-{c.branch_slug(session_id) or 'unknown'}.json"
    try:
        seen = set(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        seen = set()
    if key in seen:
        return True
    seen.add(key)
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(sorted(seen)), encoding="utf-8")
    except OSError:
        pass
    return False


def decide(data: dict) -> dict | None:
    if data.get("stop_hook_active"):
        return None
    root = c.repo_root(data.get("cwd") or ".")
    if root is None or not c.is_team_repo(root):
        return None
    changed = c.changed_files(root)
    sources = [f for f in changed if c.is_source_file(f)]
    tests = [f for f in changed if c.is_test_file(f)]
    if not sources or tests:
        return None
    branch = c.current_branch(root) or "detached"
    if already_nudged(data.get("session_id") or "", f"{root}:{branch}"):
        return None
    c.log_decision("stop_tests", "block", ["stop-no-tests"], root)
    shown = ", ".join(sources[:5]) + (f" 외 {len(sources) - 5}개" if len(sources) > 5 else "")
    return {
        "decision": "block",
        "reason": (
            "[gardenstep-team] 테스트 규칙 v1: 코드가 바뀌었는데(" + shown + ") 테스트 변경이 없습니다. "
            "바뀐 동작에 대한 테스트를 추가하거나(먼저 실패를 확인), 테스트가 필요 없는 이유를 "
            "사용자에게 한 줄로 설명한 뒤 마치세요. 이 알림은 이 브랜치에서 한 번만 나옵니다."
        ),
    }


def main() -> int:
    data = c.read_input()
    try:
        result = decide(data)
    except Exception:
        return 0
    if result:
        c.emit(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
