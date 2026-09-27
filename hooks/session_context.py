#!/usr/bin/env python3
"""SessionStart — 팀 레포에서 세션을 열면 핵심 규칙과 현재 상태를 짧게 넣어준다.

stdout이 그대로 에이전트 컨텍스트가 된다. 10줄 안쪽을 유지한다.
"""
from __future__ import annotations

import json
from pathlib import Path

import _common as c

PLUGIN_ROOT = Path(__file__).resolve().parents[1]

RULES = [
    "main·release/* 직접 push, 머지, 배포·롤백 실행, DB 쓰기는 사람 확인을 거친다 (hook이 확인을 요청한다).",
    "동작을 바꾸면 테스트를 먼저 쓰고 실패를 확인한다. PR은 /ship-pr로 연다.",
    "변경기록(docs/changes)의 '왜'는 사용자·이슈에서 받는다. 모르면 묻고 추측하지 않는다.",
]


def plugin_version() -> str:
    try:
        return json.loads((PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]
    except (OSError, KeyError, json.JSONDecodeError):
        return "?"


def agents_md_shadowed(root: Path) -> bool:
    """AGENTS.md가 있는데 작업 디렉터리나 상위에 CLAUDE.md가 있으면 Claude Code는 AGENTS.md를 읽지 않는다."""
    if not (root / "AGENTS.md").is_file():
        return False
    try:
        settings = json.loads((Path.home() / ".claude" / "settings.json").read_text(encoding="utf-8"))
        mode = settings["pluginConfigs"]["agents-md@builtin"]["options"]["instructionFiles"]
        if mode == "claude-md-and-agents-md":
            return False
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        pass
    home = Path.home().resolve()
    for directory in [root, *root.parents]:
        if any((directory / name).is_file() for name in ("CLAUDE.md", "CLAUDE.local.md", ".claude/CLAUDE.md")):
            return True
        if directory == home:
            break
    return False


def build(root: Path) -> str:
    branch = c.current_branch(root) or "(detached)"
    lines = [f"[gardenstep-team v{plugin_version()}] 브랜치 `{branch}` · 기준 `{c.base_ref(root) or '없음'}`"]
    lines += [f"- {rule}" for rule in RULES]
    if c.PROTECTED_BRANCH_RE.match(branch) or branch == "dev":
        lines.append(f"⚠ `{branch}`에서 작업 중입니다. 코드 변경은 새 브랜치(worktree)에서 하세요.")
    if agents_md_shadowed(root):
        lines.append("⚠ 상위 디렉터리의 CLAUDE.md 때문에 이 레포의 AGENTS.md가 로드되지 않습니다. "
                     "/config → Project instructions를 `claude-md-and-agents-md`로 바꾸거나 AGENTS.md를 직접 읽으세요.")
    changed = c.changed_files(root)
    if any(c.is_source_file(f) for f in changed) and c.find_change_record(root, branch) is None:
        lines.append("- 이 브랜치의 변경기록(docs/changes)이 아직 없습니다. PR 전에 /ship-pr이 만들어 줍니다.")
    return "\n".join(lines)


def main() -> int:
    data = c.read_input()
    try:
        root = c.repo_root(data.get("cwd") or ".")
        if root is None or not c.is_team_repo(root):
            return 0
        print(build(root))
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
