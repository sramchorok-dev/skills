#!/usr/bin/env python3
"""Validate and publish one HTML report to the Gardenstep DEV Report Wiki."""

from __future__ import annotations

import argparse
import datetime as dt
from html.parser import HTMLParser
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unicodedata
from urllib.parse import quote
from urllib.request import Request, urlopen


SKILL_ROOT = Path(__file__).resolve().parents[1]
INDEX = SKILL_ROOT / "assets" / "index.html"

AWS_PROFILE = os.environ.get("GARDENSTEP_AWS_PROFILE", "gardenstep-dev")
AWS_ACCOUNT = "025066272991"
BUCKET = "gardenstep-dev"
PREFIX = "report-wiki"
DISTRIBUTION_ID = "E1S7N6821RE7HR"
PUBLIC_BASE_URL = "https://cdn-dev.gardenstep.ai/report-wiki"
HEADER = "// Public registry. publish_report.py manages this array.\n"
ALLOWED_PROJECTS = {"chorok"}
PROJECT_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    re.compile(
        r"(?i)\b(?:aws_secret_access_key|openai_api_key|db_password)"
        r"\s*[:=]\s*[\"']?[A-Za-z0-9/+_=-]{8,}"
    ),
)


class PublishError(RuntimeError):
    pass


class ReportMetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title_parts: list[str] = []
        self.h1_parts: list[str] = []
        self.description = ""
        self._capture: str | None = None
        self._title_done = False
        self._h1_done = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "title" and not self._title_done:
            self._capture = "title"
        elif tag == "h1" and not self._h1_done:
            self._capture = "h1"
        if tag == "meta" and attributes.get("name", "").lower() == "description":
            self.description = (attributes.get("content") or "").strip()

    def handle_endtag(self, tag: str) -> None:
        if self._capture == tag:
            self._capture = None
            if tag == "title":
                self._title_done = True
            elif tag == "h1":
                self._h1_done = True

    def handle_data(self, data: str) -> None:
        if self._capture == "title":
            self.title_parts.append(data)
        elif self._capture == "h1":
            self.h1_parts.append(data)


def run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=check, text=True, capture_output=True)


def parse_registry(text: str) -> list[dict]:
    match = re.search(r"window\.REPORTS\s*=\s*(\[.*\]);", text, re.S)
    if not match:
        raise PublishError("data.js registry not found")
    value = json.loads(match.group(1))
    if not isinstance(value, list):
        raise PublishError("data.js registry must be an array")
    return value


def registry_text(items: list[dict]) -> str:
    return HEADER + "window.REPORTS = " + json.dumps(items, ensure_ascii=False, indent=2) + ";\n"


def file_slug(path: Path) -> str:
    stem = unicodedata.normalize("NFC", path.stem)
    stem = re.sub(r"[^0-9A-Za-z가-힣._-]+", "-", stem).strip("-.")
    if not stem:
        stem = "report-" + hashlib.sha256(path.name.encode()).hexdigest()[:10]
    return stem[:100]


def infer_metadata(path: Path) -> tuple[str, str]:
    parser = ReportMetadataParser()
    parser.feed(path.read_text(encoding="utf-8", errors="strict"))
    title = " ".join("".join(parser.title_parts).split())
    if not title:
        title = " ".join("".join(parser.h1_parts).split())
    return title, " ".join(parser.description.split())


def validate_source(path: Path, project: str, date: str, acknowledge: bool) -> str:
    if not acknowledge:
        raise PublishError("public upload requires --ack-public")
    if not PROJECT_RE.fullmatch(project):
        raise PublishError("project must match [a-z0-9-] and be at most 40 characters")
    if project not in ALLOWED_PROJECTS:
        raise PublishError("public DEV wiki currently accepts only the chorok project")
    if not DATE_RE.fullmatch(date):
        raise PublishError("date must use YYYY-MM-DD")
    try:
        dt.date.fromisoformat(date)
    except ValueError as error:
        raise PublishError("date is not a valid calendar date") from error
    if not path.is_file() or path.suffix.lower() != ".html":
        raise PublishError("public report must be an existing .html file")
    if path.stat().st_size > 20 * 1024 * 1024:
        raise PublishError("public report exceeds the 20 MiB limit")
    content = path.read_text(encoding="utf-8", errors="strict")
    lowered = content.lower()
    if "<html" not in lowered or "</html>" not in lowered:
        raise PublishError("public report must contain a complete HTML document")
    for pattern in SECRET_PATTERNS:
        if pattern.search(content):
            raise PublishError(f"possible secret detected: {pattern.pattern}")
    return content


