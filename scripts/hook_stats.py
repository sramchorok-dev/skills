#!/usr/bin/env python3
"""gardenstep-team hook 결정 로그(~/.claude/gardenstep-team/decisions.jsonl)를 규칙별로 집계한다.

  python3 scripts/hook_stats.py --days 30
  python3 scripts/hook_stats.py --days 14 --json

결과는 각자 컴퓨터의 로그만 본다. 팀 집계는 각자 출력(명령 내용 없음)을 모아 JD에게 공유한다.
조정 후보: 확인 요청이 충분히 많은데(--min-asks) 거의 항상 승인되는(--noise-rate) 규칙 — 오탐일 가능성이 높다.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys


def default_log() -> Path:
    override = os.environ.get("GARDENSTEP_TEAM_LOG")
    return Path(override) if override else Path.home() / ".claude" / "gardenstep-team" / "decisions.jsonl"


def load(paths: list[Path], since: datetime) -> list[dict]:
    rows: list[dict] = []
    for path in paths:
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
                ts = datetime.fromisoformat(row["ts"])
            except (ValueError, KeyError, TypeError):
                continue
            if ts >= since:
                rows.append(row)
    return rows


def summarize(rows: list[dict], min_asks: int = 10, noise_rate: float = 0.9) -> dict:
    asks: Counter = Counter()
    ran: Counter = Counter()
    other: dict[str, Counter] = defaultdict(Counter)
    repos: Counter = Counter()
    for row in rows:
        decision, rules = row.get("decision"), row.get("rules") or []
        if row.get("repo"):
            repos[row["repo"]] += 1
        for rule in rules:
            if decision == "ask":
                asks[rule] += 1
            elif decision == "ran":
                ran[rule] += 1
            else:
                other[decision][rule] += 1
    table = []
    for rule in sorted(set(asks) | {r for r in ran if r in asks}, key=lambda r: -asks[r]):
        rate = min(ran[rule] / asks[rule], 1.0) if asks[rule] else None
        table.append({
            "rule": rule,
            "asks": asks[rule],
            "ran": ran[rule],
            "approval_rate": round(rate, 2) if rate is not None else None,
            "tuning_candidate": bool(rate is not None and asks[rule] >= min_asks and rate >= noise_rate),
        })
    return {
        "events": len(rows),
        "ask_rules": table,
        "deny": dict(other["deny"].most_common()),
        "note": dict(other["note"].most_common()),
        "block": dict(other["block"].most_common()),
        "repos": dict(repos.most_common()),
    }


def render(summary: dict, days: int) -> str:
    lines = [f"gardenstep-team hook 통계 — 최근 {days}일, 이벤트 {summary['events']}건", ""]
    if summary["ask_rules"]:
        lines.append("확인(ask) 규칙별: 요청 → 실행(승인) · 승인률")
        for row in summary["ask_rules"]:
            rate = "—" if row["approval_rate"] is None else f"{row['approval_rate']:.0%}"
            flag = "  ← 조정 후보(거의 항상 승인)" if row["tuning_candidate"] else ""
            lines.append(f"  {row['rule']:<24} {row['asks']:>4} → {row['ran']:>4} · {rate}{flag}")
    else:
        lines.append("확인(ask) 기록 없음")
    for key, title in (("deny", "편집 차단(deny)"), ("note", "테스트 스멜 알림(note)"), ("block", "Stop 되돌림(block)")):
        if summary[key]:
            lines.append("")
            lines.append(title + ": " + ", ".join(f"{rule} {n}" for rule, n in summary[key].items()))
    if summary["repos"]:
        lines.append("")
        lines.append("레포별 이벤트: " + ", ".join(f"{repo} {n}" for repo, n in summary["repos"].items()))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="gardenstep-team hook 결정 로그 집계")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--log", type=Path, default=None, help="기본: ~/.claude/gardenstep-team/decisions.jsonl")
    parser.add_argument("--min-asks", type=int, default=10)
    parser.add_argument("--noise-rate", type=float, default=0.9)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    log = args.log or default_log()
    since = datetime.now(timezone.utc) - timedelta(days=args.days)
    rows = load([log.with_suffix(".jsonl.1"), log], since)
    summary = summarize(rows, args.min_asks, args.noise_rate)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(render(summary, args.days))
    return 0


if __name__ == "__main__":
    sys.exit(main())
