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


if __name__ == "__main__":
    unittest.main()
