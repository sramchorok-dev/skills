#!/usr/bin/env python3
"""Validate repository skill structure without third-party dependencies."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import py_compile
import re
import sys


NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FORBIDDEN_NAMES = {".env", ".env.local", ".DS_Store"}
FORBIDDEN_SUFFIXES = {".pem", ".key", ".p12", ".pfx"}


class ValidationError(RuntimeError):
    pass


def parse_frontmatter(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---":
        raise ValidationError(f"{path}: missing YAML frontmatter")
    try:
        end = lines.index("---", 1)
    except ValueError as error:
        raise ValidationError(f"{path}: unclosed YAML frontmatter") from error
    values: dict[str, str] = {}
    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            raise ValidationError(f"{path}: invalid frontmatter line: {line}")
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def validate_eval_file(path: Path, skill_name: str) -> list[str]:
    errors: list[str] = []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"{path}: invalid JSON: {error}"]
    if payload.get("skill_name") != skill_name:
        errors.append(f"{path}: skill_name must be {skill_name}")
    evals = payload.get("evals")
    if not isinstance(evals, list) or not evals:
        errors.append(f"{path}: evals must be a non-empty array")
        return errors
    ids: set[object] = set()
    for index, case in enumerate(evals, 1):
        if not isinstance(case, dict):
            errors.append(f"{path}: eval {index} must be an object")
            continue
        for key in ("id", "prompt", "expected_output", "files"):
            if key not in case:
                errors.append(f"{path}: eval {index} missing {key}")
        if case.get("id") in ids:
            errors.append(f"{path}: duplicate eval id {case.get('id')}")
        ids.add(case.get("id"))
        if not isinstance(case.get("files"), list):
            errors.append(f"{path}: eval {index} files must be an array")
    return errors


def validate(root: Path) -> list[str]:
    errors: list[str] = []
    skills_root = root / "skills"
    skill_dirs = sorted(path for path in skills_root.iterdir() if path.is_dir()) if skills_root.exists() else []
    if not skill_dirs:
        errors.append("skills/: at least one skill is required")

    catalog_path = root / "catalog.json"
    try:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        catalog_items = catalog.get("skills", [])
        catalog_names = [item.get("name") for item in catalog_items if isinstance(item, dict)]
    except (OSError, json.JSONDecodeError) as error:
        errors.append(f"catalog.json: invalid or missing: {error}")
        catalog_names = []

    directory_names = [path.name for path in skill_dirs]
    if sorted(catalog_names) != directory_names:
        errors.append(
            "catalog.json: names must exactly match skills/ directories "
            f"(catalog={sorted(catalog_names)}, directories={directory_names})"
        )
    if len(catalog_names) != len(set(catalog_names)):
        errors.append("catalog.json: duplicate skill names")

    for skill_dir in skill_dirs:
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.is_file():
            errors.append(f"{skill_dir}: SKILL.md missing")
            continue
        try:
            meta = parse_frontmatter(skill_file)
        except ValidationError as error:
            errors.append(str(error))
            continue
        name = meta.get("name", "")
        description = meta.get("description", "")
        if name != skill_dir.name:
            errors.append(f"{skill_file}: name must match directory {skill_dir.name}")
        if not NAME_RE.fullmatch(name):
            errors.append(f"{skill_file}: name must use kebab-case")
        if len(description) < 30:
            errors.append(f"{skill_file}: description must explain behavior and trigger context")
        if len(skill_file.read_text(encoding="utf-8").splitlines()) > 500:
            errors.append(f"{skill_file}: exceeds 500 lines")
        eval_file = skill_dir / "evals" / "evals.json"
        if not eval_file.is_file():
            errors.append(f"{skill_dir}: evals/evals.json missing")
        else:
            errors.extend(validate_eval_file(eval_file, name))

    for path in root.rglob("*"):
        if ".git" in path.parts or not path.is_file():
            continue
        if path.name in FORBIDDEN_NAMES or path.suffix.lower() in FORBIDDEN_SUFFIXES:
            errors.append(f"{path}: secret-bearing file type/name is forbidden")
        if path.suffix == ".py":
            try:
                py_compile.compile(str(path), doraise=True)
            except py_compile.PyCompileError as error:
                errors.append(f"{path}: Python compile failed: {error.msg}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate all skills in this repository")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    errors = validate(args.root.resolve())
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        print(f"validation failed: {len(errors)} error(s)")
        return 1
    skill_count = len([path for path in (args.root / "skills").iterdir() if path.is_dir()])
    print(f"validation passed: {skill_count} skill(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
