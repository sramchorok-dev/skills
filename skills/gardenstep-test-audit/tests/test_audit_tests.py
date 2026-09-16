import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


SKILL_ROOT = Path(__file__).resolve().parents[1]


def load_module():
    path = SKILL_ROOT / "scripts" / "audit_tests.py"
    spec = importlib.util.spec_from_file_location("audit_tests", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


audit = load_module()


def write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def fe_repo(root: Path) -> None:
    write(root, "package.json", '{"name": "gardenstep-frontend"}')
    write(root, "playwright.config.ts", "export default {};")


def admin_repo(root: Path) -> None:
    write(root, "package.json", '{"name": "gardenstep-admin"}')


def server_repo(root: Path) -> None:
    write(root, "build.gradle", "plugins { id 'java' }")


GOOD_BROWSER_SPEC = """import { test, expect } from '@playwright/test';
test('쿠폰 코드를 적용하면 할인된 합계가 표시된다', async ({ page }) => {
  await page.goto('/coupon');
  await page.getByTestId('tier2-coupon-input').fill('WELCOME10');
  await page.getByTestId('tier2-coupon-apply').click();
  await expect(page.getByTestId('tier2-coupon-total')).toHaveText('9000');
});
test('만료된 쿠폰은 적용되지 않고 사유가 표시된다', async ({ page }) => {
  await page.goto('/coupon');
  await page.getByTestId('tier2-coupon-input').fill('OLD5');
  await page.getByTestId('tier2-coupon-apply').click();
  await expect(page.getByTestId('tier2-coupon-reason')).toHaveText('만료');
});
"""

GOOD_UNIT_SPEC = """import { test, expect } from '@playwright/test';
import { applyCoupon } from '../../lib/tier2/coupon';
test('10% 쿠폰은 10,000원을 9,000원으로 만든다', () => {
  expect(applyCoupon(10000, 'WELCOME10').total).toBe(9000);
});
"""


class RepoKindTest(unittest.TestCase):
    def test_detects_each_repo_kind(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fe_repo(root)
            self.assertEqual("fe", audit.detect_repo_kind(root))
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            admin_repo(root)
            self.assertEqual("admin", audit.detect_repo_kind(root))
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            server_repo(root)
            self.assertEqual("server", audit.detect_repo_kind(root))
        with tempfile.TemporaryDirectory() as raw:
            self.assertEqual("unknown", audit.detect_repo_kind(Path(raw)))


class ClassifyTest(unittest.TestCase):
    def test_fe_paths(self):
        cases = {
            "tests/e2e/tier2-coupon.spec.ts": "test-browser",
            "tests/e2e/tier2-coupon.unit.spec.ts": "test-unit",
            "tests/e2e/helpers/tier2.ts": "test-helper",
            "app/coupon/page.tsx": "source-ui",
            "containers/coupon/CouponClient.tsx": "source-ui",
            "components/Button.tsx": "source-ui",
            "hooks/useCoupon.ts": "source-ui",
            "lib/tier2/coupon.ts": "source-logic",
            "utils/format.ts": "source-logic",
            "api/tier2.ts": "source-logic",
            ".github/workflows/cicd.yml": "ci",
            "docs/releases/x.md": "docs",
            "README.md": "docs",
            "package-lock.json": "other",
        }
        for path, expected in cases.items():
            self.assertEqual(expected, audit.classify_file("fe", path), path)

    def test_admin_paths(self):
        cases = {
            "tests/e2e/tier2-operations.spec.ts": "test-browser",
            "lib/orderStatus.test.ts": "test-unit",
            "app/(dashboard)/orders/page.tsx": "source-ui",
            "components/OrderTable.tsx": "source-ui",
            "lib/orderStatus.ts": "source-logic",
        }
        for path, expected in cases.items():
            self.assertEqual(expected, audit.classify_file("admin", path), path)

    def test_server_paths(self):
        base = "src/main/java/ai/gardenstep/gardenstepserver/application/tier2/order/"
        tbase = "src/test/java/ai/gardenstep/gardenstepserver/application/tier2/order/"
        cases = {
            base + "presentation/Tier2OrderController.java": "source-api",
            base + "presentation/dto/request/Tier2OrderCreateRequest.java": "source-api",
            base + "service/Tier2OrderWriter.java": "source-domain",
            base + "domain/Tier2Order.java": "source-domain",
            "src/main/resources/db/changelog/changes/0031-add-coupon.yaml": "schema",
            "src/main/resources/application-dev.yml": "config",
            tbase + "presentation/Tier2OrderControllerTest.java": "test-api",
            tbase + "service/Tier2OrderWriterIntegrationTest.java": "test-integration",
            tbase + "service/Tier2OrderWriterTest.java": "test-unit",
            "src/test/java/ai/gardenstep/gardenstepserver/architecture/Tier2ArchitectureTest.java": "test-contract",
            "src/test/resources/tier2/layout/v232/original.json": "test-fixture",
            "build.gradle": "config",
        }
        for path, expected in cases.items():
            self.assertEqual(expected, audit.classify_file("server", path), path)


class RequiredRulesFeTest(unittest.TestCase):
    def run_audit(self, root: Path, changed: list[str], pr_body: str | None = None) -> dict:
        return audit.audit(root, changed=changed, pr_body=pr_body)

    def test_ui_change_without_browser_spec_fails(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fe_repo(root)
            write(root, "containers/coupon/CouponClient.tsx", "export default () => null;")
            report = self.run_audit(root, ["M containers/coupon/CouponClient.tsx"])
            rule = next(r for r in report["rules"] if r["id"] == "FE-E2E")
            self.assertFalse(rule["satisfied"])
            self.assertEqual("FAIL", report["verdict"])

    def test_ui_change_with_browser_spec_passes_rule(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fe_repo(root)
            write(root, "containers/coupon/CouponClient.tsx", "export default () => null;")
            write(root, "tests/e2e/tier2-coupon.spec.ts", GOOD_BROWSER_SPEC)
            report = self.run_audit(
                root, ["M containers/coupon/CouponClient.tsx", "A tests/e2e/tier2-coupon.spec.ts"]
            )
            rule = next(r for r in report["rules"] if r["id"] == "FE-E2E")
            self.assertTrue(rule["satisfied"])
            self.assertIn("tests/e2e/tier2-coupon.spec.ts", rule["evidence"])

    def test_logic_change_requires_unit_spec(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fe_repo(root)
            write(root, "lib/tier2/coupon.ts", "export const x = 1;")
            report = self.run_audit(root, ["A lib/tier2/coupon.ts"])
            rule = next(r for r in report["rules"] if r["id"] == "FE-UNIT")
            self.assertFalse(rule["satisfied"])
            write(root, "tests/e2e/tier2-coupon.unit.spec.ts", GOOD_UNIT_SPEC)
            report = self.run_audit(
                root, ["A lib/tier2/coupon.ts", "A tests/e2e/tier2-coupon.unit.spec.ts"]
            )
            rule = next(r for r in report["rules"] if r["id"] == "FE-UNIT")
            self.assertTrue(rule["satisfied"])

    def test_new_page_without_flag_off_case_warns(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fe_repo(root)
            write(root, "app/coupon/page.tsx", "export default () => null;")
            write(root, "tests/e2e/tier2-coupon.spec.ts", GOOD_BROWSER_SPEC)
            report = self.run_audit(
                root, ["A app/coupon/page.tsx", "A tests/e2e/tier2-coupon.spec.ts"]
            )
            rule = next(r for r in report["rules"] if r["id"] == "FE-FLAG-OFF")
            self.assertFalse(rule["satisfied"])
            self.assertEqual("WARN", rule["level"])

    def test_new_page_behind_flag_without_flag_off_case_fails(self):
        flagged = "import { notFound } from 'next/navigation';\nexport default function Page() { if (!isTier2Enabled()) notFound(); return null; }\n"
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fe_repo(root)
            write(root, "app/coupon/page.tsx", flagged)
            write(root, "tests/e2e/tier2-coupon.spec.ts", GOOD_BROWSER_SPEC)
            report = self.run_audit(
                root, ["A app/coupon/page.tsx", "A tests/e2e/tier2-coupon.spec.ts"]
            )
            rule = next(r for r in report["rules"] if r["id"] == "FE-FLAG-OFF")
            self.assertEqual("FAIL", rule["level"])
            self.assertEqual("FAIL", report["verdict"])
            write(root, "tests/e2e/tier2-flag-off.spec.ts", "for (const p of ['/shop', '/coupon']) {}")
            report = self.run_audit(
                root, ["A app/coupon/page.tsx", "A tests/e2e/tier2-coupon.spec.ts", "M tests/e2e/tier2-flag-off.spec.ts"]
            )
            rule = next(r for r in report["rules"] if r["id"] == "FE-FLAG-OFF")
            self.assertTrue(rule["satisfied"])

    def test_browser_spec_without_failure_path_warns(self):
        happy_only = """import { test, expect } from '@playwright/test';
test('쿠폰 코드를 적용하면 할인된 합계가 표시된다', async ({ page }) => {
  await page.goto('/coupon');
  await expect(page.getByTestId('tier2-coupon-total')).toHaveText('9000');
});
"""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fe_repo(root)
            write(root, "containers/coupon/CouponClient.tsx", "export default () => null;")
            write(root, "tests/e2e/tier2-coupon.spec.ts", happy_only)
            report = self.run_audit(
                root, ["M containers/coupon/CouponClient.tsx", "A tests/e2e/tier2-coupon.spec.ts"]
            )
            rule = next(r for r in report["rules"] if r["id"] == "FAIL-PATH")
            self.assertFalse(rule["satisfied"])
            self.assertEqual("WARN", rule["level"])

    def test_skipped_failure_title_does_not_count_as_failure_path(self):
        skipped_only = """import { test, expect } from '@playwright/test';
test('쿠폰 코드를 적용하면 할인된 합계가 표시된다', async ({ page }) => {
  await expect(page.getByTestId('tier2-coupon-total')).toHaveText('9000');
});
test.skip('만료 쿠폰은 거절된다', async ({ page }) => {
  await expect(page.getByTestId('tier2-coupon-total')).toHaveText('10000');
});
"""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fe_repo(root)
            write(root, "containers/coupon/CouponClient.tsx", "export default () => null;")
            write(root, "tests/e2e/tier2-coupon.spec.ts", skipped_only)
            report = self.run_audit(
                root, ["M containers/coupon/CouponClient.tsx", "A tests/e2e/tier2-coupon.spec.ts"]
            )
            rule = next(r for r in report["rules"] if r["id"] == "FAIL-PATH")
            self.assertFalse(rule["satisfied"])

    def test_docs_only_change_passes_without_rules(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fe_repo(root)
            write(root, "docs/releases/note.md", "# note")
            report = self.run_audit(root, ["A docs/releases/note.md"])
            self.assertEqual("PASS", report["verdict"])
            self.assertTrue(all(r["satisfied"] for r in report["rules"]))


class RequiredRulesServerTest(unittest.TestCase):
    def test_controller_change_requires_api_test(self):
        base = "src/main/java/ai/gardenstep/gardenstepserver/application/tier2/coupon/"
        tbase = "src/test/java/ai/gardenstep/gardenstepserver/application/tier2/coupon/"
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            server_repo(root)
            write(root, base + "presentation/Tier2CouponController.java", "class Tier2CouponController {}")
            report = audit.audit(root, changed=["A " + base + "presentation/Tier2CouponController.java"])
            rule = next(r for r in report["rules"] if r["id"] == "SRV-API")
            self.assertFalse(rule["satisfied"])
            self.assertEqual("FAIL", report["verdict"])
            api_test = """import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
class Tier2CouponControllerTest {
  @Autowired MockMvc mockMvc;
  @Test @DisplayName("[API] 알 수 없는 쿠폰은 404를 돌려준다")
  void unknownCoupon() throws Exception {
    mockMvc.perform(get("/tier2/coupons/NOPE")).andExpect(status().isNotFound());
  }
}
"""
            write(root, tbase + "presentation/Tier2CouponControllerTest.java", api_test)
            report = audit.audit(
                root,
                changed=[
                    "A " + base + "presentation/Tier2CouponController.java",
                    "A " + tbase + "presentation/Tier2CouponControllerTest.java",
                ],
            )
            rule = next(r for r in report["rules"] if r["id"] == "SRV-API")
            self.assertTrue(rule["satisfied"])
            fail_path = next(r for r in report["rules"] if r["id"] == "FAIL-PATH")
            self.assertTrue(fail_path["satisfied"])

    def test_service_change_requires_any_test(self):
        base = "src/main/java/ai/gardenstep/gardenstepserver/application/tier2/coupon/"
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            server_repo(root)
            write(root, base + "service/Tier2CouponService.java", "class Tier2CouponService {}")
            report = audit.audit(root, changed=["A " + base + "service/Tier2CouponService.java"])
            rule = next(r for r in report["rules"] if r["id"] == "SRV-DOMAIN")
            self.assertFalse(rule["satisfied"])

    def test_schema_change_without_integration_test_warns(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            server_repo(root)
            write(root, "src/main/resources/db/changelog/changes/0031-coupon.yaml", "databaseChangeLog: []")
            report = audit.audit(root, changed=["A src/main/resources/db/changelog/changes/0031-coupon.yaml"])
            rule = next(r for r in report["rules"] if r["id"] == "SRV-SCHEMA")
            self.assertFalse(rule["satisfied"])
            self.assertEqual("WARN", rule["level"])


class SmellTsTest(unittest.TestCase):
    def smells_for(self, kind: str, rel: str, text: str) -> list[dict]:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            if kind == "fe":
                fe_repo(root)
            else:
                admin_repo(root)
            write(root, rel, text)
            return audit.scan_smells(kind, root, [rel])

    def rules(self, smells: list[dict]) -> set[str]:
        return {s["rule"] for s in smells}

    def test_detects_only_and_fixme(self):
        text = "import { test, expect } from '@playwright/test';\ntest.only('a', async () => { expect(1).toBe(1); });\ntest.fixme('b', async () => {});\n"
        found = self.rules(self.smells_for("fe", "tests/e2e/tier2-x.spec.ts", text))
        self.assertIn("S-ONLY", found)
        self.assertIn("S-FIXME", found)

    def test_skip_without_condition_or_reason_fails_but_env_guard_is_allowed(self):
        bad = "import { test } from '@playwright/test';\ntest.skip('만료 쿠폰', async ({ page }) => { await page.goto('/'); });\n"
        good = (
            "import { test, expect } from '@playwright/test';\n"
            "test.skip(process.env.TIER2_REMOTE_MODE !== 'true', 'remote 서버 계약 검증');\n"
            "test('원격 계약을 지킨다', async ({ page }) => { await expect(page.getByTestId('x')).toBeVisible(); });\n"
        )
        self.assertIn("S-SKIP", self.rules(self.smells_for("fe", "tests/e2e/tier2-a.spec.ts", bad)))
        self.assertNotIn("S-SKIP", self.rules(self.smells_for("fe", "tests/e2e/tier2-b.spec.ts", good)))

    def test_hard_wait_and_bad_selectors(self):
        text = (
            "import { test, expect } from '@playwright/test';\n"
            "test('쿠폰 버튼을 누르면 합계가 바뀐다', async ({ page }) => {\n"
            "  await page.waitForTimeout(1000);\n"
            "  await page.locator('.coupon-btn').click();\n"
            "  await page.locator('#total').click();\n"
            "  await page.locator('xpath=//button').click();\n"
            "  await page.locator('body').click();\n"
            "  await expect(page.getByTestId('tier2-coupon-total')).toHaveText('9000');\n"
            "});\n"
        )
        smells = self.smells_for("fe", "tests/e2e/tier2-x.spec.ts", text)
        self.assertIn("S-HARD-WAIT", self.rules(smells))
        selector_lines = sorted(s["line"] for s in smells if s["rule"] == "S-SELECTOR")
        self.assertEqual([4, 5, 6], selector_lines)

    def test_text_and_role_selectors_warn(self):
        text = (
            "import { test, expect } from '@playwright/test';\n"
            "test('메뉴가 보인다', async ({ page }) => {\n"
            "  await expect(page.getByRole('navigation')).toBeVisible();\n"
            "  await expect(page.getByText('적용')).toBeVisible();\n"
            "});\n"
        )
        smells = self.smells_for("fe", "tests/e2e/tier2-x.spec.ts", text)
        warn = [s for s in smells if s["rule"] == "S-SELECTOR-EXCEPTION"]
        self.assertEqual(2, len(warn))
        self.assertTrue(all(s["level"] == "WARN" for s in warn))

    def test_tautology_and_weak_assertions(self):
        text = (
            "import { test, expect } from '@playwright/test';\n"
            "test('쿠폰이 동작한다', async ({ page }) => {\n"
            "  expect(true).toBe(true);\n"
            "  expect(result).toBeTruthy();\n"
            "  expect(other).toBeDefined();\n"
            "});\n"
        )
        smells = self.smells_for("fe", "tests/e2e/tier2-x.spec.ts", text)
        self.assertIn("S-TAUTOLOGY", self.rules(smells))
        weak = [s for s in smells if s["rule"] == "S-WEAK-ASSERT"]
        self.assertEqual(2, len(weak))
        self.assertEqual("WARN", weak[0]["level"])

    def test_test_without_assertion_fails(self):
        text = (
            "import { test, expect } from '@playwright/test';\n"
            "test('페이지에 들어간다', async ({ page }) => {\n"
            "  await page.goto('/coupon');\n"
            "  await page.getByTestId('tier2-coupon-apply').click();\n"
            "});\n"
            "test('합계가 보인다', async ({ page }) => {\n"
            "  await expect(page.getByTestId('tier2-coupon-total')).toBeVisible();\n"
            "});\n"
        )
        smells = self.smells_for("fe", "tests/e2e/tier2-x.spec.ts", text)
        no_assert = [s for s in smells if s["rule"] == "S-NO-ASSERT"]
        self.assertEqual(1, len(no_assert))
        self.assertEqual(2, no_assert[0]["line"])

    def test_helper_with_assertion_counts_as_assertion(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fe_repo(root)
            write(root, "tests/e2e/helpers/tier2.ts", "import { expect } from '@playwright/test';\nexport async function fillWizardUpToStyle(page) { await expect(page.getByTestId('x')).toBeVisible(); }\n")
            text = (
                "import { test, expect } from '@playwright/test';\n"
                "import { fillWizardUpToStyle } from './helpers/tier2';\n"
                "async function reachCart(page) { await page.goto('/cart'); await expect(page.getByTestId('tier2-cart-page')).toBeVisible(); }\n"
                "test('위저드를 스타일까지 완주한다', async ({ page }) => { await fillWizardUpToStyle(page); });\n"
                "test('카트에 도달한다', async ({ page }) => { await reachCart(page); });\n"
                "test('재시도 횟수가 2 이상이다', async ({ page }) => { let n = 0; await expect.poll(() => n).toBeGreaterThanOrEqual(2); });\n"
                "test('아무것도 확인하지 않는다', async ({ page }) => { await page.goto('/'); });\n"
            )
            write(root, "tests/e2e/tier2-x.spec.ts", text)
            smells = audit.scan_smells("fe", root, ["tests/e2e/tier2-x.spec.ts"])
            no_assert = [s["line"] for s in smells if s["rule"] == "S-NO-ASSERT"]
            self.assertEqual([7], no_assert)

    def test_unit_spec_using_page_fixture_fails(self):
        text = (
            "import { test, expect } from '@playwright/test';\n"
            "test('계산이 맞다', async ({ page }) => {\n"
            "  expect(applyCoupon(10000, 'A').total).toBe(9000);\n"
            "});\n"
        )
        smells = self.smells_for("fe", "tests/e2e/tier2-x.unit.spec.ts", text)
        self.assertIn("S-UNIT-USES-PAGE", self.rules(smells))

    def test_self_referential_expectation_warns(self):
        text = (
            "import { test, expect } from '@playwright/test';\n"
            "test('같은 값을 돌려준다', () => {\n"
            "  expect(applyCoupon(10000, 'A').total).toBe(applyCoupon(10000, 'A').total);\n"
            "});\n"
        )
        smells = self.smells_for("fe", "tests/e2e/tier2-x.unit.spec.ts", text)
        self.assertIn("S-SELF-REFERENCE", self.rules(smells))

    def test_expected_value_computed_by_source_function_warns(self):
        text = (
            "import { test, expect } from '@playwright/test';\n"
            "import { applyCoupon } from '../../lib/tier2/coupon';\n"
            "import { seedCart } from './helpers/tier2';\n"
            "test('같은 값을 돌려준다', () => {\n"
            "  const r = applyCoupon(10000, 'A');\n"
            "  expect(r.total).toBe(applyCoupon(10000, 'A').total);\n"
            "  expect(seedCart([])).toEqual(seedCart([]));\n"
            "});\n"
        )
        smells = self.smells_for("fe", "tests/e2e/tier2-x.unit.spec.ts", text)
        hits = [s for s in smells if s["rule"] == "S-SELF-REFERENCE"]
        self.assertEqual([6, 7], sorted(s["line"] for s in hits))

    def test_vague_title_warns_and_korean_sentence_passes(self):
        vague = "import { test, expect } from '@playwright/test';\ntest('coupon works', () => { expect(1).toBe(2); });\n"
        clear = "import { test, expect } from '@playwright/test';\ntest('만료 쿠폰은 적용되지 않는다', () => { expect(f()).toBe(2); });\n"
        self.assertIn("S-TITLE", self.rules(self.smells_for("fe", "tests/e2e/tier2-a.spec.ts", vague)))
        self.assertNotIn("S-TITLE", self.rules(self.smells_for("fe", "tests/e2e/tier2-b.spec.ts", clear)))

    def test_admin_node_test_assert_is_recognised(self):
        text = (
            'import { describe, test } from "node:test";\n'
            'import assert from "node:assert/strict";\n'
            'describe("x", () => {\n'
            '  test("합계를 더한다", () => { assert.equal(sum(1, 2), 3); });\n'
            "});\n"
        )
        smells = self.smells_for("admin", "lib/sum.test.ts", text)
        self.assertNotIn("S-NO-ASSERT", self.rules(smells))


class SmellJavaTest(unittest.TestCase):
    def smells_for(self, rel: str, text: str) -> list[dict]:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            server_repo(root)
            write(root, rel, text)
            return audit.scan_smells("server", root, [rel])

    def rules(self, smells: list[dict]) -> set[str]:
        return {s["rule"] for s in smells}

    REL = "src/test/java/ai/gardenstep/gardenstepserver/application/tier2/coupon/CouponServiceTest.java"

    def test_sleep_disabled_and_tautology(self):
        text = """class CouponServiceTest {
  @Test @DisplayName("[단위] 잠깐 기다린다")
  void waits() throws Exception {
    Thread.sleep(500);
    assertTrue(true);
  }
  @Disabled
  @Test @DisplayName("[단위] 꺼둔 테스트")
  void off() { assertThat(1).isEqualTo(1); }
  @Disabled("CHR-123 재고 계약 확정 후 복구")
  @Test @DisplayName("[단위] 사유 있는 비활성")
  void offWithReason() { assertThat(1).isEqualTo(1); }
}
"""
        smells = self.smells_for(self.REL, text)
        found = self.rules(smells)
        self.assertIn("S-HARD-WAIT", found)
        self.assertIn("S-TAUTOLOGY", found)
        disabled = [s for s in smells if s["rule"] == "S-DISABLED"]
        self.assertEqual(2, len(disabled))
        levels = sorted(s["level"] for s in disabled)
        self.assertEqual(["FAIL", "WARN"], levels)

    def test_method_without_assertion_and_mock_only(self):
        text = """class CouponServiceTest {
  @Test @DisplayName("[단위] 아무것도 확인하지 않는다")
  void nothing() {
    sut.apply(10000, "A");
  }
  @Test @DisplayName("[단위] 호출만 확인한다")
  void mockOnly() {
    sut.apply(10000, "A");
    then(reader).should().read("A");
  }
  @Test @DisplayName("[단위] 결과를 확인한다")
  void real() {
    assertThat(sut.apply(10000, "A").total()).isEqualTo(9000);
  }
  @Test
  void noDisplayName() {
    assertThat(sut.apply(10000, "A").total()).isEqualTo(9000);
  }
}
"""
        smells = self.smells_for(self.REL, text)
        no_assert = [s for s in smells if s["rule"] == "S-NO-ASSERT"]
        self.assertEqual(1, len(no_assert))
        mock_only = [s for s in smells if s["rule"] == "S-MOCK-ONLY"]
        self.assertEqual(1, len(mock_only))
        self.assertEqual("WARN", mock_only[0]["level"])
        self.assertIn("S-DISPLAY-NAME", self.rules(smells))

    def test_java_helper_assertion_display_name_order_and_context_loads(self):
        text = """class CouponControllerTest {
  @Test
  @DisplayName("[API] code가 소문자면 400")
  void create_lowercase_returns400() throws Exception {
    expectBadRequest(post("/admin/coupons"), request("abc"));
  }

  @DisplayName("[API] 이름이 비면 400")
  @Test
  void create_blankName_returns400() throws Exception {
    expectBadRequest(post("/admin/coupons"), request(""));
  }

  @Test
  void contextLoads() {
  }

  private void expectBadRequest(MockHttpServletRequestBuilder builder, Object body) throws Exception {
    mockMvc.perform(builder.content(json(body))).andExpect(status().isBadRequest());
  }
}
"""
        smells = self.smells_for(self.REL.replace("CouponServiceTest", "CouponControllerTest"), text)
        self.assertEqual([], [s for s in smells if s["rule"] == "S-NO-ASSERT"])
        self.assertEqual([], [s for s in smells if s["rule"] == "S-DISPLAY-NAME" and s["line"] < 15])

    def test_spring_boot_test_without_support_base_warns(self):
        text = """@SpringBootTest
class CouponIntegrationTest {
  @Test @DisplayName("[통합] 저장한다")
  void saves() { assertThat(repo.count()).isEqualTo(1); }
}
"""
        smells = self.smells_for(self.REL.replace("CouponServiceTest", "CouponIntegrationTest"), text)
        self.assertIn("S-CONTEXT-CACHE", self.rules(smells))


class PrBodyTest(unittest.TestCase):
    def test_missing_receipt_fails(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fe_repo(root)
            findings = audit.check_pr_body("## What\n뭔가 바꿈\n## Verification\n잘 됩니다", root)
            self.assertIn("PR-RECEIPT-MISSING", {f["rule"] for f in findings})

    def test_receipt_paths_must_exist_and_mutation_line_required(self):
        body = """## 🧪 테스트 영수증
- 바뀐 사용자 동작: 쿠폰 적용
- E2E: `tests/e2e/tier2-coupon.spec.ts` — "쿠폰 코드를 적용하면 할인된 합계가 표시된다"
- 순수 로직: `tests/e2e/tier2-missing.unit.spec.ts`
- 뮤테이션 확인:
"""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fe_repo(root)
            write(root, "tests/e2e/tier2-coupon.spec.ts", GOOD_BROWSER_SPEC)
            findings = audit.check_pr_body(body, root)
            rules = {f["rule"] for f in findings}
            self.assertNotIn("PR-RECEIPT-MISSING", rules)
            missing = [f for f in findings if f["rule"] == "PR-RECEIPT-PATH"]
            self.assertEqual(1, len(missing))
            self.assertIn("tier2-missing.unit.spec.ts", missing[0]["message"])
            self.assertIn("PR-MUTATION-MISSING", rules)

    def test_complete_receipt_has_no_findings(self):
        body = """## 🧪 테스트 영수증
- 바뀐 사용자 동작: 쿠폰 적용
- E2E: `tests/e2e/tier2-coupon.spec.ts` — "쿠폰 코드를 적용하면 할인된 합계가 표시된다"
- 뮤테이션 확인: coupon.ts의 percent 10→20으로 바꾸자 "10% 쿠폰은..." 실패
- 실행: `npx playwright test tests/e2e/tier2-coupon.spec.ts` → 2 passed
"""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fe_repo(root)
            write(root, "tests/e2e/tier2-coupon.spec.ts", GOOD_BROWSER_SPEC)
            self.assertEqual([], audit.check_pr_body(body, root))

    def test_exemption_downgrades_failures(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fe_repo(root)
            write(root, "containers/coupon/CouponClient.tsx", "export default () => null;")
            report = audit.audit(
                root, changed=["M containers/coupon/CouponClient.tsx"], exempt="핫픽스 — 후속 #12에서 테스트 추가"
            )
            self.assertEqual("WARN", report["verdict"])
            self.assertEqual("핫픽스 — 후속 #12에서 테스트 추가", report["exempt"])


class GitAndCliTest(unittest.TestCase):
    def make_git_repo(self, root: Path) -> None:
        subprocess.run(["git", "init", "-q", "-b", "dev"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=root, check=True)
        fe_repo(root)
        write(root, "lib/tier2/cart.ts", "export const a = 1;")
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)
        subprocess.run(["git", "commit", "-qm", "base"], cwd=root, check=True)
        subprocess.run(["git", "checkout", "-qb", "feat/x"], cwd=root, check=True)
        write(root, "lib/tier2/coupon.ts", "export const b = 2;")
        write(root, "tests/e2e/tier2-coupon.unit.spec.ts", GOOD_UNIT_SPEC)
        (root / "lib/tier2/cart.ts").unlink()
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)
        subprocess.run(["git", "commit", "-qm", "feat"], cwd=root, check=True)

    def test_changed_files_from_git_excludes_deletions(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.make_git_repo(root)
            changed = audit.changed_files(root, "dev", "HEAD")
            self.assertEqual(
                ["A lib/tier2/coupon.ts", "A tests/e2e/tier2-coupon.unit.spec.ts"], changed
            )

    def test_cli_json_and_exit_codes(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.make_git_repo(root)
            script = str(SKILL_ROOT / "scripts" / "audit_tests.py")
            ok = subprocess.run(
                ["python3", script, "--repo", str(root), "--base", "dev", "--json"],
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, ok.returncode, ok.stderr)
            payload = json.loads(ok.stdout)
            self.assertEqual("PASS", payload["verdict"])
            self.assertEqual("fe", payload["repo_kind"])

            write(root, "containers/x/X.tsx", "export default () => null;")
            subprocess.run(["git", "add", "-A"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "ui"], cwd=root, check=True)
            bad = subprocess.run(
                ["python3", script, "--repo", str(root), "--base", "dev"],
                capture_output=True,
                text=True,
            )
            self.assertEqual(1, bad.returncode)
            self.assertIn("테스트 점검 영수증", bad.stdout)
            self.assertIn("FAIL", bad.stdout)
            tolerant = subprocess.run(
                ["python3", script, "--repo", str(root), "--base", "dev", "--no-fail"],
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, tolerant.returncode)

    def test_working_tree_mode_includes_uncommitted_and_untracked(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.make_git_repo(root)
            write(root, "playwright.config.ts", "export default { retries: 1 };")  # base에 있던 파일의 커밋 안 한 수정
            write(root, "tests/e2e/tier2-new.unit.spec.ts", GOOD_UNIT_SPEC)  # 미추적 새 파일
            changed = audit.changed_files(root, "dev", head=None)
            self.assertIn("M playwright.config.ts", changed)
            self.assertIn("A lib/tier2/coupon.ts", changed)  # 브랜치에서 추가된 파일은 merge-base 기준 A
            self.assertIn("A tests/e2e/tier2-new.unit.spec.ts", changed)
            self.assertIn("A tests/e2e/tier2-coupon.unit.spec.ts", changed)  # 브랜치 커밋분도 포함
            report = audit.audit(root, base="dev", head=None)
            self.assertEqual("working-tree", report["mode"])
            self.assertEqual("PASS", report["verdict"])

    def test_all_tests_mode_scans_every_test_file_without_rules(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fe_repo(root)
            write(root, "tests/e2e/tier2-good.spec.ts", GOOD_BROWSER_SPEC)
            write(root, "tests/e2e/tier2-bad.spec.ts", "import { test, expect } from '@playwright/test';\ntest('느리게 기다린다', async ({ page }) => { await page.waitForTimeout(500); await expect(page).toHaveURL('/'); });\n")
            write(root, "node_modules/x/tests/e2e/ignored.spec.ts", "test.only('x', () => {});")
            write(root, "containers/shop/ShopClient.tsx", "export default () => null;")
            report = audit.audit(root, all_tests=True)
            self.assertEqual("all-tests", report["mode"])
            self.assertEqual([], report["rules"])
            self.assertEqual(["tests/e2e/tier2-bad.spec.ts", "tests/e2e/tier2-good.spec.ts"], report["changed"]["test-all"])
            self.assertEqual({"S-HARD-WAIT"}, {s["rule"] for s in report["smells"]})
            self.assertEqual("FAIL", report["verdict"])
            text = audit.render_markdown(report)
            self.assertIn("레포 전체 테스트 2개", text)
            script = str(SKILL_ROOT / "scripts" / "audit_tests.py")
            result = subprocess.run(["python3", script, "--repo", str(root), "--all-tests", "--json"], capture_output=True, text=True)
            self.assertEqual(1, result.returncode)
            self.assertEqual("all-tests", json.loads(result.stdout)["mode"])

    def test_cli_accepts_changed_files_list(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fe_repo(root)
            write(root, "docs/a.md", "# a")
            listing = root / "changed.txt"
            listing.write_text("A docs/a.md\n", encoding="utf-8")
            script = str(SKILL_ROOT / "scripts" / "audit_tests.py")
            result = subprocess.run(
                ["python3", script, "--repo", str(root), "--changed-files", str(listing), "--json"],
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual("PASS", json.loads(result.stdout)["verdict"])


class RenderTest(unittest.TestCase):
    def test_markdown_receipt_sections(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            fe_repo(root)
            write(root, "containers/coupon/CouponClient.tsx", "export default () => null;")
            report = audit.audit(root, changed=["M containers/coupon/CouponClient.tsx"])
            text = audit.render_markdown(report)
            for heading in ("테스트 점검 영수증", "변경 분류", "필수 테스트 규칙", "테스트 코드 스멜"):
                self.assertIn(heading, text)
            self.assertIn("FE-E2E", text)


if __name__ == "__main__":
    unittest.main()
