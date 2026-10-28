import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "history.py"
spec = importlib.util.spec_from_file_location("history", SCRIPT)
h = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(h)

CHANGE = """---
date: 2026-10-01
branch: feat/a
pr: 11
type: feat
risk: {risk}
rollback: image
adr: none
---

# {title}

## 왜

- {why}
"""
ADR = """# 0001. 결제 알림은 큐로

- 상태: accepted
- 날짜: 2026-09-20
"""


class HistoryTest(unittest.TestCase):
    def make(self, raw: str, name: str) -> Path:
        root = Path(raw) / name
        (root / "docs/changes/2026").mkdir(parents=True)
        (root / "docs/decisions").mkdir(parents=True)
        (root / "docs/changes/2026/2026-10-01-feat-a.md").write_text(
            CHANGE.format(risk="money", title="쿠폰 할인 적용", why="추석 프로모션"), encoding="utf-8")
        (root / "docs/changes/2026/2026-10-05-fix-b.md").write_text(
            CHANGE.format(risk="normal", title="배너 오타", why="오타").replace("2026-10-01", "2026-10-05"), encoding="utf-8")
        (root / "docs/decisions/0001-queue.md").write_text(ADR, encoding="utf-8")
        return root

    def test_filters_and_keyword_search_across_repos(self):
        with tempfile.TemporaryDirectory() as raw:
            roots = [self.make(raw, "gardenstep"), self.make(raw, "gardenstep-server")]
            items = [i for r in roots for i in h.load(r, None)]
            self.assertEqual(6, len(items))
            self.assertEqual(2, len(h.select(items, ["쿠폰", "할인"])))
            self.assertEqual(2, len(h.select(items, [], risk="money")))
            self.assertEqual(2, len(h.select(items, [], kind="adr")))
            self.assertEqual(2, len(h.select(items, [], since="2026-10-03", kind="change")))
            self.assertEqual("gardenstep-server", h.select(items, ["오타"])[0]["repo"])

    def test_reads_from_git_ref_not_working_tree(self):
        with tempfile.TemporaryDirectory() as raw:
            root = self.make(raw, "svc")
            for args in (("init", "-q", "-b", "dev"), ("config", "user.email", "t@e.com"), ("config", "user.name", "t"),
                         ("add", "."), ("commit", "-q", "-m", "x")):
                subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
            (root / "docs/changes/2026/2026-10-01-feat-a.md").unlink()
            self.assertEqual(2, len([i for i in h.load(root, "dev") if i["kind"] == "change"]))
            self.assertEqual(1, len([i for i in h.load(root, None) if i["kind"] == "change"]))


if __name__ == "__main__":
    unittest.main()
