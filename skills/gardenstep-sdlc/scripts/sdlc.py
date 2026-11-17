#!/usr/bin/env python3
"""Offline contract checks, never an approval or an authenticated execution receipt."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
AUTHORITY = "local-validation-only"
PROVIDERS = {"telegram", "figma", "dropbox", "notion", "github", "interview"}
KINDS = {"test", "eval", "dev", "review"}
HEX40 = r"[0-9a-f]{40}"
HEX64 = r"[0-9a-f]{64}"


def canonical_hash(value):
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(data.encode()).hexdigest()


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key: " + key)
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError("invalid JSON number")))


def outcome(errors, **extra):
    return {"schema_version": 1, "status": "FAIL" if errors else "PASS", "authority": AUTHORITY,
            "errors": errors, **extra}


def text_value(value):
    return isinstance(value, str) and bool(value.strip()) and value == value.strip()


def timestamp(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z", value):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def schema_errors(value, schema, at="$"):
    """The small JSON Schema subset used by the published schemas; no dependencies."""
    errors = []
    types = {"object": dict, "array": list, "string": str, "integer": int, "boolean": bool}
    kind = schema.get("type")
    if kind and (not isinstance(value, types[kind]) or kind == "integer" and isinstance(value, bool)):
        return [f"{at}: expected {kind}"]
    if "const" in schema and (value != schema["const"] or type(value) is not type(schema["const"])):
        errors.append(f"{at}: unsupported value")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{at}: unsupported value")
    if kind == "object":
        properties = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{at}.{key}: required")
        if len(value) < schema.get("minProperties", 0):
            errors.append(f"{at}: empty object")
        for key, child in value.items():
            if key in properties:
                errors += schema_errors(child, properties[key], f"{at}.{key}")
            elif schema.get("additionalProperties") is False:
                errors.append(f"{at}.{key}: unknown field")
            elif isinstance(schema.get("additionalProperties"), dict):
                errors += schema_errors(child, schema["additionalProperties"], f"{at}.{key}")
    if kind == "array":
        if len(value) < schema.get("minItems", 0):
            errors.append(f"{at}: empty array")
        if schema.get("uniqueItems") and len({canonical_hash(v) for v in value}) != len(value):
            errors.append(f"{at}: duplicate items")
        for index, child in enumerate(value):
            errors += schema_errors(child, schema.get("items", {}), f"{at}[{index}]")
    if kind == "string":
        if not text_value(value):
            errors.append(f"{at}: empty or padded string")
        if "pattern" in schema and not re.fullmatch(schema["pattern"], value):
            errors.append(f"{at}: invalid format")
        if schema.get("format") == "date-time" and timestamp(value) is None:
            errors.append(f"{at}: expected valid UTC timestamp ending Z")
    if kind == "integer" and value < schema.get("minimum", 0):
        errors.append(f"{at}: below minimum")
    return errors


def shape(value, name):
    return schema_errors(value, read_json(ROOT / "schemas" / f"{name}.schema.json"), name)


def by_id(rows, label, errors):
    result = {}
    for row in rows:
        if row["id"] in result:
            errors.append(f"{label}: duplicate id {row['id']}")
        result[row["id"]] = row
    return result


def validate_bundle(manifest, evidence, policy):
    errors = shape(manifest, "manifest") + shape(evidence, "evidence") + shape(policy, "policy")
    if errors:
        return outcome(errors)
    digest = canonical_hash(manifest)
    if policy["manifest_sha256"] != digest or evidence["manifest_sha256"] != digest:
        errors.append("manifest digest differs from policy or evidence")
    for key in ("change_id", "services", "harness_version"):
        if evidence[key] != manifest[key]:
            errors.append(f"evidence {key} differs from manifest")
    checks = by_id(manifest["required_checks"], "manifest checks", errors)
    observed = by_id(evidence["checks"], "evidence checks", errors)
    sources = by_id(manifest["sources"], "sources", errors)
    requirements = by_id(manifest["requirements"], "requirements", errors)
    if set(checks) != set(policy["required_check_ids"]) or set(observed) != set(checks):
        errors.append("required check set differs: missing, unexpected or reduced checks")
    if set(sources) != set(policy["required_source_ids"]):
        errors.append("source set differs from policy")
    covered_checks, covered_sources = set(), set()
    for requirement in requirements.values():
        refs, tests = set(requirement["source_ids"]), set(requirement["check_ids"])
        if not refs <= set(sources) or not tests <= set(checks):
            errors.append(f"{requirement['id']}: unknown source or check")
        covered_sources |= refs
        covered_checks |= tests
    if covered_checks != set(checks) or covered_sources != set(sources):
        errors.append("requirement source/check coverage incomplete")
    kinds = {item["kind"] for item in checks.values()}
    if "review" not in kinds or "test" not in kinds:
        errors.append("independent review and deterministic test are required")
    if policy["require_dev"] and "dev" not in kinds:
        errors.append("policy requires actual DEV verification")
    for check in observed.values():
        ident = check["id"]
        if ident not in checks:
            continue
        if check["kind"] != checks[ident]["kind"]:
            errors.append(f"{ident}: check kind changed")
        if check["status"] != "PASS" or check["exit_code"] != 0:
            errors.append(f"{ident}: not explicit success")
        if (check["total"] <= 0 or check["passed"] != check["total"]
                or any(check[k] != 0 for k in ("failed", "skipped", "cancelled"))):
            errors.append(f"{ident}: failed, skipped, cancelled or empty execution")
        start, end = timestamp(check["started_at"]), timestamp(check["finished_at"])
        if end < start:
            errors.append(f"{ident}: reversed timestamps")
        model = check["model"]
        if check["kind"] in {"eval", "review"} and any(
                model[k].strip().lower() in {"unknown", "none", "n/a", "not-applicable", "deterministic"}
                for k in ("name", "version", "prompt_version")):
            errors.append(f"{ident}: model and prompt version required")
        if check["kind"] in {"eval", "review"} and any(
                model[k].strip().lower() in {"unknown", "none", "n/a", "not-applicable"}
                for k in ("judge_name", "judge_version")):
            errors.append(f"{ident}: judge identity and version required")
        if check["kind"] == "review":
            if not text_value(check.get("reviewer_session_id")) or check.get("reviewer_session_id") == manifest["author_session_id"]:
                errors.append(f"{ident}: review session is not independent")
            if type(check.get("blocking_findings")) is not int or check["blocking_findings"] != 0:
                errors.append(f"{ident}: unresolved or unknown blocking findings")
        if check["kind"] == "dev":
            if check.get("environment") != "dev" or check.get("services_before") != manifest["services"] or check.get("services_after") != manifest["services"]:
                errors.append(f"{ident}: actual DEV service identity missing or changed")
    return outcome(errors, manifest_sha256=digest,
                   limitations=["Input consistency only; compare the approved policy, actual GitHub run/artifacts and human approval records independently."])


def doctor(evidence):
    errors = shape(evidence, "source-evidence")
    if errors:
        return outcome(errors)
    entries = by_id(evidence["sources"], "source evidence", errors)
    results = []
    for provider in ("telegram", "figma", "dropbox", "notion"):
        rows = [r for r in entries.values() if r["provider"] == provider]
        if not rows:
            errors.append(f"{provider}: no evidence")
        for row in rows:
            failures = []
            for phase in ("installation", "authentication", "read"):
                if row[phase]["status"] != "PASS":
                    failures.append(phase)
            if row["read"]["status"] == "PASS":
                read = row["read"]
                if not read["complete"] or read["missing_parts"]:
                    failures.append("incomplete read")
                for key in ("revision", "content_sha256", "artifact_uri", "observed_at"):
                    if key not in read:
                        failures.append(f"read.{key} missing")
            if failures:
                errors.append(f"{row['id']}: " + ", ".join(failures))
            results.append({"id": row["id"], "provider": provider,
                            "installation": row["installation"]["status"],
                            "authentication": row["authentication"]["status"],
                            "read": row["read"]["status"], "ready_claim": not failures})
    return outcome(errors, sources=results,
                   limitations=["No connectors or credentials are inspected. Only supplied observation records are checked; their authenticity and freshness require actual connector/browser checks."])


def repository(repo):
    root = Path(repo).resolve()
    config = read_json(root / ".sdlc/repository.json")
    errors = shape(config, "repository")
    for file in ("CLAUDE.md", "AGENTS.md", "REVIEW.md", "docs/testing.md"):
        path = root / file
        if not path.is_file() or not path.read_text(encoding="utf-8").strip():
            errors.append(f"{file}: missing or empty")
    return outcome(errors, limitations=["Repository contract only. Commands, DEV flows, approvals and deployment controls were not executed."])


def dry_run():
    fixture = read_json(ROOT / "assets/sample-bundle.json")
    cases = []
    baseline = validate_bundle(fixture["manifest"], fixture["evidence"], fixture["policy"])
    cases.append({"case": "synthetic-valid", "expected": "PASS", "actual": baseline["status"]})
    for label, mutate in (
        ("empty", lambda b: b["evidence"].update(checks=[])),
        ("skip", lambda b: b["evidence"]["checks"][0].update(skipped=1)),
        ("cancel", lambda b: b["evidence"]["checks"][0].update(status="CANCELLED")),
        ("exit-zero-failure", lambda b: b["evidence"]["checks"][0].update(failed=1)),
        ("wrong-sha", lambda b: b["evidence"]["services"].update({"example/service": "f" * 40})),
        ("same-reviewer", lambda b: b["evidence"]["checks"][1].update(reviewer_session_id="author-sample")),
        ("reduced-required", lambda b: b["manifest"]["required_checks"].pop()),
        ("dev-drift", lambda b: b["evidence"]["checks"][2]["services_after"].update({"example/service": "f" * 40})),
    ):
        bundle = json.loads(json.dumps(fixture))
        mutate(bundle)
        result = validate_bundle(bundle["manifest"], bundle["evidence"], bundle["policy"])
        cases.append({"case": label, "expected": "FAIL", "actual": result["status"]})
    return outcome([c["case"] for c in cases if c["expected"] != c["actual"]], cases=cases,
                   limitations=["Synthetic offline dry-run. No remote writes, authenticated approval, real model call or DEV verification occurred."])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("validate")
    for name in ("manifest", "evidence", "policy"):
        check.add_argument("--" + name, required=True, type=Path)
    inspect = sub.add_parser("doctor")
    inspect.add_argument("--evidence", required=True, type=Path)
    repo = sub.add_parser("repository")
    repo.add_argument("--repo", required=True, type=Path)
    digest = sub.add_parser("hash")
    digest.add_argument("path", type=Path)
    sub.add_parser("dry-run")
    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            result = validate_bundle(read_json(args.manifest), read_json(args.evidence), read_json(args.policy))
        elif args.command == "doctor":
            result = doctor(read_json(args.evidence))
        elif args.command == "repository":
            result = repository(args.repo)
        elif args.command == "hash":
            print(canonical_hash(read_json(args.path)))
            return 0
        else:
            result = dry_run()
    except (OSError, ValueError, TypeError, KeyError) as exc:
        result = outcome([f"invalid input: {type(exc).__name__}"])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
