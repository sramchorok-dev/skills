#!/usr/bin/env python3
"""PR마다 한 파일짜리 변경기록(docs/changes/YYYY/YYYY-MM-DD-<branch>.md)을 만들고 검사한다.

  new     이 브랜치의 기록을 만든다(이미 있으면 경로만 출력)
  check   기록이 있는지, '왜'가 채워졌는지, 마이그레이션이면 rollback이 적혔는지 검사 (CI·PR 게이트)
  find    이 브랜치의 기록 경로 출력
  set-pr  frontmatter의 pr 값을 채운다

표준 라이브러리만 쓴다. hook(guard_bash)이 이 모듈을 import해 check_record·receipt_section을 재사용한다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
import sys
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parents[1] / "assets" / "change-record.md"
TYPES = {"feat", "fix", "refactor", "perf", "migration", "chore", "docs", "test", "ci"}
RISKS = {"normal", "money", "migration", "security", "infra"}
ROLLBACKS = {"image", "rds-snapshot", "config", "revert", "n/a"}
REQUIRED_KEYS = ("date", "branch", "type", "risk", "rollback")

_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_PLACEHOLDER_RE = re.compile(r"^<[^>]*>$")
_MIGRATION_PATH_RE = re.compile(r"(?:^|/)db/changelog/|(?:^|/)migrations?/")


# ---------------------------------------------------------------- git

def _git(root: Path, *args: str) -> str | None:
    try:
        done = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def current_branch(root: Path) -> str:
    return _git(root, "branch", "--show-current") or ""


def branch_slug(branch: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", branch).strip("-").lower()


def changed_files(root: Path, base: str | None) -> list[str]:
    files: set[str] = set()
    if base:
        mb = _git(root, "merge-base", base, "HEAD")
        if mb:
            files.update((_git(root, "diff", "--name-only", mb) or "").splitlines())
    files.update((_git(root, "diff", "--name-only", "HEAD") or "").splitlines())
    files.update((_git(root, "ls-files", "--others", "--exclude-standard") or "").splitlines())
    return sorted(f for f in files if f)


# ---------------------------------------------------------------- 문서 구조

def parse(text: str) -> tuple[dict[str, str], str]:
    """(frontmatter, body). frontmatter가 없으면 빈 dict."""
    lines = text.replace("\r\n", "\n").split("\n")
    if not lines or lines[0].strip() != "---":
        return {}, text
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        return {}, text
    meta: dict[str, str] = {}
    for line in lines[1:end]:
        line = line.split(" #", 1)[0].rstrip()
        if ":" in line and not line.lstrip().startswith("#"):
            key, value = line.split(":", 1)
            meta[key.strip()] = value.strip().strip('"').strip("'")
    return meta, "\n".join(lines[end + 1:])


def section(body: str, title_re: str) -> str | None:
    text = _COMMENT_RE.sub("", body.replace("\r\n", "\n"))
    lines = text.split("\n")
    pattern = re.compile(title_re)
    for i, line in enumerate(lines):
        m = _HEADING_RE.match(line)
        if not m or not pattern.search(m.group(2)):
            continue
        level = len(m.group(1))
        collected = []
        for nxt in lines[i + 1:]:
            h = _HEADING_RE.match(nxt)
            if h and len(h.group(1)) <= level:
                break
            collected.append(nxt)
        return "\n".join(collected)
    return None


def receipt_section(body: str) -> str | None:
    """PR 본문의 `검증`(구 `테스트 영수증`) 섹션. test-gate와 같은 기준."""
    return section(body, r"(검증|테스트\s*영수증)")


def has_content(text: str | None) -> bool:
    if text is None:
        return False
    for raw in text.split("\n"):
        line = raw.strip().lstrip("-*").strip()
        if line and not _PLACEHOLDER_RE.match(line):
            return True
    return False


# ---------------------------------------------------------------- 검사

def find_record(root: Path, branch: str) -> Path | None:
    slug = branch_slug(branch)
    if not slug:
        return None
    matches = sorted((root / "docs" / "changes").glob(f"**/*-{slug}.md"))
    return matches[-1] if matches else None


def validate_text(text: str, touched_migration: bool = False) -> list[str]:
    meta, body = parse(text)
    problems: list[str] = []
    if not meta:
        return ["frontmatter(--- … ---)가 없습니다"]
    missing = [k for k in REQUIRED_KEYS if not meta.get(k)]
    if missing:
        problems.append(f"frontmatter 필수 값 누락: {', '.join(missing)}")
    if meta.get("type") and meta["type"] not in TYPES:
        problems.append(f"type `{meta['type']}`는 허용 값이 아닙니다 ({'|'.join(sorted(TYPES))})")
    if meta.get("risk") and meta["risk"] not in RISKS:
        problems.append(f"risk `{meta['risk']}`는 허용 값이 아닙니다 ({'|'.join(sorted(RISKS))})")
    if meta.get("rollback") and meta["rollback"] not in ROLLBACKS:
        problems.append(f"rollback `{meta['rollback']}`는 허용 값이 아닙니다 ({'|'.join(sorted(ROLLBACKS))})")
    if (touched_migration or meta.get("type") == "migration" or meta.get("risk") == "migration") \
            and meta.get("rollback") in (None, "", "n/a", "image"):
        problems.append("마이그레이션 변경은 rollback을 `rds-snapshot` 등 실제 복구 방법으로 적어야 합니다 "
                        "(Liquibase가 다르면 이미지 롤백 불가)")
    if not has_content(section(body, r"무엇이\s*바뀌었나")):
        problems.append("`## 무엇이 바뀌었나`가 비어 있습니다")
    if not has_content(section(body, r"^왜")):
        problems.append("`## 왜`가 비어 있습니다 — 사용자·이슈에서 받은 이유를 적습니다(추측 금지)")
    return problems


def check_record(root: Path, branch: str, base: str | None = None) -> list[str]:
    record = find_record(root, branch)
    if record is None:
        return [f"`docs/changes/**/*-{branch_slug(branch) or '<branch>'}.md` 기록이 없습니다"]
    base = base or next((r for r in ("origin/dev", "origin/main") if _git(root, "rev-parse", "--verify", "--quiet", r)), None)
    touched = any(_MIGRATION_PATH_RE.search(f) for f in changed_files(root, base))
    rel = record.relative_to(root).as_posix()
    return [f"{rel}: {p}" for p in validate_text(record.read_text(encoding="utf-8"), touched)]


# ---------------------------------------------------------------- 생성

def new_record(root: Path, branch: str, change_type: str, title: str, today: dt.date | None = None) -> Path:
    existing = find_record(root, branch)
    if existing:
        return existing
    today = today or dt.date.today()
    slug = branch_slug(branch)
    if not slug:
        raise SystemExit("브랜치 이름을 알 수 없습니다(detached HEAD). --branch로 지정하세요.")
    path = root / "docs" / "changes" / f"{today:%Y}" / f"{today:%Y-%m-%d}-{slug}.md"
    text = TEMPLATE.read_text(encoding="utf-8")
    text = (text.replace("{{date}}", today.isoformat())
                .replace("{{branch}}", branch)
                .replace("{{type}}", change_type)
                .replace("{{title}}", title or "<한 줄: 무엇이 어떻게 달라졌나>"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def set_pr(record: Path, number: str) -> None:
    text = record.read_text(encoding="utf-8")
    text, count = re.subn(r"(?m)^pr:.*$", f"pr: {number}", text, count=1)
    if not count:
        raise SystemExit(f"{record}: frontmatter에 pr 줄이 없습니다")
    record.write_text(text, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PR 변경기록 생성·검사")
    parser.add_argument("command", choices=["new", "check", "find", "set-pr"])
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--branch", help="기본: 현재 브랜치 (CI는 GITHUB_HEAD_REF)")
    parser.add_argument("--base", help="변경 파일 비교 기준 (기본 origin/dev → origin/main)")
    parser.add_argument("--type", default="feat", choices=sorted(TYPES))
    parser.add_argument("--title", default="")
    parser.add_argument("--pr", help="set-pr에 쓸 PR 번호")
    args = parser.parse_args(argv)

    root = Path(_git(args.repo, "rev-parse", "--show-toplevel") or args.repo).resolve()
    branch = args.branch or current_branch(root)

    if args.command == "new":
        print(new_record(root, branch, args.type, args.title).relative_to(root))
        return 0
    if args.command == "find":
        record = find_record(root, branch)
        if record is None:
            return 1
        print(record.relative_to(root))
        return 0
    if args.command == "set-pr":
        record = find_record(root, branch)
        if record is None or not args.pr:
            print("기록 또는 --pr 값이 없습니다", file=sys.stderr)
            return 1
        set_pr(record, args.pr)
        print(record.relative_to(root))
        return 0

    problems = check_record(root, branch, args.base)
    if problems:
        print("❌ 변경기록 검사 실패")
        for problem in problems:
            print(f"- {problem}")
        print("작성법: https://github.com/sramchorok-dev/skills/blob/main/docs/team-agent-guide.md#변경기록")
        return 1
    print(f"✅ 변경기록 확인: {find_record(root, branch).relative_to(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
