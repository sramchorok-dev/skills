import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("model_eval", Path(__file__).resolve().parents[1] / "scripts/run_model_eval.py")
eval_runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eval_runner)

class ModelEvidenceTests(unittest.TestCase):
    def events(self, result=None, skill="bootstrap-eval:ai-native-sdlc-bootstrap"):
        rows = [{"message": {"content": [{"type": "tool_use", "id": "load-1", "name": "Skill", "input": {"skill": skill}}]}}]
        if result is not None:
            rows.append({"message": {"content": [result]}})
        return rows

    def test_unknown_skill_is_not_a_successful_load(self):
        self.assertFalse(eval_runner.skill_load_succeeded(self.events({"type": "tool_result", "tool_use_id": "load-1", "is_error": True, "content": "Unknown skill"})))

    def test_missing_or_unrelated_result_is_not_a_successful_load(self):
        self.assertFalse(eval_runner.skill_load_succeeded(self.events()))
        self.assertFalse(eval_runner.skill_load_succeeded(self.events({"type": "tool_result", "tool_use_id": "another-load", "content": "loaded"})))

    def test_exact_namespace_and_matching_success_are_required(self):
        result = {"type": "tool_result", "tool_use_id": "load-1", "content": "loaded skill"}
        self.assertTrue(eval_runner.skill_load_succeeded(self.events(result)))
        self.assertFalse(eval_runner.skill_load_succeeded(self.events(result, "other:ai-native-sdlc-bootstrap")))

    def test_pairs_need_same_model_and_different_real_sessions(self):
        left = {"execution": "PASS", "model_versions": ["synthetic-model"], "session_id": "one"}
        right = dict(left, session_id="two")
        self.assertTrue(eval_runner.comparison_valid([left, right]))
        for invalid in [dict(right, session_id="one"), dict(right, model_versions=[]), dict(right, model_versions=["another"]), dict(right, session_id=None)]:
            self.assertFalse(eval_runner.comparison_valid([left, invalid]))

if __name__ == '__main__':
    unittest.main()
