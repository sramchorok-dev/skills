import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from tests import test_qa_queue as fixture_module
qa_queue = fixture_module.qa_queue

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import qa_doctor


class ReviewFixTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture_module.QueueTests('test_no_ui_no_request')
        self.fixture.setUp()
        self.root, self.db = self.fixture.root, self.fixture.db

    def tearDown(self):
        self.fixture.tearDown()

    def mapping(self, rules, files):
        for name in files:
            p = self.root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('changed')
        p = self.root / 'docs/qa/local-design-map.json'
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({'schema_version': 1, 'rules': rules}))
        self.fixture.git('add', '.')
        self.fixture.git('commit', '-qm', 'change')

    def test_nonvisual_requires_reason_and_browser_scope_but_no_figma(self):
        rule = {'paths': ['utils/*.ts', 'docs/qa/local-design-map.json'], 'cards': ['PRICE'], 'viewports': ['pc'], 'design': 'not-applicable', 'reason': 'Price calculation changes no appearance'}
        self.mapping([rule], ['utils/price.ts'])
        plan = qa_queue.design_plan(self.root)
        self.assertEqual(plan['status'], 'READY')
        self.assertFalse(plan['design_required'])
        self.assertEqual(plan['required_cells'], ['PRICE@pc'])
        rule['reason'] = ''
        self.mapping([rule], ['utils/price.ts'])
        self.assertEqual(qa_queue.design_plan(self.root)['status'], 'BLOCKED')

    def test_distinct_rule_cells_do_not_create_cross_product(self):
        rules = [
            {'paths': ['components/a.tsx', 'docs/qa/local-design-map.json'], 'cards': ['A'], 'figma_nodes': ['1:1'], 'viewports': ['pc'], 'checks': ['color']},
            {'paths': ['components/b.tsx'], 'cards': ['B'], 'figma_nodes': ['2:2'], 'viewports': ['mobile'], 'checks': ['text']},
        ]
        self.mapping(rules, ['components/a.tsx', 'components/b.tsx'])
        plan = qa_queue.design_plan(self.root)
        self.assertEqual(plan['required_cells'], ['A@pc', 'B@mobile'])
        self.assertEqual(plan['design_cells'], [{'node': '1:1', 'viewport': 'pc', 'checks': ['color']}, {'node': '2:2', 'viewport': 'mobile', 'checks': ['text']}])
        manifest = {'environment': {'revisions': {'fe': 'a'*40}}, 'cells': [{'cell_id': 'A@pc'}, {'cell_id': 'B@mobile'}]}
        self.assertEqual(qa_queue.assess_run(plan, manifest, {'counts': {'FAIL': 0}, 'selected_scope_complete': True}, 'a'*40, False, {'verdict': 'PASS'}), 'PASS')

    def test_owner_deadline_shared_link_and_overdue_are_visible(self):
        self.mapping([{'paths': ['utils/*.ts', 'docs/qa/local-design-map.json'], 'cards': ['P'], 'viewports': ['pc'], 'design': 'not-applicable', 'reason': 'logic only'}], ['utils/price.ts'])
        key = qa_queue.enqueue(self.root, self.db)
        with self.assertRaises(ValueError):
            qa_queue.assign(self.root, key, '', '2020-01-01T00:00:00Z', 'https://github.com/sramchorok-dev/gardenstep/issues/1', self.db)
        qa_queue.assign(self.root, key, 'reviewer', '2020-01-01T00:00:00Z', 'https://github.com/sramchorok-dev/gardenstep/issues/1', self.db)
        row = qa_queue.tasks(self.root, self.db)[0]
        self.assertEqual(row['owner'], 'reviewer')
        self.assertTrue(row['overdue'])
        self.assertFalse(row['needs_assignment'])
        report = qa_queue.handoff(self.root, self.db)
        self.assertIn('reviewer', report)
        self.assertIn('OVERDUE', report)
        self.assertIn('/issues/1', report)

    def test_doctor_rejects_missing_script_and_probes_real_adapter(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'hooks.json'
            path.write_text(json.dumps({'hooks': {'Stop': [{'hooks': [{'command': ': gardenstep-local-qa-v1; python3 /missing/qa_queue_hook.py'}]}]}}))
            self.assertFalse(qa_doctor.diagnose(path)['ok'])
            from install_codex_hooks import change
            change(path, 'install')
            self.assertTrue(qa_doctor.diagnose(path)['ok'])

    def test_real_hook_emits_one_json_and_warns_about_unassigned_work(self):
        self.mapping([{'paths': ['utils/*.ts', 'docs/qa/local-design-map.json'], 'cards': ['P'], 'viewports': ['pc'], 'design': 'not-applicable', 'reason': 'logic only'}], ['utils/price.ts'])
        result = subprocess.run([sys.executable, str(ROOT/'hooks/qa_queue_hook.py')], input=json.dumps({'cwd': str(self.root)}), env=dict(os.environ, GARDENSTEP_QA_DB=str(self.db)), capture_output=True, text=True, check=True)
        message = json.loads(result.stdout)['systemMessage']
        self.assertIn('담당 미지정 1건', message)
        self.assertEqual(len(qa_queue.tasks(self.root, self.db)), 1)

    def test_adapter_selftest_does_not_touch_queue(self):
        result = subprocess.run([sys.executable, str(ROOT/'hooks/qa_queue_hook.py'), '--self-test'], capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout)['status'], 'adapter-ready')
