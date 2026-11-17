import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SKILL = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("scaffold", SKILL / "scripts/scaffold.py")
scaffold = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scaffold)


class ScaffoldTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / "project"
        self.root.mkdir()
        self.profile = json.loads((SKILL / "assets/profile.example.json").read_text())
        self.request = "원문: 두 팀원이 같은 권한으로 진행해줘.\n정정: 시범 운영은 제외하고 샘플만.\n"

    def run_scaffold(self, apply=False, **kwargs):
        return scaffold.generate(self.root, self.profile, self.request, "2026-01-01-sdlc", apply, **kwargs)

    def test_default_dry_run_writes_nothing(self):
        result = self.run_scaffold()
        self.assertEqual("DRY_RUN", result["status"])
        self.assertFalse(result["project_ready"])
        self.assertEqual([], list(self.root.iterdir()))
        self.assertIn("AGENTS.md", result["files"])

    def test_apply_preserves_original_request_and_no_claim_of_readiness(self):
        result = self.run_scaffold(True)
        intent = (self.root / "docs/changes/2026-01-01-sdlc/intent.md").read_text()
        self.assertIn(self.request, intent)
        self.assertEqual("WRITTEN", result["status"])
        self.assertFalse(result["project_ready"])
        self.assertIn("NOT_RUN", (self.root / "docs/sdlc/activation.md").read_text())
        self.assertEqual(["owner-a", "owner-b"], [m["id"] for m in json.loads((self.root / "docs/sdlc/profile.json").read_text())["members"]])
        self.assertLess(len((self.root / "AGENTS.md").read_text().splitlines()), 60)

    def test_existing_file_causes_no_partial_writes(self):
        existing = self.root / "AGENTS.md"
        existing.write_bytes(b"user changes\r\n")
        with self.assertRaisesRegex(scaffold.ScaffoldError, "existing files"):
            self.run_scaffold(True)
        self.assertEqual(b"user changes\r\n", existing.read_bytes())
        self.assertEqual([existing], list(self.root.iterdir()))

    def test_rerun_never_overwrites(self):
        self.run_scaffold(True)
        before = {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        with self.assertRaises(scaffold.ScaffoldError):
            self.run_scaffold(True)
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})

    def test_symlink_output_directory_cannot_escape(self):
        outside = self.root.parent / "outside"
        outside.mkdir()
        (self.root / "docs").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(scaffold.ScaffoldError, "symlink"):
            self.run_scaffold(True)
        self.assertEqual([], list(outside.iterdir()))
        self.assertFalse((self.root / "AGENTS.md").exists())

    def test_dangling_symlink_file_is_rejected(self):
        (self.root / "CLAUDE.md").symlink_to(self.root.parent / "missing")
        with self.assertRaisesRegex(scaffold.ScaffoldError, "symlink"):
            self.run_scaffold(True)
        self.assertFalse((self.root / "AGENTS.md").exists())

    def test_symlink_root_is_rejected(self):
        link = self.root.parent / "alias"
        link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(scaffold.ScaffoldError, "not a symlink"):
            scaffold.generate(link, self.profile, self.request, "sample", True)
        self.assertEqual([], list(self.root.iterdir()))

    def test_file_as_parent_is_rejected_before_writes(self):
        (self.root / "docs").write_text("original")
        with self.assertRaises(scaffold.ScaffoldError):
            self.run_scaffold(True)
        self.assertFalse((self.root / "AGENTS.md").exists())
        self.assertEqual("original", (self.root / "docs").read_text())

    def test_change_id_rejects_path_escape(self):
        for change_id in ("../outside", "/absolute", "a/b", "", "UPPER", "."):
            with self.subTest(change_id=change_id), self.assertRaises(scaffold.ScaffoldError):
                scaffold.generate(self.root, self.profile, self.request, change_id, True)
        self.assertEqual([], list(self.root.iterdir()))

    def test_relative_root_is_rejected(self):
        with self.assertRaises(scaffold.ScaffoldError):
            scaffold.generate(Path("relative"), self.profile, self.request, "sample", True)

    def test_profile_unknown_key_is_rejected(self):
        self.profile["token"] = "do-not-store"
        with self.assertRaisesRegex(scaffold.ScaffoldError, "exactly these keys"):
            self.run_scaffold(True)
        self.assertEqual([], list(self.root.iterdir()))

    def test_profile_missing_owner_and_duplicate_ids_are_rejected(self):
        for update in ([{"id": "one", "approvals": []}], self.profile["members"] * 2):
            with self.subTest(update=update), self.assertRaises(scaffold.ScaffoldError):
                scaffold.profile_check({**self.profile, "members": update})

    def test_source_owner_must_exist(self):
        self.profile["sources"][0]["owner"] = "unconfirmed-person"
        with self.assertRaises(scaffold.ScaffoldError):
            self.run_scaffold(True)

    def test_nonfinite_or_negative_budget_is_rejected(self):
        for value in (-1, float("nan"), float("inf"), True):
            with self.subTest(value=value), self.assertRaises(scaffold.ScaffoldError):
                scaffold.profile_check({**self.profile, "new_monthly_cost_limit": value})

    def test_failure_rolls_back_only_created_files(self):
        unrelated = self.root / "existing.txt"
        unrelated.write_text("retain")
        original = scaffold.os.open
        calls = 0
        def fail_third(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 3:
                raise OSError("simulated disk failure")
            return original(*args, **kwargs)
        with mock.patch.object(scaffold.os, "open", side_effect=fail_third), self.assertRaises(OSError):
            self.run_scaffold(True)
        self.assertEqual([unrelated], list(self.root.iterdir()))
        self.assertEqual("retain", unrelated.read_text())

    def test_manifest_matches_generated_bytes(self):
        self.run_scaffold(True)
        manifest = json.loads((self.root / ".sdlc/bootstrap.json").read_text())
        self.assertEqual("scaffold-only", manifest["authority"])
        for relative, digest in manifest["files"].items():
            self.assertEqual(digest, scaffold.hashlib.sha256((self.root / relative).read_bytes()).hexdigest())

    def test_generated_gate_regressions_pass_but_unfilled_project_fails(self):
        self.run_scaffold(True)
        tests = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests/sdlc", "-v"], cwd=self.root, capture_output=True, text=True)
        self.assertEqual(0, tests.returncode, tests.stderr)
        self.assertIn("Ran 15 tests", tests.stderr)
        gate = subprocess.run([sys.executable, "scripts/sdlc/check_change.py", "--root", ".", "--change", "docs/changes/2026-01-01-sdlc"], cwd=self.root, capture_output=True, text=True)
        self.assertEqual(1, gate.returncode)
        self.assertEqual("static-mapping-only", json.loads(gate.stdout)["authority"])

    def test_cli_preserves_crlf_request_bytes(self):
        profile_path = self.root.parent / "profile.json"
        profile_path.write_text(json.dumps(self.profile))
        request_path = self.root.parent / "request.txt"
        request_path.write_bytes(b"literal original\r\nsecond line\r\n")
        result = subprocess.run([sys.executable, str(SKILL / "scripts/scaffold.py"), "--root", str(self.root), "--profile", str(profile_path), "--request-file", str(request_path), "--change-id", "sample", "--apply"], capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn(request_path.read_bytes(), (self.root / "docs/changes/sample/intent.md").read_bytes())


if __name__ == "__main__":
    unittest.main()
