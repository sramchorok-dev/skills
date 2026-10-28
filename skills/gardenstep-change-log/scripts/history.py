#!/usr/bin/env python3
"""여러 레포의 변경기록(docs/changes)과 ADR(docs/adr, docs/decisions)을 한곳에서 찾는다. 읽기 전용.

  history.py 쿠폰 할인                       # 단어가 모두 들어간 기록
  history.py --risk migration --since 2026-09-01
  history.py --kind adr --ref origin/dev    # 작업 트리가 아니라 origin/dev 기준

레포마다 기록을 두는 대신 조회만 모은다 — 쓰기는 각 레포 PR에서, 읽기는 여기서.
표준 라이브러리만 쓴다.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import change_record as cr  # noqa: E402

DEFAULT_REPOS = ("gardenstep", "gardenstep-server", "gardenstep_admin", "gardenstep-ai")
DIRS = ("docs/changes", "docs/adr", "docs/decisions")


def _list(root: Path, ref: str | None) -> list[str]:
    if ref:
        out = subprocess.run(["git", "-C", str(root), "ls-tree", "-r", "--name-only", ref, "--", *DIRS],
                             capture_output=True, text=True)
        names = out.stdout.splitlines() if out.returncode == 0 else []
    else:
        names = [p.relative_to(root).as_posix() for d in DIRS for p in (root / d).glob("**/*.md")]
    return sorted(n for n in names if n.endswith(".md") and not n.rsplit("/", 1)[-1].startswith(("0000-", "README")))


def _read(root: Path, ref: str | None, rel: str) -> str:
    if ref:
        out = subprocess.run(["git", "-C", str(root), "show", f"{ref}:{rel}"], capture_output=True, text=True)
        return out.stdout if out.returncode == 0 else ""
    return (root / rel).read_text(encoding="utf-8", errors="replace")


def load(root: Path, ref: str | None) -> list[dict[str, str]]:
    items = []
    for rel in _list(root, ref):
        text = _read(root, ref, rel)
        if rel.startswith("docs/changes/"):
            meta, _ = cr.parse(text)
            kind, status = "change", meta.get("type", "")
            date = meta.get("date") or rel.rsplit("/", 1)[-1][:10]
            risk, pr, adr = meta.get("risk", ""), meta.get("pr", ""), meta.get("adr", "none")
        else:
            head = cr.adr_header(text)
            kind = "adr"
            status = (head.get("상태") or (re.search(r"(?ms)^## Status\s+(\w+)", text) or [None, ""])[1])[:20]
            date = head.get("날짜") or ""
            risk, pr, adr = "", "", ""
        title = (re.search(r"(?m)^#\s+(.+)$", text) or [None, rel])[1].strip()
        items.append({"repo": root.name, "kind": kind, "date": date, "status": status, "risk": risk,
                      "pr": pr, "adr": adr, "title": title, "path": rel, "text": text})
    return items


def select(items: list[dict[str, str]], terms: list[str], kind: str = "all", risk: str | None = None,
           type_: str | None = None, since: str | None = None, adr_only: bool = False) -> list[dict[str, str]]:
    out = []
    for it in items:
        if kind != "all" and it["kind"] != kind:
            continue
        if risk and it["risk"] != risk:
            continue
        if type_ and it["status"] != type_:
            continue
        if since and (it["date"] or "0000") < since:
            continue
        if adr_only and it["adr"] in ("", "none"):
            continue
        hay = it["text"].lower()
        if all(t.lower() in hay for t in terms):
            out.append(it)
    return sorted(out, key=lambda it: (it["date"], it["repo"], it["path"]), reverse=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="레포 가로지르는 변경기록·ADR 검색")
    ap.add_argument("terms", nargs="*", help="모두 포함해야 하는 단어")
    ap.add_argument("--root", action="append", type=Path, help="레포 경로(반복 가능). 기본: 현재 디렉터리 아래 gardenstep* 레포")
    ap.add_argument("--ref", help="작업 트리 대신 읽을 git ref (예: origin/dev)")
    ap.add_argument("--kind", choices=["all", "change", "adr"], default="all")
    ap.add_argument("--risk", choices=sorted(cr.RISKS))
    ap.add_argument("--type", dest="type_", help="변경기록 type 또는 ADR 상태")
    ap.add_argument("--since", help="YYYY-MM-DD 이후")
    ap.add_argument("--adr-only", action="store_true", help="adr:가 있는 변경기록만")
    ap.add_argument("--limit", type=int, default=30)
    args = ap.parse_args(argv)

    roots = args.root or [p for name in DEFAULT_REPOS if (p := Path(name)).is_dir()]
    if not roots:
        print("레포를 찾지 못했습니다 — --root로 지정하거나 워크스페이스 루트에서 실행하세요", file=sys.stderr)
        return 1
    items = [it for r in roots for it in load(r.resolve(), args.ref)]
    found = select(items, args.terms, args.kind, args.risk, args.type_, args.since, args.adr_only)
    for it in found[: args.limit]:
        tag = f"{it['kind']}:{it['status']}" + (f"/{it['risk']}" if it["risk"] else "")
        print(f"{it['date']}  {it['repo']:<18} {tag:<24} {it['title']}\n    {it['path']}" + (f"  (PR {it['pr']})" if it["pr"] else ""))
    print(f"-- {len(found)}건" + (f" 중 {args.limit}건 표시" if len(found) > args.limit else ""))
    return 0 if found else 1


if __name__ == "__main__":
    raise SystemExit(main())
