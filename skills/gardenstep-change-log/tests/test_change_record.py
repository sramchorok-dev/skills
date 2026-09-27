import datetime as dt
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "change_record.py"
spec = importlib.util.spec_from_file_location("change_record", SCRIPT)
cr = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(cr)


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


FILLED = """---
date: 2026-09-27
branch: feat/cart-coupon
pr:
type: feat
risk: money
rollback: image
tests: [cart.spec.ts]
adr: none
---

# 장바구니에서 쿠폰을 적용한다

## 무엇이 바뀌었나

- 장바구니에 쿠폰 입력칸이 생기고 할인 금액이 합계에 반영된다

## 왜

- 추석 프로모션 요청 (이슈 #120)

## 확인한 것

- cart.spec.ts 쿠폰 적용·만료 쿠폰 거절 통과
"""


class ChangeRecordTest(unittest.TestCase):
    def repo(self, raw: str, branch: str = "feat/cart-coupon") -> Path:
        root = Path(raw)
        git(root, "init", "-q", "-b", "dev")
        git(root, "config", "user.email", "t@example.com")
        git(root, "config", "user.name", "t")
        (root / "README.md").write_text("x", encoding="utf-8")
        git(root, "add", ".")
        git(root, "commit", "-q", "-m", "init")
        git(root, "checkout", "-q", "-b", branch)
        return root

    def test_new_creates_dated_file_named_after_branch_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as raw:
            root = self.repo(raw)
            path = cr.new_record(root, "feat/cart-coupon", "feat", "쿠폰 적용", dt.date(2026, 9, 27))
            self.assertEqual(root / "docs/changes/2026/2026-09-27-feat-cart-coupon.md", path)
            text = path.read_text(encoding="utf-8")
            self.assertIn("branch: feat/cart-coupon", text)
            self.assertIn("# 쿠폰 적용", text)
            again = cr.new_record(root, "feat/cart-coupon", "fix", "", dt.date(2026, 10, 1))
            self.assertEqual(path, again)

    def test_fresh_template_fails_because_what_and_why_are_empty(self):
        with tempfile.TemporaryDirectory() as raw:
            root = self.repo(raw)
            cr.new_record(root, "feat/cart-coupon", "feat", "쿠폰 적용", dt.date(2026, 9, 27))
            problems = cr.check_record(root, "feat/cart-coupon")
            self.assertTrue(any("무엇이 바뀌었나" in p for p in problems), problems)
            self.assertTrue(any("`## 왜`" in p for p in problems), problems)

    def test_filled_record_passes(self):
        with tempfile.TemporaryDirectory() as raw:
            root = self.repo(raw)
            path = root / "docs/changes/2026/2026-09-27-feat-cart-coupon.md"
            path.parent.mkdir(parents=True)
            path.write_text(FILLED, encoding="utf-8")
            self.assertEqual([], cr.check_record(root, "feat/cart-coupon"))

    def test_missing_record_is_reported_with_expected_glob(self):
        with tempfile.TemporaryDirectory() as raw:
            root = self.repo(raw)
            problems = cr.check_record(root, "feat/cart-coupon")
            self.assertEqual(1, len(problems))
            self.assertIn("feat-cart-coupon.md", problems[0])

    def test_placeholder_why_is_not_content(self):
        text = FILLED.replace("- 추석 프로모션 요청 (이슈 #120)", "- <이유>")
        self.assertIn("`## 왜`가 비어 있습니다 — 사용자·이슈에서 받은 이유를 적습니다(추측 금지)",
                      cr.validate_text(text))

    def test_migration_needs_real_rollback(self):
        text = FILLED.replace("type: feat", "type: migration")
        self.assertTrue(any("rds-snapshot" in p for p in cr.validate_text(text)))
        ok = text.replace("rollback: image", "rollback: rds-snapshot")
        self.assertEqual([], cr.validate_text(ok))

    def test_touching_liquibase_file_requires_rollback_even_if_type_is_feat(self):
        with tempfile.TemporaryDirectory() as raw:
            root = self.repo(raw)
            changeset = root / "src/main/resources/db/changelog/changes/0009-x.yaml"
            changeset.parent.mkdir(parents=True)
            changeset.write_text("databaseChangeLog: []", encoding="utf-8")
            path = root / "docs/changes/2026/2026-09-27-feat-cart-coupon.md"
            path.parent.mkdir(parents=True)
            path.write_text(FILLED, encoding="utf-8")
            self.assertTrue(any("rds-snapshot" in p for p in cr.check_record(root, "feat/cart-coupon", "dev")))

    def test_invalid_enum_values_are_reported(self):
        text = FILLED.replace("risk: money", "risk: huge")
        self.assertTrue(any("risk `huge`" in p for p in cr.validate_text(text)))

    def test_set_pr_fills_number(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "r.md"
            path.write_text(FILLED, encoding="utf-8")
            cr.set_pr(path, "1130")
            self.assertIn("pr: 1130", path.read_text(encoding="utf-8"))

    def test_receipt_section_matches_test_gate_titles(self):
        self.assertIsNotNone(cr.receipt_section("## 검증\n- 통과"))
        self.assertIsNotNone(cr.receipt_section("## 🧪 테스트 영수증\n- 통과"))
        self.assertIsNone(cr.receipt_section("## Verification\n- pass"))


if __name__ == "__main__":
    unittest.main()
