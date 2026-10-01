#!/usr/bin/env python3
"""플러그인에 실리는 파일을 바꿨으면 .claude-plugin/plugin.json의 version을 올렸는지 검사한다.

팀원 캐시는 version이 바뀌어야 갱신된다. 올리지 않으면 머지해도 아무에게도 반영되지 않는다.

  python3 scripts/check_plugin_version.py --base origin/main
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

PLUGIN_PATHS = ("hooks/", "commands/", "skills/", "scripts/hook_stats.py", ".claude-plugin/plugin.json")
SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout


def parse(version: str) -> tuple[int, int, int]:
    m = SEMVER.match(version or "")
    if not m:
        raise ValueError(f"semver가 아닌 version: {version!r}")
    return tuple(int(x) for x in m.groups())  # type: ignore[return-value]


def plugin_changes(root: Path, base: str) -> list[str]:
    changed = git(root, "diff", "--name-only", f"{base}...HEAD").splitlines()
    return [f for f in changed if f.startswith(PLUGIN_PATHS) and "/tests/" not in f and "/evals/" not in f]


def check(root: Path, base: str) -> list[str]:
    changes = plugin_changes(root, base)
    if not changes:
        return []
    head = json.loads((root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]
    try:
        old = json.loads(git(root, "show", f"{base}:.claude-plugin/plugin.json"))["version"]
    except subprocess.CalledProcessError:
        return []  # 기준 브랜치에 플러그인이 없음 — 첫 도입
    if parse(head) <= parse(old):
        shown = ", ".join(changes[:5]) + (f" 외 {len(changes) - 5}개" if len(changes) > 5 else "")
        return [f"플러그인 파일이 바뀌었는데({shown}) version이 그대로입니다: {old} → {head}. "
                ".claude-plugin/plugin.json의 version을 올리세요 (동작 변경 minor, 수정 patch)."]
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="플러그인 version 증가 검사")
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    problems = check(args.root, args.base)
    for problem in problems:
        print(f"ERROR: {problem}")
    if not problems:
        print("plugin version check passed")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
