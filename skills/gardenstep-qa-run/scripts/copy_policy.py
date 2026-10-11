#!/usr/bin/env python3
"""Check public pages for banned copy (QA sheet A-11) and print paste-ready TSV.

  python3 copy_policy.py --base-url <DEV FE 주소> [--paths / /design /terms | --paths-file paths.txt] --out a11.tsv
  python3 copy_policy.py --html-dir saved-dom/ --out a11.tsv      # 브라우저에서 저장한 DOM으로 오프라인 검사

Raw HTML may miss text rendered in the browser. Pages with little text are reported as LOW_TEXT so an empty
page is never read as "no banned copy". For those, save document.documentElement.outerHTML from the browser
into --html-dir (file name = path with '/' → '_', e.g. _design.html) and run again.
Exit code 1 when a disallowed hit exists (use as a gate), unless --report-only.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

DEFAULT_PATHS = ["/", "/design", "/service", "/faq", "/policy/returns", "/terms", "/proposal", "/estimate",
                 "/cart", "/case"]
DEFAULT_POLICY = Path(__file__).resolve().parents[1] / "assets" / "copy-policy.json"
LOW_TEXT_CHARS = 200
SNIPPET_CHARS = 20
SAFE_HOST_MARKERS = ("dev", "localhost", "127.0.0.1")
OUT_HEADER = ["path", "pattern", "count", "snippet", "allowed", "reason"]

FetchFn = Callable[[str], str]


class PolicyError(ValueError):
    pass


class TextExtractor(HTMLParser):
    SKIP = {"script", "style", "noscript", "template", "svg"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skipping = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skipping += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skipping:
            self.skipping -= 1

    def handle_data(self, data):
        if not self.skipping and data.strip():
            self.parts.append(data.strip())


def page_text(html: str) -> str:
    parser = TextExtractor()
    parser.feed(html)
    return re.sub(r"\s+", " ", " ".join(parser.parts)).strip()


def guard_host(base_url: str, allow_host: str | None) -> str:
    parts = urlsplit(base_url)
    host = (parts.hostname or "").lower()
    if parts.scheme not in ("http", "https") or not host:
        raise PolicyError(f"--base-url이 주소 형식이 아닙니다: {base_url}")
    if not (allow_host and host == allow_host.lower()) and not any(m in host for m in SAFE_HOST_MARKERS):
        raise PolicyError(f"{host}는 DEV 주소로 보이지 않아 멈춥니다. DEV가 맞으면 --allow-host {host}로 다시 실행하세요.")
    return base_url.rstrip("/")


def urllib_fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"Accept": "text/html"})
    with urllib.request.urlopen(request, timeout=30) as reply:
        return reply.read().decode("utf-8", errors="replace")


def load_policy(path: Path) -> dict:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(policy.get("rules"), list) or not policy["rules"]:
        raise PolicyError(f"{path}: rules가 비었습니다.")
    for rule in policy["rules"]:
        if not rule.get("pattern"):
            raise PolicyError(f"{path}: pattern 없는 규칙이 있습니다.")
        for allow in rule.get("allow") or []:
            if allow.get("context"):
                re.compile(allow["context"])
    return policy


def allowed_by(rule: dict, path: str, window: str) -> str | None:
    for allow in rule.get("allow") or []:
        if path in (allow.get("paths") or []):
            return allow.get("reason", "허용 경로")
        if allow.get("context") and re.search(allow["context"], window):
            return allow.get("reason", "허용 문맥")
    return None


def check_page(path: str, text: str, policy: dict) -> list[dict]:
    rows: list[dict] = []
    span = int(policy.get("context_chars", 40))
    for rule in policy["rules"]:
        pattern = rule["pattern"]
        grouped: dict[tuple[str, str], dict] = {}
        for match in re.finditer(re.escape(pattern), text):
            start, end = match.start(), match.end()
            window = text[max(0, start - span):end + span]
            reason = allowed_by(rule, path, window)
            snippet = text[max(0, start - SNIPPET_CHARS):end + SNIPPET_CHARS]
            key = ("yes" if reason else "no", reason or rule.get("reason", ""))
            row = grouped.setdefault(key, {"path": path, "pattern": pattern, "count": 0, "snippet": snippet,
                                           "allowed": key[0], "reason": key[1]})
            row["count"] += 1
        rows.extend(grouped.values())
    return rows


def path_from_file(name: str) -> str:
    stem = Path(name).stem
    return "/" if stem in ("_", "index", "") else stem.replace("_", "/")


def main(argv: list[str] | None = None, fetch: FetchFn = urllib_fetch) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--base-url", help="DEV FE 주소. 운영으로 보이면 멈춘다")
    source.add_argument("--html-dir", help="브라우저에서 저장한 HTML/DOM 폴더(오프라인)")
    parser.add_argument("--allow-host")
    parser.add_argument("--paths", nargs="+")
    parser.add_argument("--paths-file")
    parser.add_argument("--policy", default=str(DEFAULT_POLICY))
    parser.add_argument("--out", help="TSV 경로(없으면 표준 출력)")
    parser.add_argument("--report-only", action="store_true", help="위반이 있어도 종료 코드 0")
    args = parser.parse_args(argv)
    try:
        policy = load_policy(Path(args.policy))
        pages: list[tuple[str, str]] = []
        if args.html_dir:
            files = sorted(p for p in Path(args.html_dir).iterdir() if p.suffix.lower() in (".html", ".htm"))
            if not files:
                raise PolicyError(f"{args.html_dir}에 .html 파일이 없습니다.")
            pages = [(path_from_file(p.name), p.read_text(encoding="utf-8", errors="replace")) for p in files]
        else:
            base = guard_host(args.base_url, args.allow_host)
            paths = args.paths or DEFAULT_PATHS
            if args.paths_file:
                paths = [line.strip() for line in Path(args.paths_file).read_text(encoding="utf-8").splitlines()
                         if line.strip() and not line.startswith("#")]
            for path in paths:
                try:
                    pages.append((path, fetch(base + path)))
                except (urllib.error.URLError, OSError) as error:
                    pages.append((path, ""))
                    print(f"{path}: 불러오지 못함 ({error})", file=sys.stderr)
    except (PolicyError, OSError, json.JSONDecodeError, re.error) as error:
        print(f"실행하지 않았습니다: {error}", file=sys.stderr)
        return 2

    rows: list[dict] = []
    low_text: list[str] = []
    for path, html in pages:
        text = page_text(html)
        if len(text) < LOW_TEXT_CHARS:
            low_text.append(path)
            rows.append({"path": path, "pattern": "LOW_TEXT", "count": len(text), "snippet": text[:40],
                         "allowed": "-", "reason": "글자가 거의 없음 — 브라우저 DOM을 저장해 --html-dir로 다시 검사"})
        rows.extend(check_page(path, text, policy))

    handle = open(args.out, "w", encoding="utf-8", newline="") if args.out else sys.stdout
    try:
        writer = csv.DictWriter(handle, fieldnames=OUT_HEADER, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    finally:
        if args.out:
            handle.close()
    violations = [row for row in rows if row["allowed"] == "no"]
    allowed = [row for row in rows if row["allowed"] == "yes"]
    print(f"페이지 {len(pages)}개 · 위반 {sum(r['count'] for r in violations)}건"
          f"({len({r['path'] for r in violations})}개 페이지) · 허용 {sum(r['count'] for r in allowed)}건"
          f" · LOW_TEXT {len(low_text)}개{' ' + ', '.join(low_text) if low_text else ''}", file=sys.stderr)
    if low_text:
        print("LOW_TEXT 페이지는 검사한 것이 아니다. 위반 0건을 PASS로 적지 않는다.", file=sys.stderr)
    return 1 if violations and not args.report_only else 0


if __name__ == "__main__":
    raise SystemExit(main())
