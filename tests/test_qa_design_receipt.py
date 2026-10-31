import json
from pathlib import Path
import tempfile
import unittest
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'hooks'))
import qa_design_receipt as r

class DesignReceiptTest(unittest.TestCase):
 def test_scope_revision_evidence_and_mismatch(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'figma.png').write_bytes(b'figma');(root/'actual.png').write_bytes(b'actual')
   cell={'node':'1:2','viewport':'pc','verdict':'MATCH','checks':[{'item':'색상','expected':'white','actual':'white'}],'figma_screenshot':'figma.png','actual_screenshot':'actual.png'}
   data={'schema_version':1,'revision':'a'*40,'observed_at':'2026-10-31','source_checked_at':'2026-10-31','source_url':'https://figma.com/file/x','cells':[cell]}
   path=root/'receipt.json';path.write_text(json.dumps(data))
   self.assertEqual(r.validate(path,['1:2'],['pc'],'a'*40,['색상'])['verdict'],'PASS')
   with self.assertRaises(r.ReceiptError):r.validate(path,['1:2'],['pc'],'a'*40,['가려짐'])
   with self.assertRaises(r.ReceiptError):r.validate(path,['1:2'],['mobile'],'a'*40)
   with self.assertRaises(r.ReceiptError):r.validate(path,['1:2'],['pc'],'b'*40)
   cell['checks'][0]['actual']='black';path.write_text(json.dumps(data));self.assertEqual(r.validate(path,['1:2'],['pc'],'a'*40)['verdict'],'FAIL')
   cell['verdict']='MISMATCH';path.write_text(json.dumps(data));self.assertEqual(r.validate(path,['1:2'],['pc'],'a'*40)['verdict'],'FAIL')
   (root/'actual.png').unlink()
   with self.assertRaises(r.ReceiptError):r.validate(path,['1:2'],['pc'],'a'*40)
if __name__=='__main__': unittest.main()
