"""gardenstep-team hook 공통 도구. 표준 라이브러리만 쓴다.

hook은 실패해도 작업을 막지 않는다: 예상 못 한 예외는 조용히 통과(exit 0)시키고,
막아야 할 때만 명시적으로 JSON 결정을 출력한다.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

TEAM_REMOTE_RE = re.compile(r"sramchorok-dev/")
PROTECTED_BRANCH_RE = re.compile(r"^(main|master|release/.+)$")


LOG_MAX_BYTES = 2 * 1024 * 1024


def log_path() -> Path:
    """hook 결정 로그. 각자 컴퓨터에만 남고 어디에도 전송하지 않는다."""
    override = os.environ.get("GARDENSTEP_TEAM_LOG")
    return Path(override) if override else Path.home() / ".claude" / "gardenstep-team" / "decisions.jsonl"


def log_decision(hook: str, decision: str, rules: list[str], root: Path | None = None) -> None:
    """결정 한 건을 JSONL로 남긴다. 명령·파일 내용은 기록하지 않고 규칙 ID와 레포 이름만 남긴다."""
    if os.environ.get("GARDENSTEP_TEAM_LOG_DISABLED") == "1":
        return
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "hook": hook,
        "decision": decision,
        "rules": rules,
        "repo": root.name if root else "",
    }
    try:
        path = log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > LOG_MAX_BYTES:
            path.replace(path.with_suffix(".jsonl.1"))
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def read_input() -> dict:
    try:
        return json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return {}


def emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def git(cwd: str | Path, *args: str, timeout: int = 10) -> str | None:
    """git 명령 stdout. 실패하면 None."""
    try:
        done = subprocess.run(
            ["git", "-C", str(cwd), *args],
            capture_output=True, text=True, timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if done.returncode != 0:
        return None
    return done.stdout.strip()


def repo_root(cwd: str | Path) -> Path | None:
    out = git(cwd, "rev-parse", "--show-toplevel")
    return Path(out) if out else None


def is_team_repo(root: Path) -> bool:
    remotes = git(root, "remote", "-v") or ""
    return bool(TEAM_REMOTE_RE.search(remotes))


def current_branch(root: Path) -> str:
    return git(root, "branch", "--show-current") or ""


def base_ref(root: Path) -> str | None:
    """PR 기준 브랜치. dev가 기본이고, dev가 없는 레포는 main."""
    for ref in ("origin/dev", "origin/main", "origin/master"):
        if git(root, "rev-parse", "--verify", "--quiet", ref) is not None:
            return ref
    return None


def merge_base(root: Path) -> str | None:
    ref = base_ref(root)
    if not ref:
        return None
    return git(root, "merge-base", ref, "HEAD")


def changed_files(root: Path) -> list[str]:
    """merge-base 이후 이 브랜치가 바꾼 파일 + 작업 트리 변경 + 미추적 새 파일."""
    base = merge_base(root)
    files: set[str] = set()
    if base:
        files.update((git(root, "diff", "--name-only", base) or "").splitlines())
    files.update((git(root, "diff", "--name-only", "HEAD") or "").splitlines())
    files.update((git(root, "ls-files", "--others", "--exclude-standard") or "").splitlines())
    return sorted(f for f in files if f)


def branch_slug(branch: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", branch).strip("-").lower()


# ---------------------------------------------------------------- 변경 분류

_JS_TEST_RE = re.compile(r"(^|/)(tests?|__tests__|e2e)/|\.(test|spec)\.[cm]?[jt]sx?$")
_PY_TEST_RE = re.compile(r"(^|/)tests?/|(^|/)test_[^/]+\.py$|_test\.py$")
_JS_SOURCE_RE = re.compile(
    r"^(src/|app/|components/|containers/|lib/|hooks/|atoms/|store/|api/|actions/|utils/|middleware\.ts$)"
)


def is_test_file(path: str) -> bool:
    if path.startswith("src/test/"):
        return True
    return bool(_JS_TEST_RE.search(path) or (path.endswith(".py") and _PY_TEST_RE.search(path)))


def is_source_file(path: str) -> bool:
    """사용자 동작이나 계산을 담을 수 있는 코드. 문서·설정·CI·생성물은 제외."""
    if is_test_file(path) or path.endswith(".d.ts"):
        return False
    if path.startswith("src/main/") and path.endswith((".java", ".kt")):
        return True
    if re.search(r"\.[cm]?[jt]sx?$", path):
        return bool(_JS_SOURCE_RE.match(path))
    if path.endswith(".py"):
        return not path.startswith(("scripts/", "docs/"))
    return False


def find_change_record(root: Path, branch: str) -> Path | None:
    slug = branch_slug(branch)
    if not slug:
        return None
    matches = sorted((root / "docs" / "changes").glob(f"**/*-{slug}.md"))
    return matches[-1] if matches else None
