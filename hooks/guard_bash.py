#!/usr/bin/env python3
"""PreToolUse(Bash) 가드.

팀 정책(docs/adr/0002): Bash는 차단(deny)하지 않고 **사람에게 확인(ask)** 한다.
확인 사유는 사용자 프롬프트에 보이고, 같은 내용이 additionalContext로 에이전트에게도 전달된다.

1. 위험 명령 — 보호 브랜치 push·force push, 머지·배포·롤백 실행, DB 쓰기, 원격 서버, 파괴적 삭제 등
2. `gh pr create` 게이트 — 변경기록·`## 검증`·테스트 점검이 준비되지 않았으면 확인을 요청
"""
from __future__ import annotations

import importlib.util
import json
import re
import shlex
import subprocess
import tempfile
from pathlib import Path

import _common as c

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
AUDIT = PLUGIN_ROOT / "skills" / "gardenstep-test-audit" / "scripts" / "audit_tests.py"
CHANGE_RECORD = PLUGIN_ROOT / "skills" / "gardenstep-change-log" / "scripts" / "change_record.py"

I = re.IGNORECASE

# (규칙 ID, 정규식, 사유). 명령 전체 문자열에 대해 검사한다. ID는 결정 로그·통계에 쓰인다. 오탐은 확인 한 번으로 끝나므로 넓게 잡는다.
RULES: list[tuple[str, re.Pattern[str], str]] = [
    # --- git: 되돌리기 어려운 로컬 작업
    ("force-push", re.compile(r"\bgit\b[^|;&]*\s(?:push)\b[^|;&]*(?:\s--force\b|\s--force-with-lease\b|\s-f\b|\s\+\S)"),
     "force push — 원격 히스토리를 덮어씁니다"),
    ("push-delete", re.compile(r"\bgit\b[^|;&]*\spush\b[^|;&]*(?:\s--delete\b|\s-d\b|\s:\S)"),
     "원격 브랜치 삭제"),
    ("reset-hard", re.compile(r"\bgit\b[^|;&]*\sreset\s+[^|;&]*--hard\b"), "git reset --hard — 커밋 안 한 변경이 사라집니다"),
    ("clean-force", re.compile(r"\bgit\b[^|;&]*\sclean\s+-[a-zA-Z]*f"), "git clean -f — 미추적 파일이 삭제됩니다"),
    ("restore-all", re.compile(r"\bgit\b[^|;&]*\s(?:checkout|restore)\s+(?:--\s+)?\.(?:\s|$)"), "작업 트리 전체 되돌리기"),
    ("stash-drop", re.compile(r"\bgit\b[^|;&]*\sstash\s+(?:drop|clear)\b"), "stash 삭제"),
    ("branch-force-delete", re.compile(r"\bgit\b[^|;&]*\sbranch\s+[^|;&]*-D\b"), "브랜치 강제 삭제"),
    ("history-rewrite", re.compile(r"\bgit\b[^|;&]*\s(?:filter-branch|filter-repo)\b"), "히스토리 재작성"),
    ("no-verify", re.compile(r"\s--no-verify\b"), "--no-verify — git hook 검사를 건너뜁니다"),
    # --- GitHub: 머지·배포·설정
    ("skip-ci", re.compile(r"\[(?:skip ci|ci skip|no ci|skip actions|actions skip)\]", I),
     "[skip ci] — PR CI·빌드·DEV 배포가 돌지 않습니다 (CI 초록 없이 머지되는 경로)"),
    ("pr-merge", re.compile(r"\bgh\s+pr\s+merge\b"), "PR 머지 — 머지는 CI 초록 + JD 승인 후에 합니다"),
    ("workflow-run", re.compile(r"\bgh\s+(?:workflow\s+(?:run|enable|disable)|run\s+rerun)\b"),
     "GitHub Actions 실행 — 배포·롤백 워크플로일 수 있습니다 (오래된 run 재실행은 이전 버전 재배포 위험)"),
    ("gh-secret", re.compile(r"\bgh\s+(?:secret|variable)\s+(?:set|delete|remove)\b"), "GitHub 비밀값·변수 변경"),
    ("gh-repo-settings", re.compile(r"\bgh\s+(?:repo\s+(?:delete|edit|rename|archive)|release\s+(?:create|delete|edit))\b"),
     "저장소·릴리스 설정 변경"),
    ("gh-api-write", re.compile(r"\bgh\s+api\b[^|;&]*(?:-X|--method)\s*(?:DELETE|PUT|PATCH)\b", I), "GitHub API 쓰기 요청"),
    # --- 데이터베이스
    ("db-write", re.compile(r"\b(?:mysql|mariadb|mysqlsh|psql)\b[^|;&]*\b(?:update\s+\w|delete\s+from|drop\s|alter\s|"
                r"truncate\s|insert\s+into|replace\s+into|create\s|grant\s|rename\s+table)", I),
     "DB 쓰기 SQL — 운영 DB는 조회만, 쓰기는 JD가 SQL을 승인한 경우만"),
    ("sql-file", re.compile(r"\b(?:mysql|mariadb|psql)\b[^|;&]*\s<\s*\S+"), "SQL 파일 실행 — 내용에 쓰기 문이 있을 수 있습니다"),
    ("liquibase", re.compile(r"\bliquibase\b[^|;&]*\s(?:update|rollback|drop-?all|clear-?check-?sums|changelog-sync)\b", I),
     "Liquibase 직접 실행"),
    ("liquibase-gradle", re.compile(r"\bgradlew\b[^|;&]*\s(?:update|dropAll|clearChecksums|rollback\w*)\b"), "Liquibase Gradle 태스크 실행"),
    # --- 인프라·원격
    ("aws-write", re.compile(r"\baws\s+(?:[\w-]+\s+)?(?:delete|terminate|stop|put|update|create|modify|remove|reboot|"
                r"restore|revoke|authorize|attach|detach|run-instances|send-command)[\w-]*"),
     "AWS 리소스 변경"),
    ("s3-write", re.compile(r"\baws\s+s3\s+(?:rm|mv|sync)\b|\baws\s+s3\s+cp\b[^|;&]*\ss3://\S+\s*$"), "S3 쓰기·삭제"),
    ("terraform", re.compile(r"\bterraform\s+(?:apply|destroy|import|state\s+rm)\b"), "Terraform 인프라 변경"),
    ("kubectl", re.compile(r"\bkubectl\s+(?:delete|apply|scale|edit|patch)\b"), "Kubernetes 변경"),
    ("docker-volume", re.compile(r"\bdocker\s+(?:compose\s+down\b[^|;&]*\s-v\b|system\s+prune|volume\s+(?:rm|prune))"),
     "Docker 볼륨·데이터 삭제"),
    ("publish", re.compile(r"\bdocker\s+push\b|\bnpm\s+publish\b"), "이미지·패키지 게시"),
    ("remote-shell", re.compile(r"(?:^|[\s;&|(])(?:ssh|scp)\s"), "원격 서버 접속 — 운영 서버일 수 있습니다"),
    # --- 로컬 파괴·권한
    ("rm-rf", re.compile(r"\brm\s+(?:-[a-zA-Z]*r[a-zA-Z]*f|-[a-zA-Z]*f[a-zA-Z]*r|-r\s+-f|-f\s+-r|--recursive\s+--force)\b"),
     "rm -rf — 복구할 수 없는 삭제"),
    ("sudo", re.compile(r"(?:^|[\s;&|(])sudo\s"), "sudo — 관리자 권한 실행"),
    ("curl-pipe-sh", re.compile(r"\b(?:curl|wget)\b[^|;&]*\|\s*(?:sudo\s+)?(?:sh|bash|zsh)\b"), "원격 스크립트 바로 실행"),
    # --- 보호 파일 우회 (편집 도구는 guard_edit이 막는다)
    ("claude-settings-write", re.compile(r"(?:>|>>|\btee\b|\bsed\s+-i\b|\bcp\b|\bmv\b)[^|;&]*\.claude/settings(?:\.local)?\.json"),
     "Claude 권한·hook 설정 변경"),
]

