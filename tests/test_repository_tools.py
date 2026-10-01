import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


validator = load("validate_skills", ROOT / "scripts" / "validate_skills.py")
installer = load("install_skills", ROOT / "scripts" / "install.py")
version_check = load("check_plugin_version", ROOT / "scripts" / "check_plugin_version.py")


class RepositoryToolsTest(unittest.TestCase):
    def fixture_repo(self, root: Path) -> None:
        skill = root / "skills" / "example-skill"
        (skill / "evals").mkdir(parents=True)
        (skill / "SKILL.md").write_text(
            "---\nname: example-skill\n"
            "description: Use this skill whenever a user asks for an example deterministic workflow.\n"
            "---\n\n# Example\n",
            encoding="utf-8",
        )
        (skill / "evals" / "evals.json").write_text(
            json.dumps(
                {
                    "skill_name": "example-skill",
                    "evals": [
                        {"id": 1, "prompt": "run example", "expected_output": "done", "files": []}
                    ],
                }
            ),
            encoding="utf-8",
        )
        (root / "catalog.json").write_text(
            json.dumps({"skills": [{"name": "example-skill"}]}), encoding="utf-8"
        )

    def test_valid_repository_passes(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.fixture_repo(root)
            self.assertEqual([], validator.validate(root))

    def plugin_fixture(self, root: Path) -> None:
        (root / ".claude-plugin").mkdir()
        (root / ".claude-plugin" / "plugin.json").write_text(
            json.dumps({"name": "team", "version": "0.1.0"}), encoding="utf-8")
        (root / ".claude-plugin" / "marketplace.json").write_text(
            json.dumps({"name": "m", "owner": {"name": "o"}, "plugins": [{"name": "team", "source": "./"}]}),
            encoding="utf-8")
        (root / "hooks").mkdir()
        (root / "hooks" / "guard.py").write_text("print()\n", encoding="utf-8")
        (root / "hooks" / "hooks.json").write_text(json.dumps({"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
            {"type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/guard.py\""}]}]}}), encoding="utf-8")

    def test_valid_plugin_passes(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.fixture_repo(root)
            self.plugin_fixture(root)
            self.assertEqual([], validator.validate(root))

    def test_plugin_hook_pointing_to_missing_script_fails(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.fixture_repo(root)
            self.plugin_fixture(root)
            (root / "hooks" / "guard.py").unlink()
            self.assertTrue(any("missing hooks/guard.py" in e for e in validator.validate(root)))

    def test_plugin_without_semver_fails(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.fixture_repo(root)
            self.plugin_fixture(root)
            (root / ".claude-plugin" / "plugin.json").write_text('{"name": "team"}', encoding="utf-8")
            self.assertTrue(any("semver" in e for e in validator.validate(root)))

    def test_catalog_drift_fails(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.fixture_repo(root)
            (root / "catalog.json").write_text('{"skills": []}', encoding="utf-8")
            self.assertTrue(any("exactly match" in error for error in validator.validate(root)))

    def test_installer_creates_idempotent_symlink(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.fixture_repo(root)
            target = root / "installed"
            first = installer.install_skill(root / "skills", target, "example-skill")
            second = installer.install_skill(root / "skills", target, "example-skill")
            self.assertEqual("installed", first)
            self.assertEqual("unchanged", second)
            self.assertEqual((root / "skills" / "example-skill").resolve(), (target / "example-skill").resolve())

    def test_installer_refuses_real_directory_overwrite(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.fixture_repo(root)
            target = root / "installed"
            (target / "example-skill").mkdir(parents=True)
            with self.assertRaisesRegex(installer.InstallError, "not a symlink"):
                installer.install_skill(root / "skills", target, "example-skill")


class PluginVersionCheckTest(unittest.TestCase):
    def repo(self, raw: str) -> Path:
        import subprocess
        root = Path(raw)
        run = lambda *a: subprocess.run(["git", "-C", str(root), *a], check=True, capture_output=True)
        run("init", "-q", "-b", "main")
        run("config", "user.email", "t@example.com")
        run("config", "user.name", "t")
        (root / ".claude-plugin").mkdir()
        (root / ".claude-plugin" / "plugin.json").write_text('{"name": "team", "version": "0.1.0"}', encoding="utf-8")
        (root / "hooks").mkdir()
        (root / "hooks" / "guard.py").write_text("print(1)\n", encoding="utf-8")
        (root / "docs").mkdir()
        (root / "docs" / "guide.md").write_text("a\n", encoding="utf-8")
        run("add", "."); run("commit", "-q", "-m", "init"); run("checkout", "-q", "-b", "feat")
        self.run_git = run
        return root

    def test_hook_change_without_bump_fails(self):
        with tempfile.TemporaryDirectory() as raw:
            root = self.repo(raw)
            (root / "hooks" / "guard.py").write_text("print(2)\n", encoding="utf-8")
            self.run_git("commit", "-qam", "change hook")
            problems = version_check.check(root, "main")
            self.assertEqual(1, len(problems))
            self.assertIn("hooks/guard.py", problems[0])

    def test_hook_change_with_bump_passes(self):
        with tempfile.TemporaryDirectory() as raw:
            root = self.repo(raw)
            (root / "hooks" / "guard.py").write_text("print(2)\n", encoding="utf-8")
            (root / ".claude-plugin" / "plugin.json").write_text('{"name": "team", "version": "0.2.0"}', encoding="utf-8")
            self.run_git("commit", "-qam", "change hook and bump")
            self.assertEqual([], version_check.check(root, "main"))

    def test_docs_only_change_needs_no_bump(self):
        with tempfile.TemporaryDirectory() as raw:
            root = self.repo(raw)
            (root / "docs" / "guide.md").write_text("b\n", encoding="utf-8")
            self.run_git("commit", "-qam", "docs")
            self.assertEqual([], version_check.check(root, "main"))


if __name__ == "__main__":
    unittest.main()
