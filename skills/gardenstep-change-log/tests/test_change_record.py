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


GOOD_ADR = """# 0002. 결제 알림은 큐로 보낸다

- 상태: accepted
- 날짜: 2026-10-28
- 결정: JD
- 기준: 되돌리기 비쌈 · 대안 검토

## 맥락

알림 발송이 결제 트랜잭션 안에서 돌아 PG 응답이 늦으면 커넥션이 묶인다.

## 결정

발송을 큐로 분리한다.

## 검토한 대안

| 대안 | 버린 이유 |
|---|---|
| 트랜잭션 안 유지 | 커넥션 고갈 |

## 결과

- 좋아지는 것: 결제 지연 격리
- 감수하는 것: 알림이 수 초 늦다
- 다시 볼 조건: 알림 지연 민원이 월 5건을 넘을 때
"""


class AdrRuleTest(unittest.TestCase):
    def repo_with_adr(self, raw: str, existing: bool = True) -> Path:
        root = Path(raw)
        git(root, "init", "-q", "-b", "dev")
        git(root, "config", "user.email", "t@example.com")
        git(root, "config", "user.name", "t")
        if existing:
            d = root / "docs/decisions"
            d.mkdir(parents=True)
            (d / "0001-old.md").write_text(GOOD_ADR.replace("0002", "0001"), encoding="utf-8")
        (root / "README.md").write_text("x", encoding="utf-8")
        git(root, "add", ".")
        git(root, "commit", "-q", "-m", "init")
        git(root, "checkout", "-q", "-b", "feat/queue")
        rec = root / "docs/changes/2026/2026-10-28-feat-queue.md"
        rec.parent.mkdir(parents=True)
        rec.write_text(FILLED.replace("feat/cart-coupon", "feat/queue").replace("adr: none", "adr: docs/decisions/0002-queue.md"),
                       encoding="utf-8")
        return root

    def write_adr(self, root: Path, text: str = GOOD_ADR, name: str = "0002-queue.md") -> None:
        (root / "docs/decisions" / name).write_text(text, encoding="utf-8")

    def test_good_adr_with_matching_record_passes(self):
        with tempfile.TemporaryDirectory() as raw:
            root = self.repo_with_adr(raw)
            self.write_adr(root)
            self.assertEqual([], cr.check_record(root, "feat/queue", "dev"))

    def test_adr_needs_two_criteria(self):
        with tempfile.TemporaryDirectory() as raw:
            root = self.repo_with_adr(raw)
            self.write_adr(root, GOOD_ADR.replace("되돌리기 비쌈 · 대안 검토", "되돌리기 비쌈"))
            self.assertTrue(any("기준" in p for p in cr.check_record(root, "feat/queue", "dev")))

    def test_template_placeholders_fail(self):
        with tempfile.TemporaryDirectory() as raw:
            root = self.repo_with_adr(raw)
            path = cr.new_adr(root, "큐 분리", dt.date(2026, 10, 28))
            self.assertEqual("0002-큐-분리.md", path.name)
            rec = root / "docs/changes/2026/2026-10-28-feat-queue.md"
            rec.write_text(rec.read_text(encoding="utf-8").replace("0002-queue", "0002-큐-분리"), encoding="utf-8")
            problems = cr.check_record(root, "feat/queue", "dev")
            joined = "\n".join(problems)
            for needle in ("결정:", "기준", "맥락", "검토한 대안", "다시 볼 조건"):  # 템플릿 그대로는 통과 못 한다
                self.assertIn(needle, joined)

    def test_number_must_be_next(self):
        with tempfile.TemporaryDirectory() as raw:
            root = self.repo_with_adr(raw)
            self.write_adr(root, GOOD_ADR.replace("0002", "0005"), "0005-queue.md")
            rec = root / "docs/changes/2026/2026-10-28-feat-queue.md"
            rec.write_text(rec.read_text(encoding="utf-8").replace("0002-queue", "0005-queue"), encoding="utf-8")
            self.assertTrue(any("다음 순번 0002" in p for p in cr.check_record(root, "feat/queue", "dev")))

    def test_date_named_decision_doc_is_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            root = self.repo_with_adr(raw)
            self.write_adr(root, GOOD_ADR, "2026-10-28-queue.md")
            self.assertTrue(any("NNNN-짧은-제목" in p for p in cr.check_record(root, "feat/queue", "dev")))

    def test_over_one_page_fails(self):
        with tempfile.TemporaryDirectory() as raw:
            root = self.repo_with_adr(raw)
            self.write_adr(root, GOOD_ADR + "\n".join(f"- 줄 {i}" for i in range(90)) + "\n")
            self.assertTrue(any("한 페이지" in p for p in cr.check_record(root, "feat/queue", "dev")))

    def test_added_adr_requires_record_to_point_at_it(self):
        with tempfile.TemporaryDirectory() as raw:
            root = self.repo_with_adr(raw)
            self.write_adr(root)
            rec = root / "docs/changes/2026/2026-10-28-feat-queue.md"
            rec.write_text(rec.read_text(encoding="utf-8").replace("adr: docs/decisions/0002-queue.md", "adr: none"),
                           encoding="utf-8")
            self.assertTrue(any("`adr:`에 그 경로" in p for p in cr.check_record(root, "feat/queue", "dev")))

    def test_record_pointing_at_missing_adr_fails(self):
        with tempfile.TemporaryDirectory() as raw:
            root = self.repo_with_adr(raw)
            self.assertTrue(any("파일이 없습니다" in p for p in cr.check_record(root, "feat/queue", "dev")))

    def test_editing_accepted_adr_body_fails_but_status_change_is_allowed(self):
        with tempfile.TemporaryDirectory() as raw:
            root = self.repo_with_adr(raw)
            self.write_adr(root)
            old = root / "docs/decisions/0001-old.md"
            text = old.read_text(encoding="utf-8")
            old.write_text(text.replace("발송을 큐로 분리한다.", "발송을 다르게 한다."), encoding="utf-8")
            self.assertTrue(any("본문을 고쳤습니다" in p for p in cr.check_record(root, "feat/queue", "dev")))
            old.write_text(text.replace("- 상태: accepted", "- 상태: superseded by 0002"), encoding="utf-8")
            self.assertEqual([], cr.check_record(root, "feat/queue", "dev"))
            old.write_text(text.replace("- 상태: accepted", "- 상태: superseded by 0009"), encoding="utf-8")
            self.assertTrue(any("0009" in p for p in cr.check_record(root, "feat/queue", "dev")))

    def test_recorded_judgment_silences_the_warning(self):
        with tempfile.TemporaryDirectory() as raw:
            root = self.repo_with_adr(raw, existing=False)
            rec = root / "docs/changes/2026/2026-10-28-feat-queue.md"
            rec.write_text(rec.read_text(encoding="utf-8")
                           .replace("adr: docs/decisions/0002-queue.md", "adr: none (기준 1개: 스키마 변경뿐)")
                           .replace("risk: money", "risk: migration").replace("rollback: image", "rollback: rds-snapshot"),
                           encoding="utf-8")
            self.assertEqual(([], []), cr.review(root, "feat/queue", "dev"))

    def test_new_prefills_migration_defaults(self):
        with tempfile.TemporaryDirectory() as raw:
            root = self.repo_with_adr(raw, existing=False)
            text = cr.new_record(root, "feat/cart-coupon", "feat", "x", dt.date(2026, 9, 27), touched_migration=True).read_text(encoding="utf-8")
            self.assertIn("risk: migration", text)
            self.assertIn("rollback: rds-snapshot", text)

    def test_risky_change_without_adr_only_warns(self):
        with tempfile.TemporaryDirectory() as raw:
            root = self.repo_with_adr(raw, existing=False)
            rec = root / "docs/changes/2026/2026-10-28-feat-queue.md"
            rec.write_text(rec.read_text(encoding="utf-8").replace("adr: docs/decisions/0002-queue.md", "adr: none")
                           .replace("risk: money", "risk: infra"), encoding="utf-8")
            problems, warnings = cr.review(root, "feat/queue", "dev")
            self.assertEqual([], problems)
            self.assertTrue(any("ADR 기준" in w for w in warnings))


class WhyQualityTest(unittest.TestCase):
    def test_filler_and_too_short_why_fail_but_issue_link_passes(self):
        for why in ("개선", "- 리팩터링", "- 정리 필요", "- 요청"):
            text = FILLED.replace("- 추석 프로모션 요청 (이슈 #120)", why)
            self.assertTrue(any("너무 짧거나" in p for p in cr.validate_text(text)), why)
        self.assertEqual([], cr.validate_text(FILLED.replace("- 추석 프로모션 요청 (이슈 #120)", "- 이슈 #120")))


if __name__ == "__main__":
    unittest.main()
