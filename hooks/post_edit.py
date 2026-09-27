#!/usr/bin/env python3
"""PostToolUse(Edit|Write|MultiEdit) — 테스트 파일에 새로 들어간 스멜을 바로 알려준다.

막지 않는다(이미 편집됨). 규칙 ID는 gardenstep-test-audit의 smell-catalog와 같다.
PR 단계에서 test-audit이 FAIL로 판정할 것을 편집 직후에 고치게 하는 것이 목적이다.
"""
from __future__ import annotations

import re

import _common as c

SMELLS: list[tuple[str, re.Pattern[str], str]] = [
    ("S-ONLY", re.compile(r"\b(?:test|it|describe)\.only\s*\(|\bfit\s*\(|\bfdescribe\s*\("),
     "`.only`가 남으면 CI에서 다른 테스트가 전부 건너뛰어집니다"),
    ("S-SKIP", re.compile(r"\b(?:test|it|describe)\.skip\s*\(|\bx(?:it|describe)\s*\(|@Disabled\b|@Ignore\b|"
                          r"pytest\.mark\.skip"),
     "건너뛴 테스트는 증거가 아닙니다. 필요하면 사유와 후속 이슈를 남기세요"),
    ("S-HARD-WAIT", re.compile(r"\bwaitForTimeout\s*\(|\bThread\.sleep\s*\(|\btime\.sleep\s*\("),
     "고정 대기 대신 관찰 가능한 상태를 기다리세요"),
    ("S-FIXME", re.compile(r"\b(?:FIXME|XXX)\b"), "테스트 안의 FIXME는 미완성 표시입니다"),
]


def new_text(tool_input: dict) -> str:
    parts = [tool_input.get("content") or "", tool_input.get("new_string") or ""]
    for edit in tool_input.get("edits") or []:
        if isinstance(edit, dict):
            parts.append(edit.get("new_string") or "")
    return "\n".join(parts)


def decide(tool_input: dict) -> dict | None:
    path = tool_input.get("file_path") or ""
    if not path or not c.is_test_file(_rel(path)):
        return None
    text = new_text(tool_input)
    found = [f"- `{rule}`: {why}" for rule, pattern, why in SMELLS if pattern.search(text)]
    if not found:
        return None
    message = "[gardenstep-team] 방금 편집한 테스트에 팀 규칙 위반 가능성이 있습니다:\n" + "\n".join(found)
    return {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": message}}


def _rel(path: str) -> str:
    """절대 경로에서 테스트 판별에 필요한 부분만 남긴다."""
    posix = path.replace("\\", "/")
    if "/src/test/" in posix:
        return "src/test/" + posix.split("/src/test/", 1)[1]
    for marker in ("/tests/", "/test/", "/__tests__/", "/e2e/"):
        if marker in posix:
            return marker.strip("/") + "/" + posix.split(marker, 1)[1]
    return posix.rsplit("/", 1)[-1]


def main() -> int:
    data = c.read_input()
    try:
        result = decide(data.get("tool_input") or {})
    except Exception:
        return 0
    if result:
        c.emit(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
