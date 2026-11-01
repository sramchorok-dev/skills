import importlib.util
from pathlib import Path
import tempfile
import unittest

path = Path(__file__).resolve().parents[1] / 'scripts/audit_tests.py'
spec = importlib.util.spec_from_file_location('audit_dev_pilot', path)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class DevPilotReceiptTest(unittest.TestCase):
    def test_pending_is_visible_without_implying_success(self):
        with tempfile.TemporaryDirectory() as d:
            body = '## 검증\n- 대기: DEV E2E, 담당 JD, QA-20261031-01\n- 결함 감지: 대기\n'
            findings = audit.check_pr_body(body, Path(d), dev_pilot=True)
            self.assertEqual({f['rule'] for f in findings}, {'PR-QA-PENDING', 'PR-MUTATION-PENDING'})
            self.assertTrue(all(f['level'] == audit.WARN for f in findings))
            legacy = audit.check_pr_body(body, Path(d))
            self.assertFalse(any(f['rule'] == 'PR-QA-PENDING' for f in legacy))

    def test_pass_receipt_has_no_pending_warning(self):
        with tempfile.TemporaryDirectory() as d:
            body = '## 검증\n- 완료: DEV Chromium 1건\n- 결함 감지: 불투명 오버레이에서 검사 실패 후 원복\n'
            self.assertEqual(audit.check_pr_body(body, Path(d), dev_pilot=True), [])

    def test_empty_receipt_still_fails(self):
        with tempfile.TemporaryDirectory() as d:
            result = audit.check_pr_body('## 검증\n', Path(d), dev_pilot=True)
            self.assertTrue(any(f['rule'] == 'PR-RECEIPT-EMPTY' and f['level'] == audit.FAIL for f in result))
