#!/usr/bin/env python3
"""Print one checklist card per TC from the Tier2 QA sheet.

Examples:
  python3 tc_cards.py qa-sheet.xlsx --ids A-01,A-02
  python3 tc_cards.py qa-sheet.xlsx --area P --priority P0
  python3 tc_cards.py qa-sheet.xlsx --issue R52
  python3 tc_cards.py tc.csv --ids G-03          # CSV of the '01 TC정의' tab
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from qa_sheet import AUTOMATION_TAB, ISSUE_TAB, TC_TAB, load_tab  # noqa: E402

STEP_RE = re.compile(r"(?:^|\s)(\d{1,2})\.\s+")


def split_steps(text: str) -> list[str]:
    """'1. 접속 2. 메뉴 읽기' -> ['접속', '메뉴 읽기']. Text without numbers stays one step."""
    parts = STEP_RE.split(text.strip())
    if len(parts) < 3:
        return [text.strip()] if text.strip() else []
    steps = []
    for i in range(1, len(parts) - 1, 2):
        body = parts[i + 1].strip()
        if body:
            steps.append(body)
    return steps


OPEN_QUOTES = "“‘\"'「"
CLOSE_FOR = {"“": "”", "‘": "’", '"': '"', "'": "'", "「": "」"}
STEP_CHECK_RE = re.compile(r"(?:^|\s)(\d{1,2}):\s+")


def _sentences(line: str) -> list[str]:
    """Split on '.' / '。' followed by a space, but never inside quotes (UI copy often has periods)."""
    parts, current, closing = [], [], None
    for index, char in enumerate(line):
        current.append(char)
        if closing:
            if char == closing:
                closing = None
            continue
        if char in OPEN_QUOTES:
            closing = CLOSE_FOR[char]
            continue
        nxt = line[index + 1] if index + 1 < len(line) else ""
        if char in ".。" and nxt.isspace():
            parts.append("".join(current).strip())
            current = []
    tail = "".join(current).strip()
    if tail:
        parts.append(tail)
    return [part for part in parts if part]


def split_checks(text: str) -> list[str]:
    """Split acceptance criteria into separately verifiable checks.

    Criteria keyed by procedure step ('3: 미리보기만. 4: "…"') become one check per step. Otherwise
    split on line breaks and sentence ends outside quotes.
    """
    text = text.strip()
    if len(STEP_CHECK_RE.findall(text)) >= 2:
        parts = STEP_CHECK_RE.split(text)
        checks = [parts[0].strip()] if parts[0].strip() else []
        for i in range(1, len(parts) - 1, 2):
            body = parts[i + 1].strip()
            if body:
                checks.append(f"절차 {parts[i]}: {body}")
        return checks
    checks = []
    for line in text.splitlines():
        line = line.strip().lstrip("•-·").strip()
        if line:
            checks.extend(_sentences(line))
    return checks


def select(tcs: list[dict[str, str]], ids: set[str], area: str | None, priority: str | None,
           issue: str | None) -> list[dict[str, str]]:
    chosen = []
    for tc in tcs:
        tc_id = tc.get("ID", "")
        if not re.match(r"^[A-Z]-\d", tc_id):
            continue
        if ids and tc_id not in ids:
            continue
        if area and not tc_id.startswith(f"{area}-"):
            continue
        if priority and tc.get("우선순위") != priority:
            continue
        if issue and issue not in re.split(r"[\s,;/]+", tc.get("연결 이슈", "")):
            continue
        chosen.append(tc)
    return chosen


def issue_ids_for(tc: dict[str, str], issues: dict[str, dict[str, str]]) -> list[str]:
    linked = [part for part in re.split(r"[\s,;/]+", tc.get("연결 이슈", "")) if part]
    return [issue_id for issue_id in linked if issue_id in issues]


def card(tc: dict[str, str], issues: dict[str, dict[str, str]], automation: dict[str, dict[str, str]]) -> str:
    tc_id = tc.get("ID", "")
    lines = [
        f"## {tc_id} · {tc.get('우선순위', '')} · v{tc.get('TC 버전', '?')}",
        f"- 의도: {tc.get('테스트 의도', '')}",
        f"- 화면: {tc.get('화면', '')}",
        f"- 준비 데이터: {tc.get('준비 데이터', '') or '-'}",
        f"- 선행조건: {tc.get('선행조건', '') or '-'}",
        "",
        "절차:",
    ]
    for number, step in enumerate(split_steps(tc.get("절차", "")), 1):
        lines.append(f"  {number}. {step}")
    lines += ["", "합격 기준 (항목마다 일치/불일치/확인불가 + 증거):"]
    for number, check in enumerate(split_checks(tc.get("합격 기준", "")), 1):
        lines.append(f"  [C{number}] {check}")
    lines += ["", f"합격 기준 원문: {tc.get('합격 기준', '')}"]
    note = tc.get("현재 사전판정", "")
    if note:
        lines.append(f"사전판정 메모(참고만, 결과로 옮기지 않음): {note}")
    for issue_id in issue_ids_for(tc, issues):
        issue = issues[issue_id]
        summary = (issue.get("현상", "").splitlines() or [""])[0][:160]
        lines.append(f"연결 이슈 {issue_id} [{issue.get('상태', '')}]: {summary} (상세는 04 탭)")
    mapping = automation.get(tc_id)
    if mapping:
        lines.append(f"자동화({mapping.get('검증 계층', '')}) 있음 — 자동화 통과는 DEV 실행 결과가 아니다")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("sheet", type=Path, help="QA 시트 xlsx 또는 '01 TC정의' CSV")
    parser.add_argument("--ids", default="", help="쉼표로 구분한 TC ID (예: A-01,A-02)")
    parser.add_argument("--area", help="영역 글자 (예: P → P-xx 전체)")
    parser.add_argument("--priority", help="P0 / P1 / P2")
    parser.add_argument("--issue", help="연결 이슈 ID (예: R52)")
    parser.add_argument("--list", action="store_true", help="카드 대신 ID·의도 한 줄 목록만")
    args = parser.parse_args(argv)

    try:
        tcs = load_tab(args.sheet, TC_TAB)
    except (KeyError, OSError) as error:
        print(f"시트를 읽지 못했습니다: {error}", file=sys.stderr)
        return 2
    issues: dict[str, dict[str, str]] = {}
    automation: dict[str, dict[str, str]] = {}
    if args.sheet.suffix.lower() != ".csv":
        for tab, target, key in ((ISSUE_TAB, issues, "이슈 ID"), (AUTOMATION_TAB, automation, "TC ID")):
            try:
                target.update({row[key]: row for row in load_tab(args.sheet, tab) if row.get(key)})
            except KeyError:
                pass

    ids = {part.strip() for part in args.ids.split(",") if part.strip()}
    chosen = select(tcs, ids, args.area, args.priority, args.issue)
    missing = sorted(ids - {tc["ID"] for tc in chosen})
    if missing:
        print(f"시트에 없는 TC ID: {', '.join(missing)}", file=sys.stderr)
    if not chosen:
        print("조건에 맞는 TC가 없습니다.", file=sys.stderr)
        return 1
    if args.list:
        for tc in chosen:
            print(f"{tc['ID']}\t{tc.get('우선순위', '')}\t{tc.get('테스트 의도', '')}")
        return 0
    print(f"# TC 카드 {len(chosen)}개\n")
    print("\n\n".join(card(tc, issues, automation) for tc in chosen))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
