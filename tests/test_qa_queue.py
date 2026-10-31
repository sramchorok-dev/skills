import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'hooks'))
import qa_queue

class QueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name) / 'repo'; self.root.mkdir(); self.db = Path(self.tmp.name) / 'q.sqlite'
        self.git('init', '-q'); self.git('config', 'user.email', 'test@example.invalid'); self.git('config', 'user.name', 'test')
        self.git('remote', 'add', 'origin', 'https://github.com/sramchorok-dev/gardenstep.git')
        (self.root / 'README.md').write_text('base'); self.git('add', '.'); self.git('commit', '-qm', 'base')
        self.git('update-ref', 'refs/remotes/origin/dev', 'HEAD')
    def tearDown(self): self.tmp.cleanup()
    def git(self, *args): return subprocess.run(['git', '-C', str(self.root), *args], check=True, capture_output=True, text=True).stdout
    def test_no_ui_no_request(self): self.assertIsNone(qa_queue.enqueue(self.root, self.db))
    def test_idempotence_change_and_private_content(self):
        p = self.root / 'components' / 'card.tsx'; p.parent.mkdir(); p.write_text('unique private text')
        first = qa_queue.enqueue(self.root, self.db); self.assertEqual(first, qa_queue.enqueue(self.root, self.db))
        p.write_text('different'); second = qa_queue.enqueue(self.root, self.db)
        self.assertNotEqual(first, second); rows = qa_queue.tasks(self.root, self.db)
        self.assertEqual(len(rows), 2); self.assertEqual({row['status'] for row in rows}, {'STALE', 'PENDING'})
        self.assertNotIn(b'unique private text', self.db.read_bytes())
    def test_scope_requires_explicit_map(self):
        import json
        p = self.root / 'components' / 'card.tsx'; p.parent.mkdir(); p.write_text('ui')
        self.assertEqual(qa_queue.design_plan(self.root)['status'], 'BLOCKED')
        mapping = self.root / 'docs/qa/local-design-map.json'; mapping.parent.mkdir(parents=True)
        mapping.write_text(json.dumps({'schema_version':1, 'rules':[{'paths':['components/*.tsx','docs/qa/local-design-map.json'], 'cards':['QA-01'], 'figma_nodes':['1:2'], 'viewports':['pc']}]}))
        result = qa_queue.design_plan(self.root)
        self.assertEqual(result['status'], 'READY'); self.assertEqual(result['cards'], ['QA-01'])
        (self.root / 'components/other.css').write_text('css')
        self.assertEqual(qa_queue.design_plan(self.root)['status'], 'BLOCKED')
    def test_receipt_needs_clean_exact_revision_and_scope(self):
        plan={'status':'READY','cards':['C1'],'viewports':['pc','mobile']}
        manifest={'environment':{'revisions':{'fe':'a'*40}},'cells':[{'cell_id':'C1@pc'},{'cell_id':'C1@mobile'}]}
        report={'counts':{'FAIL':0}, 'selected_scope_complete':True}
        self.assertEqual(qa_queue.assess_run(plan,manifest,report,'a'*40,False),'BLOCKED') # Figma receipt still missing
        self.assertEqual(qa_queue.assess_run(plan,manifest,report,'a'*40,True),'BLOCKED')
        self.assertEqual(qa_queue.assess_run(plan,manifest,report,'b'*40,False),'BLOCKED')
        manifest['cells'].pop()
        self.assertEqual(qa_queue.assess_run(plan,manifest,report,'a'*40,False),'BLOCKED')
    def test_shared_code_config_and_assets_are_ui_candidates(self):
        for path in ['hooks/useForm.ts','lib/common.ts','utils/price.ts','package.json','tailwind.config.ts','public/icon.svg','public/font.woff2']:
            self.assertTrue(qa_queue.affects_ui(path), path)
        self.assertFalse(qa_queue.affects_ui('docs/changes/note.md'))
    def test_docs_only_commit_does_not_stale_ui(self):
        p=self.root/'components/card.tsx';p.parent.mkdir();p.write_text('ui')
        self.git('add','components/card.tsx');self.git('commit','-qm','ui')
        first=qa_queue.enqueue(self.root,self.db)
        (self.root/'README.md').write_text('new docs');self.git('add','README.md');self.git('commit','-qm','docs')
        self.assertEqual(first,qa_queue.enqueue(self.root,self.db))
    def test_foreign_repo_rejected(self):
        self.git('remote', 'set-url', 'origin', 'https://example.com/foreign.git')
        with self.assertRaises(ValueError): qa_queue.enqueue(self.root, self.db)

if __name__ == '__main__': unittest.main()
