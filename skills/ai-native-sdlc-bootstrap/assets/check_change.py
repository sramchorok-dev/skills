#!/usr/bin/env python3
"""Check requirement-to-test references. This is not an approval or test runner."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys


class InvalidRecord(ValueError):
    pass


def beneath(root: Path, relative: str) -> Path:
    path = Path(relative)
    if not relative or path.is_absolute() or ".." in path.parts:
        raise InvalidRecord(f"path must stay under the project root: {relative!r}")
    current = root
    for part in path.parts:
        current = current / part
        if current.is_symlink():
            raise InvalidRecord(f"symlink is not a record/test file: {relative}")
    if not current.is_file():
        raise InvalidRecord(f"missing regular file: {relative}")
    return current


def validate(root: Path, change: str) -> list[str]:
    errors: list[str] = []
    root = root.resolve(strict=True)
    try:
        texts = {
            name: beneath(root, f"{change}/{name}.md").read_text(encoding="utf-8")
            for name in ("intent", "spec", "plan")
        }
        if any(not text.strip() for text in texts.values()):
            raise InvalidRecord("intent/spec/plan must all contain text")
        if re.search(r"\b(?:TODO|TBD|REPLACE_ME)\b", texts["spec"] + texts["plan"]):
            raise InvalidRecord("spec/plan still contains draft placeholders")
        requirements = re.findall(r"^## (R[1-9][0-9]*):\s+\S.*$", texts["spec"], re.MULTILINE)
        if not requirements or len(set(requirements)) != len(requirements):
            raise InvalidRecord("spec needs unique '## R1: observable requirement' headings")
        mapping = json.loads(beneath(root, f"{change}/checks.json").read_text(encoding="utf-8"))
        if not isinstance(mapping, dict) or mapping.get("schema_version") != 1 or not isinstance(mapping.get("requirements"), list):
            raise InvalidRecord("checks.json needs schema_version 1 and requirements array")
        entries = mapping["requirements"]
        ids = [entry.get("id") if isinstance(entry, dict) else None for entry in entries]
        if len(ids) != len(set(ids)) or set(ids) != set(requirements):
            raise InvalidRecord("checks.json must map every spec requirement exactly once")
        for entry in entries:
            requirement = entry["id"]
            if entry.get("verification") == "manual":
                if not isinstance(entry.get("reason"), str) or not entry["reason"].strip():
                    raise InvalidRecord(f"{requirement}: manual verification needs a reason")
                if not isinstance(entry.get("owner"), str) or not entry["owner"].strip():
                    raise InvalidRecord(f"{requirement}: manual verification needs an owner")
                continue
            if entry.get("verification") != "automated":
                raise InvalidRecord(f"{requirement}: verification must be automated or manual")
            tests = entry.get("tests")
            if not isinstance(tests, list) or not tests:
                raise InvalidRecord(f"{requirement}: automated requirement has no test references")
            for test in tests:
                if not isinstance(test, dict) or not isinstance(test.get("path"), str):
                    raise InvalidRecord(f"{requirement}: test needs a relative path")
                content = beneath(root, test["path"]).read_text(encoding="utf-8")
                case = test.get("case")
                if not isinstance(case, str) or not case.strip() or case not in content:
                    raise InvalidRecord(f"{requirement}: referenced test case was not found")
    except (InvalidRecord, OSError, ValueError, TypeError) as error:
        errors.append(str(error))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--change", required=True, help="relative change directory")
    args = parser.parse_args()
    try:
        errors = validate(args.root, args.change)
    except OSError as error:
        errors = [str(error)]
    print(json.dumps({"authority": "static-mapping-only", "status": "FAIL" if errors else "PASS", "errors": errors}, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
