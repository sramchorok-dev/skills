#!/usr/bin/env python3
"""Rehearse local scaffold success and failure paths without remote operations."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from scaffold import ASSETS, ScaffoldError, generate


def main():
    results = []
    profile = json.loads((ASSETS / "profile.example.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="sdlc-bootstrap-sample-") as temporary:
        root = Path(temporary).resolve()
        for mode in ("new", "migration"):
            candidate = root / mode
            candidate.mkdir()
            current = copy.deepcopy(profile)
            current["mode"] = mode
            generated = generate(candidate, current, "Synthetic request.\nCorrection: retain equal owner authority.\n", "sample", True)
            results.append({"case": f"{mode}-draft", "pass": generated["status"] == "WRITTEN" and generated["project_ready"] is False})
            run = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests/sdlc"], cwd=candidate, capture_output=True, text=True)
            results.append({"case": f"{mode}-gate-regressions", "pass": run.returncode == 0, "raw_summary": run.stderr.strip()})
            gate = subprocess.run([sys.executable, "scripts/sdlc/check_change.py", "--root", ".", "--change", "docs/changes/sample"], cwd=candidate, capture_output=True, text=True)
            results.append({"case": f"{mode}-unfinished-blocked", "pass": gate.returncode == 1 and json.loads(gate.stdout)["authority"] == "static-mapping-only"})
            try:
                generate(candidate, current, "Repeated request", "sample", True)
                rejected = False
            except ScaffoldError:
                rejected = True
            results.append({"case": f"{mode}-overwrite-blocked", "pass": rejected})
    print(json.dumps({"authority": "local-synthetic-dry-run", "actual_ci_or_dev_verified": False, "cases": results}, ensure_ascii=False, indent=2))
    return 0 if all(case["pass"] for case in results) else 1


if __name__ == "__main__":
    sys.exit(main())