def normalize_tags(raw_tags: str) -> list[str]:
    tags = list(dict.fromkeys(value.strip() for value in raw_tags.split(",") if value.strip()))
    if len(tags) > 10:
        raise PublishError("at most 10 public tags are allowed")
    if any(len(tag) > 30 for tag in tags):
        raise PublishError("each public tag must be at most 30 characters")
    return tags


def make_entry(
    *, source: Path, project: str, title: str, desc: str, tags: list[str], date: str
) -> dict:
    title = title.strip()
    desc = desc.strip()
    if not title:
        raise PublishError("title is required; add --title or an HTML <title>/<h1>")
    if len(title) > 120:
        raise PublishError("title must be at most 120 characters")
    if len(desc) > 240:
        raise PublishError("description must be at most 240 characters")
    stem = file_slug(source)
    relative = Path("reports") / project / f"{date}-{stem}.html"
    digest = hashlib.sha256(str(relative).encode()).hexdigest()[:12]
    return {
        "id": f"{project}-{date}-{digest}",
        "project": project,
        "type": "html",
        "title": title,
        "desc": desc,
        "date": date,
        "path": relative.as_posix(),
        "tags": tags,
    }


def merge_entry(items: list[dict], entry: dict) -> list[dict]:
    remaining = [
        item
        for item in items
        if item.get("id") != entry["id"] and item.get("path") != entry["path"]
    ]
    return [entry, *remaining]


def aws_base() -> list[str]:
    return ["aws", "--profile", AWS_PROFILE]


def verify_account() -> None:
    result = run(
        [*aws_base(), "sts", "get-caller-identity", "--query", "Account", "--output", "text"]
    )
    if result.stdout.strip() != AWS_ACCOUNT:
        raise PublishError(f"unexpected AWS account: {result.stdout.strip()}")


def remote_registry(temp_dir: Path) -> tuple[list[dict], str | None]:
    target = temp_dir / "data.js"
    result = run(
        [
            *aws_base(), "s3api", "get-object", "--bucket", BUCKET,
            "--key", f"{PREFIX}/data.js", str(target),
        ],
        check=False,
    )
    if result.returncode:
        if "NoSuchKey" in result.stderr or "404" in result.stderr:
            return [], None
        raise PublishError(result.stderr.strip() or "remote registry download failed")
    metadata = json.loads(result.stdout or "{}")
    return parse_registry(target.read_text(encoding="utf-8")), metadata.get("ETag")


def put_static(local: Path, key: str, content_type: str, cache_control: str) -> None:
    run(
        [
            *aws_base(), "s3api", "put-object", "--bucket", BUCKET, "--key", key,
            "--body", str(local), "--content-type", content_type,
            "--cache-control", cache_control, "--server-side-encryption", "AES256",
        ]
    )


def put_registry(path: Path, etag: str | None) -> bool:
    command = [
        *aws_base(), "s3api", "put-object", "--bucket", BUCKET,
        "--key", f"{PREFIX}/data.js", "--body", str(path),
        "--content-type", "application/javascript; charset=utf-8",
        "--cache-control", "no-cache, max-age=0", "--server-side-encryption", "AES256",
    ]
    command.extend(["--if-match", etag] if etag else ["--if-none-match", "*"])
    result = run(command, check=False)
    if result.returncode == 0:
        return True
    if "PreconditionFailed" in result.stderr or "412" in result.stderr:
        return False
    raise PublishError(result.stderr.strip() or "remote registry upload failed")


