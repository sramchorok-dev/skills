#!/usr/bin/env python3
"""PR마다 한 파일짜리 변경기록(docs/changes/YYYY/YYYY-MM-DD-<branch>.md)을 만들고 검사한다.

  new     이 브랜치의 기록을 만든다(이미 있으면 경로만 출력)
  check   기록이 있는지, '왜'가 채워졌는지, 마이그레이션이면 rollback이 적혔는지 검사 (CI·PR 게이트)
  find    이 브랜치의 기록 경로 출력
  set-pr  frontmatter의 pr 값을 채운다
  new-adr 다음 번호의 ADR 초안을 만든다(docs/adr 또는 docs/decisions)

`check`는 ADR 규칙도 함께 본다: 새 ADR이 기준(둘 이상)·형식·분량을 지키는지, 기존 ADR을 몰래 고치지 않았는지,
기록의 `adr:`와 PR이 추가한 ADR이 서로 가리키는지. 규칙 정본은 skills 저장소 docs/adr/README.md.

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

ADR_DIRS = ("docs/adr", "docs/decisions")
ADR_TEMPLATE = Path(__file__).resolve().parents[1] / "assets" / "adr.md"
ADR_MAX_LINES = 80  # "한 페이지를 넘기지 않는다"
ADR_CRITERIA = {"되돌리기": "되돌리기 비쌈", "영향": "넓은 영향", "대안": "대안 검토"}
ADR_STATUS_NEW = {"proposed", "accepted"}
RISKY_WITHOUT_ADR = {"migration", "infra", "security"}
WHY_MIN_CHARS = 10
WHY_FILLER = {"개선", "리팩터링", "리팩토링", "정리", "없음", "버그수정", "기능추가", "요청", "필요", "n/a", "tbd", "todo"}

_ADR_PATH_RE = re.compile(r"^(docs/(?:adr|decisions))/(\d{4})-(?!\d{2}-\d{2}-)[^/]+\.md$")
_ADR_DIR_FILE_RE = re.compile(r"^docs/(?:adr|decisions)/[^/]+\.md$")
_ADR_HEADER_RE = re.compile(r"(?m)^- (상태|날짜|결정|기준):[ \t]*(.*)$")
_ADR_STATUS_LINE_RE = re.compile(r"^[-+]- 상태:")
_ADR_STATUS_OK_RE = re.compile(r"proposed|accepted|deprecated|superseded by (\d{4})")
_RAW = ("-c", "core.quotepath=off")  # 한글 파일명을 이스케이프하지 않고 받는다
_EVIDENCE_RE = re.compile(r"#\d+|https?://")


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
    why = section(body, r"^왜")
    if not has_content(why):
        problems.append("`## 왜`가 비어 있습니다 — 사용자·이슈에서 받은 이유를 적습니다(추측 금지)")
    else:
        flat = re.sub(r"\s+", "", " ".join(l.strip().lstrip("-*").strip() for l in why.split("\n")))
        if not _EVIDENCE_RE.search(flat) and (len(flat) < WHY_MIN_CHARS or flat.lower().rstrip(".") in WHY_FILLER):
            problems.append(f"`## 왜`가 너무 짧거나 형식적입니다 — 누가 어떤 상황에서 요청했는지, 또는 이슈 링크를 적습니다 "
                            f"({WHY_MIN_CHARS}자 이상)")
    return problems


def review(root: Path, branch: str, base: str | None = None) -> tuple[list[str], list[str]]:
    """(problems, warnings) — 변경기록 검사와 ADR 규칙 검사."""
    record = find_record(root, branch)
    if record is None:
        return [f"`docs/changes/**/*-{branch_slug(branch) or '<branch>'}.md` 기록이 없습니다"], []
    base = base or next((r for r in ("origin/dev", "origin/main") if _git(root, "rev-parse", "--verify", "--quiet", r)), None)
    touched = any(_MIGRATION_PATH_RE.search(f) for f in changed_files(root, base))
    rel = record.relative_to(root).as_posix()
    text = record.read_text(encoding="utf-8")
    problems = [f"{rel}: {p}" for p in validate_text(text, touched)]
    adr_problems, warnings = review_adr(root, base, parse(text)[0], touched)
    return problems + adr_problems, warnings


def check_record(root: Path, branch: str, base: str | None = None) -> list[str]:
    return review(root, branch, base)[0]


# ---------------------------------------------------------------- ADR 규칙

def adr_header(text: str) -> dict[str, str]:
    return {k: v.strip() for k, v in _ADR_HEADER_RE.findall(text)}


def _table_has_row(text: str | None) -> bool:
    """헤더·구분선을 뺀 표 행 중 앞 두 칸이 채워진 행이 있는가."""
    rows = [l.strip() for l in (text or "").split("\n") if l.strip().startswith("|")]
    for row in rows[2:]:
        cells = [c.strip() for c in row.strip("|").split("|")]
        if len(cells) >= 2 and all(c and not _PLACEHOLDER_RE.match(c) for c in cells[:2]):
            return True
    return False


def validate_adr(text: str, number: str | None = None) -> list[str]:
    """새로 추가한 ADR이 README의 규칙을 지키는지. 기존(옛 형식) ADR에는 적용하지 않는다."""
    problems: list[str] = []
    head = adr_header(text)
    body = _COMMENT_RE.sub("", text)
    title = re.search(r"(?m)^#\s+(\d{4})\.\s+\S", body)
    if not title:
        problems.append("첫 제목은 `# NNNN. 결정을 한 문장으로` 형식이어야 합니다")
    elif number and title.group(1) != number:
        problems.append(f"제목 번호 {title.group(1)}가 파일명 번호 {number}와 다릅니다")
    if head.get("상태") not in ADR_STATUS_NEW:
        problems.append("`- 상태:`는 새 ADR에서 proposed 또는 accepted 여야 합니다")
    try:
        dt.date.fromisoformat(head.get("날짜", ""))
    except ValueError:
        problems.append("`- 날짜:`는 YYYY-MM-DD 여야 합니다")
    if not head.get("결정") or _PLACEHOLDER_RE.match(head["결정"]):
        problems.append("`- 결정:`에 결정한 사람을 적습니다")
    criteria = "" if _PLACEHOLDER_RE.match(head.get("기준", "")) else head.get("기준", "")
    met = {k for k in ADR_CRITERIA if k in criteria}
    if len(met) < 2:
        problems.append("`- 기준:`에 충족한 기준을 둘 이상 적습니다 "
                        "(" + " · ".join(ADR_CRITERIA.values()) + ") — 하나뿐이면 ADR이 아니라 변경기록 `## 왜`로 충분합니다")
    for name in ("맥락", "결정", "결과"):
        if not has_content(section(body, rf"^{name}")):
            problems.append(f"`## {name}`이 비어 있습니다")
    if not _table_has_row(section(body, r"^검토한\s*대안")):
        problems.append("`## 검토한 대안` 표에 버린 대안과 이유를 한 행 이상 적습니다")
    again = re.search(r"다시 볼 조건\s*:\s*(\S.*)", section(body, r"^결과") or "")
    if not again or _PLACEHOLDER_RE.match(again.group(1).strip()):
        problems.append("`## 결과`에 `- 다시 볼 조건:`을 적습니다 — 언제 이 결정을 다시 열지")
    lines = sum(1 for l in body.split("\n") if l.strip())
    if lines > ADR_MAX_LINES:
        problems.append(f"ADR이 {lines}줄입니다 — 한 페이지({ADR_MAX_LINES}줄)를 넘기지 않습니다")
    return problems


def _adr_numbers(root: Path, directory: str, exclude: set[str]) -> list[int]:
    nums = []
    for f in (root / directory).glob("[0-9][0-9][0-9][0-9]-*.md"):
        rel = f.relative_to(root).as_posix()
        if rel not in exclude and not f.name.startswith("0000-"):
            nums.append(int(f.name[:4]))
    return nums


def _is_adr_candidate(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return bool(_ADR_DIR_FILE_RE.match(path)) and not name.startswith(("0000-", "README"))


def adr_changes(root: Path, base: str | None) -> tuple[list[str], list[str], str | None]:
    """(추가된 ADR, 수정된 ADR, merge-base). 로컬 작업 트리·untracked 포함."""
    mb = _git(root, "merge-base", base, "HEAD") if base else None
    added: set[str] = set()
    modified: set[str] = set()
    for line in (_git(root, *_RAW, "diff", "--name-status", "--no-renames", mb or "HEAD") or "").splitlines():
        status, _, path = line.partition("\t")
        if _is_adr_candidate(path):
            (added if status == "A" else modified if status == "M" else set()).add(path)
    for path in (_git(root, *_RAW, "ls-files", "--others", "--exclude-standard") or "").splitlines():
        if _is_adr_candidate(path):
            added.add(path)
    return sorted(added), sorted(modified), mb


def _adr_edit_problems(root: Path, path: str, mb: str | None) -> list[str]:
    """채택된 ADR은 상태 줄만 바꿀 수 있다. 결정이 바뀌면 새 ADR을 쓰고 옛 ADR을 superseded로 표시한다."""
    diff = _git(root, *_RAW, "diff", "-U0", "--no-renames", mb or "HEAD", "--", path) or ""
    changed = [l for l in diff.splitlines()
               if l[:1] in "+-" and not l.startswith(("+++", "---")) and l[1:].strip()]
    if any(not _ADR_STATUS_LINE_RE.match(l) for l in changed):
        return [f"{path}: 이미 있는 ADR의 본문을 고쳤습니다 — 결정이 바뀌었다면 새 ADR을 쓰고 이 ADR의 `- 상태:`만 "
                f"`superseded by NNNN`으로 바꿉니다 (오타 수정은 JD 확인 후)"]
    status = adr_header((root / path).read_text(encoding="utf-8")).get("상태", "")
    m = _ADR_STATUS_OK_RE.fullmatch(status)
    if not m:
        return [f"{path}: `- 상태:` 값 `{status}`는 proposed | accepted | deprecated | superseded by NNNN 이어야 합니다"]
    if m.group(1) and not list((root / path).parent.glob(f"{m.group(1)}-*.md")):
        return [f"{path}: superseded by {m.group(1)} — 그 번호의 ADR이 같은 디렉터리에 없습니다"]
    return []


def review_adr(root: Path, base: str | None, meta: dict[str, str], touched_migration: bool = False) -> tuple[list[str], list[str]]:
    """(problems, warnings). meta는 이 PR 변경기록의 frontmatter."""
    added, modified, mb = adr_changes(root, base)
    problems: list[str] = []
    warnings: list[str] = []
    for path in [p for p in added if not _ADR_PATH_RE.match(p)]:
        problems.append(f"{path}: ADR 파일명은 `NNNN-짧은-제목.md` 입니다 (날짜 이름 금지) — "
                        f"`change_record.py new-adr --title \"…\"`로 만듭니다")
    added = [p for p in added if _ADR_PATH_RE.match(p)]
    for path in [p for p in modified if not _ADR_PATH_RE.match(p)]:
        problems.append(f"{path}: 번호 없는 옛 결정 문서를 고쳤습니다 — 바뀐 결정이면 새 ADR을 씁니다")
    modified = [p for p in modified if _ADR_PATH_RE.match(p)]
    for path in modified:
        problems += _adr_edit_problems(root, path, mb)

    by_dir: dict[str, list[str]] = {}
    for path in added:
        by_dir.setdefault(_ADR_PATH_RE.match(path).group(1), []).append(path)
    for directory, paths in by_dir.items():
        expect = max(_adr_numbers(root, directory, set(paths)), default=0) + 1
        for offset, path in enumerate(sorted(paths)):
            number = _ADR_PATH_RE.match(path).group(2)
            if int(number) != expect + offset:
                problems.append(f"{path}: 번호는 다음 순번 {expect + offset:04d} 이어야 합니다 "
                                f"(다른 PR이 먼저 머지됐다면 번호를 바꿔 다시 올립니다)")
            problems += [f"{path}: {p}" for p in validate_adr((root / path).read_text(encoding="utf-8"), number)]
    if len(added) > 1:
        warnings.append(f"이 PR이 ADR을 {len(added)}개 추가합니다 — 정말 각각이 독립된 결정인가요?")

    adr = meta.get("adr", "none")
    if adr == "" or adr.split("(")[0].strip() == "none":
        judged = "(" in adr and adr.rstrip().endswith(")")  # `none (기준 1개: …)` — 판정을 남겼다
        if added:
            problems.append(f"PR이 ADR({added[0]})을 추가했으니 변경기록 `adr:`에 그 경로를 적습니다")
        elif not judged and (meta.get("risk") in RISKY_WITHOUT_ADR or touched_migration):
            warnings.append("위험도가 높은 변경인데 `adr: none`입니다 — ADR 기준(되돌리기 비쌈 · 넓은 영향 · 대안 검토) 중 "
                            "둘 이상이면 ADR을 씁니다. 아니면 판정을 기록에 남기면 경고가 사라집니다: "
                            "`adr: none (기준 1개: 스키마 변경뿐, 다른 레포 영향·검토한 대안 없음)`")
    elif not (root / adr).is_file():
        problems.append(f"변경기록 `adr: {adr}` 파일이 없습니다")
    elif added and adr not in added:
        problems.append(f"PR이 추가한 ADR({added[0]})과 변경기록 `adr: {adr}`가 다릅니다")
    return problems, warnings


# ---------------------------------------------------------------- 생성

def new_record(root: Path, branch: str, change_type: str, title: str, today: dt.date | None = None,
               touched_migration: bool = False) -> Path:
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
    if touched_migration:  # Liquibase/migration 변경 → 이미지 롤백 불가, 기본값을 미리 맞춰 둔다
        text = re.sub(r"(?m)^risk: normal", "risk: migration", text, count=1)
        text = re.sub(r"(?m)^rollback: image", "rollback: rds-snapshot", text, count=1)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def adr_slug(title: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]+", "-", title.lower()).strip("-")[:60] or "decision"


def new_adr(root: Path, title: str, today: dt.date | None = None) -> Path:
    directory = next((d for d in ADR_DIRS if (root / d).is_dir()), "docs/decisions")
    number = max(_adr_numbers(root, directory, set()), default=0) + 1
    today = today or dt.date.today()
    path = root / directory / f"{number:04d}-{adr_slug(title)}.md"
    text = ADR_TEMPLATE.read_text(encoding="utf-8")
    text = (text.replace("{{number}}", f"{number:04d}").replace("{{date}}", today.isoformat())
                .replace("{{title}}", title or "<결정을 한 문장으로>"))
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
    parser.add_argument("command", choices=["new", "check", "find", "set-pr", "new-adr"])
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
        base = args.base or next((r for r in ("origin/dev", "origin/main", "dev", "main")
                                  if _git(root, "rev-parse", "--verify", "--quiet", r)), None)
        touched = any(_MIGRATION_PATH_RE.search(f) for f in changed_files(root, base))
        existed = find_record(root, branch) is not None
        path = new_record(root, branch, args.type, args.title, touched_migration=touched).relative_to(root)
        print(path)
        if not existed:
            print("다음: ① `무엇이 바뀌었나`는 동작 중심으로 ② `왜`는 사용자·이슈에서 받은 이유만(모르면 묻는다) "
                  "③ `tests`·`확인한 것`은 실제로 돌린 것만 ④ `adr:`는 `none (판정 한 줄)` 또는 ADR 경로 ⑤ check로 확인"
                  + (" — 마이그레이션 변경을 감지해 risk/rollback을 미리 채웠으니 맞는지 확인" if touched else ""),
                  file=sys.stderr)
        return 0
    if args.command == "new-adr":
        if not args.title:
            print("--title이 필요합니다", file=sys.stderr)
            return 1
        path = new_adr(root, args.title).relative_to(root)
        print(path)
        print(f"다음: ① 헤더 `결정`·`기준`과 각 섹션을 채운다(결정자·기준·대안은 사람에게 확인) "
              f"② 변경기록 `adr:`에 {path}를 적는다 ③ check로 확인", file=sys.stderr)
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

    problems, warnings = review(root, branch, args.base)
    if problems:
        print("❌ 변경기록·ADR 검사 실패")
        for problem in problems:
            print(f"- {problem}")
    else:
        print(f"✅ 변경기록 확인: {find_record(root, branch).relative_to(root)}")
    for warning in warnings:
        print(f"⚠️ {warning}")
    if problems:
        print("작성법: https://github.com/sramchorok-dev/skills/blob/main/docs/team-agent-guide.md#변경기록")
        if any(k in " ".join(problems) for k in ("ADR", "adr:")):
            print("ADR 규칙: https://github.com/sramchorok-dev/skills/blob/main/docs/adr/README.md "
                  "(기준·결정자·대안은 사람에게 확인한다. 검사를 통과시키려고 지어내 채우지 않는다)")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
