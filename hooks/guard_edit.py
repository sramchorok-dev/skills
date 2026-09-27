#!/usr/bin/env python3
"""PreToolUse(Edit|Write|MultiEdit|NotebookEdit) 가드.

팀 정책(docs/adr/0002): 편집 도구는 아래 파일에 한해 **차단(deny)** 한다. 사유는 에이전트에게 전달되어
대안(새 changeset 추가, 사용자에게 값 입력 안내 등)을 찾게 한다.

- 비밀값: `.env`(예시 파일 제외), 키·인증서, `application-prod*`
- 권한 설정: `.claude/settings*.json`
- git 내부: `.git/`
- Liquibase: 이미 기준 브랜치(dev)에 들어간 changeset — checksum이 바뀌면 배포가 멈춘다
"""
from __future__ import annotations

import re
from pathlib import Path

import _common as c

_ENV_RE = re.compile(r"^\.env(?:\..+)?$")
_ENV_EXAMPLE_RE = re.compile(r"\.(?:example|sample|template|defaults|dist)$")
_KEY_RE = re.compile(r"(?:\.(?:pem|key|p12|pfx|jks|keystore)$|^id_(?:rsa|ed25519|ecdsa)(?:\.pub)?$)")
_PROD_CONFIG_RE = re.compile(r"^application-prod[\w-]*\.(?:ya?ml|properties)$")
_CLAUDE_SETTINGS_RE = re.compile(r"(?:^|/)\.claude/settings(?:\.local)?\.json$")
_CHANGESET_RE = re.compile(r"(?:^|/)db/changelog/(?:.+/)?(?:changes|baseline)/[^/]+\.(?:ya?ml|xml|sql|json)$")


def protected_reason(path: Path) -> str | None:
    name = path.name
    posix = path.as_posix()
    if _ENV_RE.match(name) and not _ENV_EXAMPLE_RE.search(name):
        return f"`{name}`는 비밀값 파일이라 에이전트가 편집하지 않습니다. 필요한 키 이름과 설정 방법을 사용자에게 안내하세요."
    if _KEY_RE.search(name):
        return f"`{name}`는 키·인증서 파일이라 편집할 수 없습니다."
    if _PROD_CONFIG_RE.match(name):
        return f"`{name}`는 운영 설정입니다. 변경이 필요하면 diff를 제안하고 JD의 확인을 받으세요."
    if _CLAUDE_SETTINGS_RE.search(posix):
        return "Claude 권한·hook 설정은 사람이 직접 수정합니다. 필요한 변경을 사용자에게 제안하세요."
    if "/.git/" in f"/{posix}":
        return "`.git/` 내부 파일은 편집하지 않습니다. git 명령을 사용하세요."
    return None


def applied_changeset_reason(path: Path, cwd: str) -> str | None:
    if not _CHANGESET_RE.search(path.as_posix()):
        return None
    root = c.repo_root(path.parent if path.parent.exists() else cwd)
    if root is None:
        return None
    try:
        rel = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None
    base = c.merge_base(root)
    if not base or c.git(root, "cat-file", "-e", f"{base}:{rel}") is None:
        return None  # 이 브랜치에서 새로 만든 changeset은 수정해도 된다
    return (f"`{rel}`는 이미 `{c.base_ref(root)}`에 들어간 Liquibase changeset입니다. 적용된 changeset을 고치면 "
            "checksum 불일치로 배포가 멈춥니다. 수정 대신 새 changeset 파일을 추가하세요.")


def decide(tool_input: dict, cwd: str) -> dict | None:
    raw = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute() and cwd:
        path = Path(cwd) / path
    reason = protected_reason(path) or applied_changeset_reason(path, cwd)
    if not reason:
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": f"[gardenstep-team] {reason}",
        }
    }


def main() -> int:
    data = c.read_input()
    try:
        result = decide(data.get("tool_input") or {}, data.get("cwd") or "")
    except Exception:
        return 0
    if result:
        c.emit(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
