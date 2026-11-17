"""Contract probes for the scaffolded requirement reference gate."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

GATE = Path(__file__).resolve().parents[2] / "scripts/sdlc/check_change.py"
spec = importlib.util.spec_from_file_location("change_gate", GATE)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class ChangeGateTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.change = self.root / "docs/changes/sample"
        self.change.mkdir(parents=True)
        for name in ("intent", "plan"):
            (self.change / f"{name}.md").write_text("A concrete reviewed record.\n")
        (self.change / "spec.md").write_text("## R1: A signed-in user can read a result\n")
        (self.root / "test_result.py").write_text("def test_read_result(): pass\n")
        self.mapping = {"schema_version": 1, "requirements": [{"id": "R1", "verification": "automated", "tests": [{"path": "test_result.py", "case": "test_read_result"}]}]}

    def check(self):
        (self.change / "checks.json").write_text(json.dumps(self.mapping))
        return gate.validate(self.root, "docs/changes/sample")

    def test_valid_references_are_only_static_validation(self):
        self.assertEqual([], self.check())

    def test_missing_requirement_mapping_fails(self):
        self.mapping["requirements"] = []
        self.assertTrue(self.check())

    def test_missing_test_file_fails(self):
        (self.root / "test_result.py").unlink()
        self.assertTrue(self.check())

    def test_wrong_case_fails(self):
        self.mapping["requirements"][0]["tests"][0]["case"] = "test_other"
        self.assertTrue(self.check())

    def test_escaping_test_path_fails(self):
        self.mapping["requirements"][0]["tests"][0]["path"] = "../outside.py"
        self.assertTrue(self.check())

    def test_symlink_test_file_fails(self):
        (self.root / "link.py").symlink_to(self.root / "test_result.py")
        self.mapping["requirements"][0]["tests"][0]["path"] = "link.py"
        self.assertTrue(self.check())

    def test_duplicate_requirement_fails(self):
        (self.change / "spec.md").write_text("## R1: first\n## R1: duplicate\n")
        self.assertTrue(self.check())

    def test_draft_placeholders_fail(self):
        (self.change / "plan.md").write_text("TODO: verification\n")
        self.assertTrue(self.check())

    def test_manual_requirement_needs_owner_and_reason(self):
        self.mapping["requirements"][0] = {"id": "R1", "verification": "manual"}
        self.assertTrue(self.check())
        self.mapping["requirements"][0].update(owner="reviewer", reason="Physical device interaction")
        self.assertEqual([], self.check())


if __name__ == "__main__":
    unittest.main()