_PUSH_RE = re.compile(r"\bgit\b(?P<pre>[^|;&]*?)\spush\b(?P<args>[^|;&]*)")
_PROTECTED_REF_RE = re.compile(r"(?:^|[\s:/+])(?:main|master|release/\S+)(?:\s|$)")
_PR_CREATE_RE = re.compile(r"\bgh\s+pr\s+create\b")


def push_to_protected(command: str, root: Path | None) -> str | None:
    for m in _PUSH_RE.finditer(command):
        args = m.group("args")
        if _PROTECTED_REF_RE.search(args):
            return "보호 브랜치(main·release/*)로 push — 운영 배포로 이어질 수 있습니다"
        positional = [a for a in args.split() if not a.startswith("-")]
        if len(positional) <= 1 and root is not None:
            branch = c.current_branch(root)
            if c.PROTECTED_BRANCH_RE.match(branch):
                return f"현재 브랜치 `{branch}`를 push — 보호 브랜치입니다"
    return None


_WRITE_OP_RE = re.compile(r"(?:>|\btee\b|\bsed\s+-i\b|\bcp\b|\bmv\b|\btruncate\b)")
_ENV_TOKEN_RE = re.compile(r"(?:^|[\s/'\"=])(\.env(?:\.[\w.-]+)?)(?=$|[\s'\";|&)])")
_ENV_EXAMPLE_RE = re.compile(r"example|sample|template|defaults|dist")


