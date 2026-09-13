#!/usr/bin/env python3
"""Install repository skills into the shared ~/.agents skill root."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]


class InstallError(RuntimeError):
    pass


def install_skill(source_root: Path, target_root: Path, name: str) -> str:
    source = (source_root / name).resolve()
    if not (source / "SKILL.md").is_file():
        raise InstallError(f"unknown or invalid skill: {name}")
    target_root.mkdir(parents=True, exist_ok=True)
    target = target_root / name
    if target.is_symlink():
        if target.resolve() == source:
            return "unchanged"
        raise InstallError(f"target symlink points elsewhere: {target}")
    if target.exists():
        raise InstallError(f"target already exists and is not a symlink: {target}")
    target.symlink_to(source, target_is_directory=True)
    return "installed"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install shared agent skills from this repository")
    parser.add_argument("skills", nargs="*", help="skill names; default: all")
    parser.add_argument(
        "--target-root",
        type=Path,
        default=Path(os.environ.get("AGENTS_SKILL_HOME", "~/.agents/skills")).expanduser(),
    )
    parser.add_argument("--no-sync", action="store_true", help="skip ~/.agents/sync.py")
    args = parser.parse_args(argv)
    available = sorted(path.name for path in (REPO_ROOT / "skills").iterdir() if path.is_dir())
    names = args.skills or available
    try:
        for name in names:
            result = install_skill(REPO_ROOT / "skills", args.target_root, name)
            print(f"{result}: {name}")
        sync = Path("~/.agents/sync.py").expanduser()
        if not args.no_sync and sync.is_file():
            subprocess.run([sys.executable, str(sync), "--dry-run"], check=True)
            subprocess.run([sys.executable, str(sync), "--skills-only"], check=True)
            print("synced: Claude Code, Codex, OpenCode")
        elif not args.no_sync:
            print("sync skipped: ~/.agents/sync.py not found")
        return 0
    except (InstallError, OSError, subprocess.CalledProcessError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
