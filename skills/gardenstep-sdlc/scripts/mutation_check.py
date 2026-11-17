#!/usr/bin/env python3
"""Remove four gate protections in temporary copies and require tests to catch them."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MUTATIONS = [
    ("failure-count", 'or any(check[k] != 0 for k in ("failed", "skipped", "cancelled"))', 'or False',
     'test_sdlc.EvidenceContractTest.test_failed_tests_with_exit_zero_do_not_pass'),
    ("independent-session", 'or check.get("reviewer_session_id") == manifest["author_session_id"]', 'or False',
     'test_sdlc.EvidenceContractTest.test_same_model_is_allowed_but_same_session_is_not'),
    ("service-identity", 'for key in ("change_id", "services", "harness_version"):', 'for key in ("change_id", "harness_version"):',
     'test_sdlc.EvidenceContractTest.test_wrong_service_sha_and_harness_version_fail'),
    ("required-set", 'if set(checks) != set(policy["required_check_ids"]) or set(observed) != set(checks):', 'if False:',
     'test_sdlc.EvidenceContractTest.test_missing_and_unexpected_checks_fail'),
]


def main():
    original = (ROOT / "scripts/sdlc.py").read_text()
    results = []
    with tempfile.TemporaryDirectory(prefix="sdlc-mutations-") as raw:
        for name, before, after, test in MUTATIONS:
            if original.count(before) != 1:
                raise RuntimeError("mutation target drift: " + name)
            path = Path(raw) / (name.replace("-", "_") + ".py")
            path.write_text(original.replace(before, after, 1))
            run = subprocess.run([sys.executable, "-m", "unittest", test], cwd=ROOT / "tests",
                                 env={**os.environ, "SDLC_TEST_MODULE": str(path)}, capture_output=True, text=True)
            caught = run.returncode != 0 and "FAIL:" in run.stderr and "ERROR:" not in run.stderr
            results.append({"mutation": name, "caught_by_assertion": caught, "test": test})
    print(json.dumps({"status": "PASS" if all(r["caught_by_assertion"] for r in results) else "FAIL",
                      "scope": "four synthetic gate mutations only", "results": results}, indent=2))
    return 0 if all(r["caught_by_assertion"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
