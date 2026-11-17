import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = Path(os.environ.get("SDLC_TEST_MODULE", ROOT / "scripts/sdlc.py"))
spec = importlib.util.spec_from_file_location("sdlc", SCRIPT)
sdlc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sdlc)
# Mutations run a copied module; contracts and input fixtures remain unchanged.
sdlc.ROOT = ROOT


class EvidenceContractTest(unittest.TestCase):
    def setUp(self):
        self.bundle = sdlc.read_json(ROOT / "assets/sample-bundle.json")

    def validate(self):
        return sdlc.validate_bundle(self.bundle["manifest"], self.bundle["evidence"], self.bundle["policy"])

    def repin(self):
        digest = sdlc.canonical_hash(self.bundle["manifest"])
        self.bundle["policy"]["manifest_sha256"] = digest
        self.bundle["evidence"]["manifest_sha256"] = digest

    def assert_rejected(self):
        self.assertEqual("FAIL", self.validate()["status"])

    def test_valid_fixture_is_consistency_only_not_approval(self):
        result = self.validate()
        self.assertEqual("PASS", result["status"])
        self.assertEqual("local-validation-only", result["authority"])
        self.assertNotIn("approved", result)

    def test_same_model_is_allowed_but_same_session_is_not(self):
        self.bundle["evidence"]["checks"][1]["reviewer_session_id"] = "author-sample"
        self.assert_rejected()

    def test_blocking_review_finding_prevents_success(self):
        self.bundle["evidence"]["checks"][1]["blocking_findings"] = 1
        self.assert_rejected()

    def test_failed_tests_with_exit_zero_do_not_pass(self):
        self.bundle["evidence"]["checks"][0]["failed"] = 1
        self.assert_rejected()

    def test_missing_review_findings_does_not_mean_zero(self):
        del self.bundle["evidence"]["checks"][1]["blocking_findings"]
        self.assert_rejected()

    def test_empty_execution_does_not_pass(self):
        self.bundle["evidence"]["checks"][0].update(total=0, passed=0)
        self.assert_rejected()

    def test_every_nonpass_state_fails(self):
        for state in ["FAIL", "BLOCKED", "NOT_RUN", "SKIPPED", "CANCELLED", "success", "neutral"]:
            with self.subTest(state=state):
                self.bundle["evidence"]["checks"][0]["status"] = state
                self.assert_rejected()

    def test_skipped_cancelled_and_nonzero_exit_fail(self):
        for field in ["skipped", "cancelled", "exit_code"]:
            with self.subTest(field=field):
                self.setUp()
                self.bundle["evidence"]["checks"][0][field] = 1
                self.assert_rejected()

    def test_wrong_service_sha_and_harness_version_fail(self):
        self.bundle["evidence"]["services"]["example/service"] = "f" * 40
        self.assert_rejected()
        self.setUp()
        self.bundle["evidence"]["harness_version"] = "other"
        self.assert_rejected()

    def test_missing_and_unexpected_checks_fail(self):
        self.bundle["evidence"]["checks"].pop()
        self.assert_rejected()
        self.setUp()
        extra = copy.deepcopy(self.bundle["evidence"]["checks"][0])
        extra["id"] = "unexpected"
        self.bundle["evidence"]["checks"].append(extra)
        self.assert_rejected()

    def test_duplicate_check_source_and_requirement_ids_fail(self):
        for document, field in [("evidence", "checks"), ("manifest", "sources"), ("manifest", "requirements")]:
            with self.subTest(field=field):
                self.setUp()
                self.bundle[document][field].append(copy.deepcopy(self.bundle[document][field][0]))
                self.repin()
                self.assert_rejected()

    def test_required_list_cannot_be_reduced_even_with_recomputed_claim_hash(self):
        self.bundle["manifest"]["required_checks"].pop()
        self.bundle["manifest"]["requirements"][0]["check_ids"].pop()
        self.bundle["evidence"]["checks"].pop()
        self.repin()
        self.assert_rejected()

    def test_manifest_document_edit_invalidates_existing_policy(self):
        self.bundle["manifest"]["document_hashes"]["spec"] = "f" * 64
        self.assert_rejected()

    def test_unknown_requirement_source_and_check_fail(self):
        for field in ["source_ids", "check_ids"]:
            with self.subTest(field=field):
                self.setUp()
                self.bundle["manifest"]["requirements"][0][field] = ["missing"]
                self.repin()
                self.assert_rejected()

    def test_uncovered_check_fails_even_if_execution_is_green(self):
        self.bundle["manifest"]["requirements"][0]["check_ids"].pop()
        self.repin()
        self.assert_rejected()

    def test_dev_identity_changed_between_start_and_end_fails(self):
        self.bundle["evidence"]["checks"][2]["services_after"]["example/service"] = "f" * 40
        self.assert_rejected()

    def test_fake_dev_environment_fails(self):
        self.bundle["evidence"]["checks"][2]["environment"] = "local"
        self.assert_rejected()

    def test_policy_requires_dev_even_if_manifest_hash_was_repinned(self):
        self.bundle["manifest"]["required_checks"].pop()
        self.bundle["manifest"]["requirements"][0]["check_ids"].pop()
        self.bundle["policy"]["required_check_ids"].pop()
        self.bundle["evidence"]["checks"].pop()
        self.repin()
        self.assert_rejected()

    def test_check_kind_cannot_change_to_bypass_review(self):
        self.bundle["evidence"]["checks"][1]["kind"] = "test"
        self.assert_rejected()

    def test_invalid_timestamp_empty_metadata_and_boolean_counts_fail(self):
        for field, value in [("started_at", "2026-02-30T00:00:00Z"), ("finished_at", "2025-12-01T00:00:00Z"),
                             ("command", "  "), ("artifact_sha256", "x" * 64), ("total", True), ("run_id", "")]:
            with self.subTest(field=field):
                self.setUp()
                self.bundle["evidence"]["checks"][0][field] = value
                self.assert_rejected()

    def test_model_prompt_and_judge_metadata_are_required(self):
        for field in ["version", "prompt_version", "judge_version"]:
            with self.subTest(field=field):
                self.setUp()
                del self.bundle["evidence"]["checks"][1]["model"][field]
                self.assert_rejected()

    def test_unknown_review_model_version_is_not_evaluation_evidence(self):
        self.bundle["evidence"]["checks"][1]["model"]["version"] = "unknown"
        self.assert_rejected()

    def test_malformed_document_fails_without_traceback(self):
        self.assertEqual("FAIL", sdlc.validate_bundle([], {}, {})["status"])

    def test_cli_failure_returns_nonzero_and_no_approval(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.bundle["evidence"]["checks"][0]["failed"] = 1
            for name, value in self.bundle.items():
                (root / f"{name}.json").write_text(json.dumps(value))
            run = subprocess.run([sys.executable, str(ROOT / "scripts/sdlc.py"), "validate",
                                  *[arg for name in ("manifest", "evidence", "policy")
                                    for arg in ("--" + name, str(root / f"{name}.json"))]], capture_output=True, text=True)
            self.assertEqual(1, run.returncode)
            self.assertEqual("local-validation-only", json.loads(run.stdout)["authority"])

    def test_duplicate_json_keys_are_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "bad.json"
            path.write_text('{"schema_version":1,"schema_version":1}')
            with self.assertRaises(ValueError):
                sdlc.read_json(path)


class SourceDoctorTest(unittest.TestCase):
    def setUp(self):
        self.data = sdlc.read_json(ROOT / "assets/source-evidence.example.json")

    def complete(self):
        for row in self.data["sources"]:
            row["authentication"]["status"] = "PASS"
            row["read"].update(status="PASS", complete=True, missing_parts=[], revision="observation-v1",
                               content_sha256="a" * 64, artifact_uri="fixture://synthetic",
                               observed_at="2026-01-01T00:00:01Z")

    def test_installation_does_not_prove_authentication_or_read(self):
        result = sdlc.doctor(self.data)
        self.assertEqual("FAIL", result["status"])
        self.assertTrue(all(row["installation"] == "PASS" and not row["ready_claim"] for row in result["sources"]))

    def test_complete_synthetic_record_passes_only_local_validation(self):
        self.complete()
        self.assertEqual("PASS", sdlc.doctor(self.data)["status"])

    def test_missing_provider_partial_pagination_and_attachment_fail(self):
        self.complete()
        self.data["sources"].pop()
        self.assertEqual("FAIL", sdlc.doctor(self.data)["status"])
        self.setUp()
        self.complete()
        self.data["sources"][0]["read"]["missing_parts"] = ["attachment-2", "next-page"]
        self.assertEqual("FAIL", sdlc.doctor(self.data)["status"])

    def test_pass_without_read_hash_is_rejected(self):
        self.complete()
        del self.data["sources"][0]["read"]["content_sha256"]
        self.assertEqual("FAIL", sdlc.doctor(self.data)["status"])

    def test_unknown_fields_cannot_carry_credentials(self):
        self.data["sources"][0]["authentication"]["token"] = "synthetic-secret"
        result = sdlc.doctor(self.data)
        self.assertEqual("FAIL", result["status"])
        self.assertNotIn("synthetic-secret", json.dumps(result))


class RepositoryContractTest(unittest.TestCase):
    def test_contract_does_not_execute_declared_commands(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / ".sdlc").mkdir()
            (root / "docs").mkdir()
            for path in ["CLAUDE.md", "AGENTS.md", "REVIEW.md", "docs/testing.md"]:
                (root / path).write_text("synthetic contract\n")
            config = {"schema_version": 1, "repository": "example/service", "policy_version": "sdlc-v1",
                      "harness_revision": "a" * 40, "change_home": "example/work", "control_repository": "example/control",
                      "verification": {"test_commands": ["touch unexpected"], "eval_commands": [],
                                       "dev_verification": "BLOCKED: unconfigured", "limitations": ["synthetic"]}}
            (root / ".sdlc/repository.json").write_text(json.dumps(config))
            self.assertEqual("PASS", sdlc.repository(root)["status"])
            self.assertFalse((root / "unexpected").exists())
            (root / "REVIEW.md").unlink()
            self.assertEqual("FAIL", sdlc.repository(root)["status"])


if __name__ == "__main__":
    unittest.main()