def writes_env_file(command: str) -> bool:
    """.env 계열 파일을 쓰는 명령인가. 예시 파일(.env.example 등)만 다루면 해당 없음."""
    if not _WRITE_OP_RE.search(command):
        return False
    return any(not _ENV_EXAMPLE_RE.search(m.group(1)) for m in _ENV_TOKEN_RE.finditer(command))


def risky_rules(command: str, root: Path | None) -> list[tuple[str, str]]:
    """(규칙 ID, 사유) 목록. 걸린 규칙이 없으면 빈 목록."""
    found = [(rule_id, reason) for rule_id, pattern, reason in RULES if pattern.search(command)]
    if writes_env_file(command):
        found.append(("env-write", ".env 파일 쓰기 — 비밀값 파일"))
    protected = push_to_protected(command, root)
    if protected:
        found.insert(0, ("push-protected", protected))
    return list(dict.fromkeys(found))


def risky_reasons(command: str, root: Path | None) -> list[str]:
    return [reason for _, reason in risky_rules(command, root)]


# ---------------------------------------------------------------- gh pr create 게이트

def _pr_args(command: str) -> dict:
    segment = command[_PR_CREATE_RE.search(command).end():]
    segment = re.split(r"(?:&&|\|\||;|\|)", segment, maxsplit=1)[0]
    try:
        tokens = shlex.split(segment)
    except ValueError:
        tokens = segment.split()
    args: dict = {"body": None, "body_file": None, "base": None, "fill": False}
    it = iter(range(len(tokens)))
    for i in it:
        tok = tokens[i]
        key, _, inline = tok.partition("=")
        nxt = inline if inline else (tokens[i + 1] if i + 1 < len(tokens) else None)
        consumed = not inline
        if key in ("--body", "-b"):
            args["body"] = nxt
        elif key in ("--body-file", "-F"):
            args["body_file"] = nxt
        elif key in ("--base", "-B"):
            args["base"] = nxt
        elif key in ("--fill", "--fill-first", "--fill-verbose", "-f"):
            args["fill"] = True
            continue
        else:
            continue
        if consumed:
            next(it, None)
    return args


