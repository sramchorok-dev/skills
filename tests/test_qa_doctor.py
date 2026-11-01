import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('doctor', Path(__file__).resolve().parents[1] / 'scripts/qa_doctor.py')
doctor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(doctor)


class DoctorTests(unittest.TestCase):
    def test_inspect_only_gardenstep_marker(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'hooks.json'
            path.write_text(json.dumps({'hooks': {'SessionStart': [{'hooks': [{'command': ': gardenstep-local-qa-v1; python3 x'}, {'command': 'unrelated'}]}]}}))
            self.assertEqual(doctor.inspect(path), {'SessionStart': 1, 'Stop': 0})
            path.write_text('{')
            self.assertIsNone(doctor.inspect(path))
