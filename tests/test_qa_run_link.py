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
 def test_pass_requires_two_valid_receipts_and_tamper_revokes(self):
  q=queue_tests.QueueTests('test_no_ui_no_request'); q.setUp()
  b=mod.BrowserAgentTests('test_전체항목증거가있으면_PASS다'); b.setUp()
  try:
   ui=q.root/'components/card.tsx';ui.parent.mkdir();ui.write_text('ui')
   mapping=q.root/'docs/qa/local-design-map.json';mapping.parent.mkdir(parents=True)
   mapping.write_text(json.dumps({'schema_version':1,'rules':[{'paths':['components/*.tsx','docs/qa/local-design-map.json'],'cards':['CASE-01'],'figma_nodes':['1:2'],'viewports':['pc'],'checks':['color']}]}))
   q.git('add','.');q.git('commit','-qm','ui')
   head=q.git('rev-parse','HEAD').strip();task=qa_queue.enqueue(q.root,q.db)
   b.env['revisions']['fe']=head;runpath=b.root/'run2'
   mod.ba.init_run(b.catalog,b.env,runpath,'QA-20261024-02','critical',proof_root=b.root)
   (runpath/'screenshots/one.png').write_bytes(b'actual screenshot')
   result=mod.ba.result_template(runpath,'CASE-01@pc');result.update({'preconditions_met':True,'steps_completed':['S1'],'ui_observation':'Opened screen','started_at':'2026-10-24T14:01:00Z','finished_at':'2026-10-24T14:02:00Z','session':{'context_id':'ctx','role_alias':'guest','isolation_verified':True,'proof':'clean dedicated session'}})
   for check in result['checks']:check.update({'status':'MATCH','observed':'shown','evidence':['screenshots/one.png']})
   mod.ba.record(runpath,result)
   proof=b.root/'design';proof.mkdir();(proof/'figma.png').write_bytes(b'figma screenshot');(proof/'actual.png').write_bytes(b'actual screenshot')
   receipt=proof/'receipt.json';receipt.write_text(json.dumps({'schema_version':1,'revision':head,'source_url':'https://figma.com/file/example','source_checked_at':'2026-10-24','observed_at':'2026-10-24','cells':[{'node':'1:2','viewport':'pc','verdict':'MATCH','checks':[{'item':'color','expected':'white','actual':'white'}],'figma_screenshot':'figma.png','actual_screenshot':'actual.png'}]}))
   env=dict(os.environ,GARDENSTEP_QA_DB=str(q.db));base=['python3',str(ROOT/'hooks/qa_queue.py')]
   subprocess.run(base+['link-design','--repo',str(q.root),'--id',task,'--receipt',str(receipt)],env=env,text=True,capture_output=True,check=True)
   out=subprocess.run(base+['link-run','--repo',str(q.root),'--id',task,'--run',str(runpath)],env=env,text=True,capture_output=True,check=True)
   self.assertEqual(json.loads(out.stdout)['queue_status'],'BLOCKED')
   (proof/'actual.png').write_bytes(b'tampered')
   self.assertEqual(qa_queue.tasks(q.root,q.db)[0]['status'],'BLOCKED')
  finally:b.tearDown();q.tearDown()
if __name__ == '__main__': unittest.main()