def _load_change_record():
    spec = importlib.util.spec_from_file_location("change_record", CHANGE_RECORD)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def _run_audit(root: Path, body_path: str | None) -> list[str]:
    if not AUDIT.is_file() or c.base_ref(root) is None:
        return []
    cmd = ["python3", str(AUDIT), "--repo", str(root), "--base", c.base_ref(root), "--working-tree", "--json"]
    if body_path:
        cmd += ["--pr-body", body_path]
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
        report = json.loads(done.stdout)
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return ["테스트 점검(gardenstep-test-audit)을 실행하지 못했습니다 — 직접 실행해 결과를 확인하세요"]
    if report.get("verdict") != "FAIL":
        return []
    problems = [f"테스트 규칙 `{r['id']}`: {r['title']}" for r in report.get("rules", [])
                if r.get("level") == "FAIL" and not r.get("satisfied")]
    problems += [f"테스트 스멜 `{s['rule']}` {s['file']}:{s['line']}" for s in report.get("smells", [])
                 if s.get("level") == "FAIL"][:5]
    problems += [f"PR 본문: {p.get('message', p)}" for p in report.get("pr_body", [])
                 if isinstance(p, dict) and p.get("level") == "FAIL"]
    return problems or ["테스트 점검 판정 FAIL — gardenstep-test-audit 결과를 확인하세요"]


def pr_gate(command: str, root: Path) -> list[str]:
    problems: list[str] = []
    args = _pr_args(command)
    if args["base"] and c.PROTECTED_BRANCH_RE.match(args["base"]):
        problems.append(f"PR 대상이 `{args['base']}` — 기능 PR의 대상은 `dev`입니다")

    body = args["body"]
    if body is None and args["body_file"] and args["body_file"] != "-":
        path = Path(args["body_file"])
        path = path if path.is_absolute() else root / path
        body = path.read_text(encoding="utf-8") if path.is_file() else None

    cr = _load_change_record()
    if body is None:
        problems.append("PR 본문을 확인할 수 없습니다 — `--body-file`로 `## 검증`이 있는 본문을 넘기세요 (/ship-pr)")
    elif cr.receipt_section(body) is None:
        problems.append("PR 본문에 `## 검증` 섹션이 없습니다")

    branch = c.current_branch(root)
    problems += [f"변경기록: {p}" for p in cr.check_record(root, branch)]

    body_path = None
    if body is not None:
        tmp = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8")
        tmp.write(body)
        tmp.close()
        body_path = tmp.name
    try:
        problems += _run_audit(root, body_path)
    finally:
        if body_path:
            Path(body_path).unlink(missing_ok=True)
    return problems


def decide(command: str, cwd: str) -> dict | None:
    root = c.repo_root(cwd) if cwd else None
    rules = risky_rules(command, root)
    reasons = [reason for _, reason in rules]
    gate: list[str] = []
    if _PR_CREATE_RE.search(command) and root is not None and c.is_team_repo(root):
        gate = pr_gate(command, root)
    if not reasons and not gate:
        return None
    c.log_decision("guard_bash", "ask", [rule_id for rule_id, _ in rules] + (["pr-gate"] if gate else []), root)
    lines = []
    if reasons:
        lines.append("[gardenstep-team] 확인이 필요한 명령입니다:")
        lines += [f"- {r}" for r in reasons]
    if gate:
        lines.append("[gardenstep-team] PR을 열기 전에 준비되지 않은 항목:")
        lines += [f"- {p}" for p in gate]
        lines.append("→ /ship-pr 절차로 채운 뒤 다시 시도하는 것을 권장합니다.")
    text = "\n".join(lines)
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": text,
            "additionalContext": text,
        }
    }


def main() -> int:
    data = c.read_input()
    command = (data.get("tool_input") or {}).get("command") or ""
    if not command.strip():
        return 0
    try:
        result = decide(command, data.get("cwd") or "")
    except Exception:  # hook 오류로 작업을 막지 않는다
        return 0
    if result:
        c.emit(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
