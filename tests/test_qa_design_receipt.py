import json
from PIL import Image
from pathlib import Path
import tempfile
import unittest
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'hooks'))
import qa_design_receipt as r

class DesignReceiptTest(unittest.TestCase):
 def test_scope_revision_evidence_and_mismatch(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);Image.new('RGB',(2,2),'white').save(root/'figma.png');Image.new('RGB',(2,2),'blue').save(root/'actual.png')
   cell={'node':'1:2','node_url':'https://www.figma.com/design/x?node-id=1-2','viewport':'pc','verdict':'MATCH','checks':[{'item':'색상','expected':'white','actual':'white'}],'figma_screenshot':'figma.png','actual_screenshot':'actual.png'}
   data={'schema_version':1,'revision':'a'*40,'observed_at':'2026-10-31T03:00:00Z','source_checked_at':'2026-10-31T02:59:00Z','source_url':'https://www.figma.com/design/x','source_observer':'qa-agent','independent_source_observation':True,'cells':[cell]}
   path=root/'receipt.json';path.write_text(json.dumps(data))
   self.assertEqual(r.validate(path,['1:2'],['pc'],'a'*40,['색상'])['verdict'],'PASS')
   data['independent_source_observation']=False;path.write_text(json.dumps(data))
   with self.assertRaises(r.ReceiptError):r.validate(path,['1:2'],['pc'],'a'*40)
   data['independent_source_observation']=True;data['source_url']='https://example.com/design/x';path.write_text(json.dumps(data))
   with self.assertRaises(r.ReceiptError):r.validate(path,['1:2'],['pc'],'a'*40)
   data['source_url']='https://www.figma.com/design/x';cell['node_url']='https://figma.com/design/wrong?node-id=1-2';path.write_text(json.dumps(data))
   with self.assertRaises(r.ReceiptError):r.validate(path,['1:2'],['pc'],'a'*40)
   cell['node_url']='https://figma.com/design/x?node-id=1-3';path.write_text(json.dumps(data))
   with self.assertRaises(r.ReceiptError):r.validate(path,['1:2'],['pc'],'a'*40)
   cell['node_url']='https://figma.com/design/x?node-id=1-2';path.write_text(json.dumps(data))
   (root/'actual.png').write_bytes(b'\x89PNG\r\n\x1a\ninvalid')
   with self.assertRaises(r.ReceiptError):r.validate(path,['1:2'],['pc'],'a'*40)
   Image.new('RGB',(2,2),'blue').save(root/'actual.png')
   with self.assertRaises(r.ReceiptError):r.validate(path,['1:2'],['pc'],'a'*40,['가려짐'])
   with self.assertRaises(r.ReceiptError):r.validate(path,['1:2'],['mobile'],'a'*40)
   with self.assertRaises(r.ReceiptError):r.validate(path,['1:2'],['pc'],'b'*40)
   cell['checks'][0]['actual']='black';path.write_text(json.dumps(data));self.assertEqual(r.validate(path,['1:2'],['pc'],'a'*40)['verdict'],'FAIL')
   cell['verdict']='MISMATCH';path.write_text(json.dumps(data));self.assertEqual(r.validate(path,['1:2'],['pc'],'a'*40)['verdict'],'FAIL')
   (root/'actual.png').unlink()
   with self.assertRaises(r.ReceiptError):r.validate(path,['1:2'],['pc'],'a'*40)
if __name__=='__main__': unittest.main()
