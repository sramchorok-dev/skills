#!/usr/bin/env python3
"""PostToolUse(Bash) — 확인(ask)을 거쳐 실제로 실행된 명령을 결정 로그에 남긴다.

guard_bash가 확인을 요청한 명령이 PostToolUse까지 왔다면 사람이 승인한 것이다.
규칙별 "확인 요청 수 대비 실행 수"(승인률)가 규칙 조정의 근거가 된다 — 거의 항상 승인되는 규칙은 오탐 후보다.
명령 내용은 기록하지 않는다.
"""
from __future__ import annotations

import re

import _common as c
import guard_bash as gb

_PR_CREATE_RE = re.compile(r"\bgh\s+pr\s+create\b")


def rule_ids(command: str, root) -> list[str]:
    ids = [rule_id for rule_id, _ in gb.risky_rules(command, root)]
    if _PR_CREATE_RE.search(command) and root is not None and c.is_team_repo(root):
        ids.append("pr-create")
    return ids


def main() -> int:
    data = c.read_input()
    command = (data.get("tool_input") or {}).get("command") or ""
    if not command.strip():
        return 0
    try:
        cwd = data.get("cwd") or ""
        root = c.repo_root(cwd) if cwd else None
        ids = rule_ids(command, root)
        if ids:
            c.log_decision("post_bash", "ran", ids, root)
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
