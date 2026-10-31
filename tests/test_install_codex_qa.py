import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('installer', Path(__file__).resolve().parents[1] / 'scripts/install_codex_hooks.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

class InstallTest(unittest.TestCase):
 def test_install_idempotent_and_uninstall_preserves_other_hooks(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'hooks.json'; original={'hooks': {'Stop':[{'hooks':[{'type':'command','command':'echo other'}]}]}, 'description':'preserve'}
   p.write_text(json.dumps(original)); first=m.change(p,'install'); second=m.change(p,'install')
   self.assertEqual(first,second)
   uninstalled=m.change(p,'uninstall')
   self.assertEqual(uninstalled['hooks']['Stop'],original['hooks']['Stop'])
   self.assertEqual(uninstalled['description'],'preserve')
if __name__=='__main__': unittest.main()
