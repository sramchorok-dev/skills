"""Queue must call the actual browser-agent verifier and never promote unrun cells."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import unittest
from tests import test_qa_queue as queue_tests
qa_queue = queue_tests.qa_queue

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('browser_tests', ROOT / 'skills/gardenstep-qa-run/tests/test_browser_agent.py')
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

class QueueLinkTest(unittest.TestCase):
 def test_unrun_browser_run_stays_blocked(self):
  q = queue_tests.QueueTests('test_no_ui_no_no_request' if False else 'test_no_ui_no_request'); q.setUp()
  b = mod.BrowserAgentTests('test_전체항목증거가있으면_PASS다'); b.setUp()
  try:
   ui=q.root/'components/card.tsx'; ui.parent.mkdir(); ui.write_text('ui')
   task=qa_queue.enqueue(q.root,q.db)
   env=dict(os.environ,GARDENSTEP_QA_DB=str(q.db))
   run=subprocess.run(['python3',str(ROOT/'hooks/qa_queue.py'),'link-run','--repo',str(q.root),'--id',task,'--run',str(b.run)],env=env,text=True,capture_output=True,check=True)
   result=json.loads(run.stdout)
   self.assertEqual(result['counts']['NOT_RUN'],1)
   self.assertEqual(result['queue_status'],'BLOCKED')
  finally: b.tearDown(); q.tearDown()
if __name__ == '__main__': unittest.main()
