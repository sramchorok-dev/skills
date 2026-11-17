import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
import os

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "hooks"))
import guard_sources


class SourceHookTest(unittest.TestCase):
    def setUp(self):
        guard = patch.dict(os.environ, {"GARDENSTEP_TEAM_LOG_DISABLED": "1"})
        guard.start()
        self.addCleanup(guard.stop)

    def test_known_reads_are_quiet(self):
        for tool in ["mcp__figma__get_screenshot", "mcp__notion__notion-fetch", "mcp__dropbox__get_file_contents", "mcp__telegram__get_messages"]:
            with self.subTest(tool=tool):
                self.assertIsNone(guard_sources.decide(tool))

    def test_write_and_unknown_calls_require_separate_authority(self):
        for tool in ["mcp__figma__generate_figma_design", "mcp__notion__create_page", "mcp__dropbox__upload_file",
                     "mcp__telegram__send_message", "mcp__notion__new_unknown_tool", "mcp__figma__get_and_update_design"]:
            with self.subTest(tool=tool):
                self.assertEqual("ask", guard_sources.decide(tool)["hookSpecificOutput"]["permissionDecision"])

    def test_other_tools_are_not_claimed_as_guarded(self):
        self.assertIsNone(guard_sources.decide("Bash"))
        self.assertIsNone(guard_sources.decide("mcp__github__create_issue"))

    def test_hook_stdio_does_not_echo_tool_payload(self):
        import os
        run = subprocess.run([sys.executable, str(ROOT / "hooks/guard_sources.py")], input=json.dumps({
            "tool_name": "mcp__telegram__send_message", "tool_input": {"text": "synthetic-private-value"}}),
            capture_output=True, text=True, env={**os.environ, "GARDENSTEP_TEAM_LOG_DISABLED": "1"})
        self.assertEqual(0, run.returncode)
        self.assertEqual("ask", json.loads(run.stdout)["hookSpecificOutput"]["permissionDecision"])
        self.assertNotIn("synthetic-private-value", run.stdout)


if __name__ == "__main__":
    unittest.main()
