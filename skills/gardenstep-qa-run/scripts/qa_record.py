#!/usr/bin/env python3
"""Build '02 실행기록' rows for the Tier2 QA sheet and decide the verdict from per-check results.

The verdict is computed here, not typed by hand, so PASS can only come from checks that were all
observed as matching with evidence.

  python3 qa_record.py init --out run.tsv --run-id QA-20261010-01 --env "DEV FE 6a3cdca2, BE 297e3873, Admin 64242dd8" \
      --runner 유푸름 --tool "Claude+Playwright"
  python3 qa_record.py add --run run.tsv result.json      # result.json format: see references/result-json.md
  python3 qa_record.py summary --run run.tsv
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HEADER = ["Run ID", "TC ID", "TC 버전", "파라미터/뷰포트", "환경/FE·BE·Admin SHA", "실행자", "실행시각",
          "결과", "실제 결과", "증거 링크", "이슈 ID", "정리 결과"]
VERDICTS = ("PASS", "FAIL", "BLOCKED", "NOT_RUN", "N/A")
CHECK_STATUSES = ("일치", "불일치", "확인불가")
RUN_ID_RE = re.compile(r"^QA-\d{8}-\d{2}$")
TC_ID_RE = re.compile(r"^[A-Z]-\d{2}[a-z]?$")
KST = timezone(timedelta(hours=9))
SENSITIVE = [
    (re.compile(r"01[016789]-?\d{3,4}-?\d{4}"), "전화번호"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "이메일"),
    (re.compile(r"(?i)(token|password|비밀번호)\s*[=:]\s*\S+"), "토큰·비밀번호"),
    (re.compile(r"eyJ[\w-]{10,}\.[\w-]{10,}"), "JWT"),
]


class RecordError(ValueError):
    pass


def meta_path(run: Path) -> Path:
    return run.with_suffix(".meta.json")


def check_sensitive(text: str, where: str) -> None:
    for pattern, label in SENSITIVE:
        if pattern.search(text):
            raise RecordError(f"{where}에 {label}로 보이는 값이 있습니다. 가리고(예: 010-****-****) 다시 실행하세요.")


def decide(result: dict) -> tuple[str, str]:
    """Return (verdict, conclusion line). Raises RecordError when the result is inconsistent."""
    if result.get("na_reason"):
        if not result.get("na_decided_by"):
            raise RecordError("N/A는 사람이 정한 경우만 씁니다. na_decided_by(결정한 사람)를 적으세요.")
        return "N/A", f"[결론] 이번 회차 범위 아님 → N/A ({result['na_reason']}, 판단: {result['na_decided_by']})"
    if result.get("not_run_reason"):
        return "NOT_RUN", f"[결론] 실행하지 않음 → NOT_RUN ({result['not_run_reason']})"
    if result.get("preconditions_met") is False:
        reason = result.get("blocked_reason", "").strip()
        if not reason:
            raise RecordError("선행조건을 못 갖췄으면 blocked_reason에 무엇이 없었는지 적으세요.")
        return "BLOCKED", f"[결론] 선행조건 미충족 → BLOCKED: {reason}"

    checks = result.get("checks") or []
    if not checks:
        raise RecordError("checks가 비었습니다. 합격 기준 항목마다 한 줄씩 적으세요.")
    for check in checks:
        label = check.get("id") or check.get("criterion", "?")
        if check.get("status") not in CHECK_STATUSES:
            raise RecordError(f"{label}: status는 {', '.join(CHECK_STATUSES)} 중 하나여야 합니다.")
        if not str(check.get("observed", "")).strip():
            raise RecordError(f"{label}: observed에 실제로 본 내용을 적으세요(화면 문구·값 그대로).")
        if check["status"] != "확인불가" and not check.get("evidence"):
            raise RecordError(f"{label}: {check['status']} 판정에는 evidence(스크린샷·로그 경로)가 필요합니다.")

    failed = [c for c in checks if c["status"] == "불일치"]
    unknown = [c for c in checks if c["status"] == "확인불가"]
    issue = result.get("issue_id", "").strip()
    if failed:
        suffix = f" (이슈 {issue})" if issue else " (이슈 미등록 — 04 탭 초안 필요)"
        return "FAIL", f"[결론] 기준과 다름 → FAIL{suffix}"
    if unknown:
        names = ", ".join(c.get("id", "?") for c in unknown)
        return "BLOCKED", f"[결론] 확인하지 못한 항목 있음 → BLOCKED ({names})"
    return "PASS", "[결론] 기준과 일치 → PASS"


def actual_text(result: dict, conclusion: str) -> str:
    lines = [conclusion]
    for check in result.get("checks") or []:
        criterion = check.get("criterion", "")
        lines.append(f"• {check.get('id', '')} {criterion}({check['status']}): {check['observed']}".strip())
    if result.get("note"):
        lines.append(f"※ {result['note']}")
    return "\n".join(lines)


def evidence_text(result: dict) -> str:
    links: list[str] = []
    for check in result.get("checks") or []:
        evidence = check.get("evidence") or []
        for item in evidence if isinstance(evidence, list) else [evidence]:
            if item not in links:
                links.append(item)
    if result.get("evidence_folder"):
        links.insert(0, result["evidence_folder"])
    return "\n".join(links)


def build_row(meta: dict, result: dict, now: datetime | None = None) -> list[str]:
    tc_id = result.get("tc_id", "")
    if not TC_ID_RE.match(tc_id):
        raise RecordError(f"tc_id '{tc_id}' 형식이 아닙니다(예: A-01).")
    for key in ("tc_version", "viewport"):
        if not str(result.get(key, "")).strip():
            raise RecordError(f"{key}를 적으세요(TC 카드의 버전, 뷰포트·브라우저).")
    verdict, conclusion = decide(result)
    text = actual_text(result, conclusion)
    check_sensitive(text, "실제 결과")
    timestamp = (now or datetime.now(KST)).strftime("%H:%M:%S")
    viewport = result["viewport"]
    if meta.get("tool") and not viewport.startswith("[자동실행"):
        viewport = f"[자동실행 · {meta['tool']}] {viewport}"
    return [meta["run_id"], tc_id, str(result["tc_version"]), viewport, meta["env"], meta["runner"],
            timestamp, verdict, text, evidence_text(result), result.get("issue_id", ""), verdict]


def cmd_init(args: argparse.Namespace) -> int:
    if not RUN_ID_RE.match(args.run_id):
        raise RecordError("Run ID는 QA-YYYYMMDD-NN 형식입니다(예: QA-20261010-01).")
    if "확인" not in args.env and not re.search(r"[0-9a-f]{7}", args.env):
        raise RecordError("--env에 배포 SHA(7자 이상)를 적거나, 모르면 '확인 불가'라고 적으세요. 추측하지 마세요.")
    out = Path(args.out)
    if out.exists() and not args.force:
        raise RecordError(f"{out}가 이미 있습니다. 이어 쓰려면 add를, 새로 만들려면 --force를 쓰세요.")
    with out.open("w", encoding="utf-8", newline="") as handle:
        csv.writer(handle, delimiter="\t").writerow(HEADER)
    meta_path(out).write_text(json.dumps({"run_id": args.run_id, "env": args.env, "runner": args.runner,
                                          "tool": args.tool},
                                         ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"만듦: {out} (Run {args.run_id})")
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    run = Path(args.run)
    meta = json.loads(meta_path(run).read_text(encoding="utf-8"))
    result = json.loads(Path(args.result).read_text(encoding="utf-8"))
    row = build_row(meta, result)
    with run.open("a", encoding="utf-8", newline="") as handle:
        csv.writer(handle, delimiter="\t").writerow(row)
    print(f"{row[1]} → {row[7]}")
    print(row[8])
    return 0


def cmd_summary(args: argparse.Namespace) -> int:
    with Path(args.run).open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    counts = {verdict: 0 for verdict in VERDICTS}
    for row in rows:
        counts[row["결과"]] = counts.get(row["결과"], 0) + 1
    print(" · ".join(f"{verdict} {count}" for verdict, count in counts.items()) + f" (총 {len(rows)}행)")
    for row in rows:
        if row["결과"] != "PASS":
            first = row["실제 결과"].splitlines()[0]
            print(f"- {row['TC ID']} [{row['파라미터/뷰포트']}] {first}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("--out", required=True)
    init.add_argument("--run-id", required=True)
    init.add_argument("--env", required=True, help="예: 'DEV FE 6a3cdca2, BE 297e3873, Admin 64242dd8'")
    init.add_argument("--runner", required=True, help="책임자(사람) 이름. 시트 규칙: 실행자 칸에는 사람만 적는다")
    init.add_argument("--tool", default="", help="모델이 실행하면 도구 이름(예: 'Claude+Playwright'). 파라미터 칸에 [자동실행 · 도구]가 붙는다")
    init.add_argument("--force", action="store_true")
    add = sub.add_parser("add")
    add.add_argument("--run", required=True)
    add.add_argument("result")
    summary = sub.add_parser("summary")
    summary.add_argument("--run", required=True)
    args = parser.parse_args(argv)
    try:
        return {"init": cmd_init, "add": cmd_add, "summary": cmd_summary}[args.command](args)
    except (RecordError, OSError, json.JSONDecodeError, KeyError) as error:
        print(f"기록하지 않았습니다: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