def verify_public(entry: dict) -> None:
    index_url = f"{PUBLIC_BASE_URL}/index.html"
    data_url = f"{PUBLIC_BASE_URL}/data.js"
    report_url = f"{PUBLIC_BASE_URL}/{quote(entry['path'], safe='/')}"
    headers = {"User-Agent": "gardenstep-report-wiki/1.0"}
    with urlopen(Request(index_url, headers=headers), timeout=20) as response:
        if response.status != 200:
            raise PublishError(f"public index returned HTTP {response.status}")
    with urlopen(Request(data_url, headers=headers), timeout=20) as response:
        remote_items = parse_registry(response.read().decode("utf-8"))
    if not any(item.get("id") == entry["id"] for item in remote_items):
        raise PublishError("public registry read-back is missing the report")
    with urlopen(Request(report_url, method="HEAD", headers=headers), timeout=20) as response:
        if response.status != 200:
            raise PublishError(f"public report returned HTTP {response.status}")


def deploy(source: Path, entry: dict) -> None:
    if not INDEX.is_file():
        raise PublishError(f"bundled index missing: {INDEX}")
    verify_account()
    put_static(INDEX, f"{PREFIX}/index.html", "text/html; charset=utf-8", "no-cache, max-age=0")
    put_static(
        source, f"{PREFIX}/{entry['path']}", "text/html; charset=utf-8", "public, max-age=300"
    )

    with tempfile.TemporaryDirectory(prefix="report-wiki-") as raw_temp:
        temp_dir = Path(raw_temp)
        for attempt in range(1, 4):
            items, etag = remote_registry(temp_dir)
            registry = temp_dir / f"data-{attempt}.js"
            registry.write_text(registry_text(merge_entry(items, entry)), encoding="utf-8")
            if put_registry(registry, etag):
                break
        else:
            raise PublishError("remote registry changed repeatedly; retry the publish command")

    report_path = "/" + quote(f"{PREFIX}/{entry['path']}", safe="/")
    invalidation = run(
        [
            *aws_base(), "cloudfront", "create-invalidation",
            "--distribution-id", DISTRIBUTION_ID,
            "--paths", f"/{PREFIX}/index.html", f"/{PREFIX}/data.js", report_path,
            "--query", "Invalidation.Id", "--output", "text",
        ]
    )
    invalidation_id = invalidation.stdout.strip()
    if not invalidation_id:
        raise PublishError("CloudFront invalidation ID missing")
    run(
        [
            *aws_base(), "cloudfront", "wait", "invalidation-completed",
            "--distribution-id", DISTRIBUTION_ID, "--id", invalidation_id,
        ]
    )
    verify_public(entry)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate and publish a public Gardenstep HTML report"
    )
    parser.add_argument("file", help="complete HTML report path")
    parser.add_argument("--project", default="chorok")
    parser.add_argument("--title", help="default: HTML <title>, then first <h1>")
    parser.add_argument("--desc", help="default: HTML meta description")
    parser.add_argument("--tags", default="", help="comma-separated public tags")
    parser.add_argument("--date", help="YYYY-MM-DD; default: source modification date")
    parser.add_argument(
        "--ack-public", action="store_true", help="confirm the report is safe for public access"
    )
    parser.add_argument("--deploy", action="store_true", help="upload to the public DEV CDN")
    parser.add_argument("--json", action="store_true", help="print a machine-readable receipt")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    source = Path(args.file).expanduser().resolve()
    date = args.date or (
        dt.date.fromtimestamp(source.stat().st_mtime).isoformat() if source.exists() else ""
    )
    try:
        validate_source(source, args.project, date, args.ack_public)
        inferred_title, inferred_desc = infer_metadata(source)
        entry = make_entry(
            source=source,
            project=args.project,
            title=args.title if args.title is not None else inferred_title,
            desc=args.desc if args.desc is not None else inferred_desc,
            tags=normalize_tags(args.tags),
            date=date,
        )
        if args.deploy:
            deploy(source, entry)
        receipt = {
            "status": "published" if args.deploy else "validated",
            "wiki_url": f"{PUBLIC_BASE_URL}/index.html",
            "report_url": f"{PUBLIC_BASE_URL}/{quote(entry['path'], safe='/')}",
            "entry": entry,
        }
        if args.json:
            print(json.dumps(receipt, ensure_ascii=False, indent=2))
        else:
            print(f"status: {receipt['status']}")
            print(f"wiki: {receipt['wiki_url']}")
            print(f"report: {receipt['report_url']}")
        return 0
    except (OSError, ValueError, PublishError, subprocess.CalledProcessError) as error:
        if args.json:
            print(json.dumps({"status": "error", "error": str(error)}, ensure_ascii=False))
        else:
            print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
