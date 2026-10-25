import copy
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading

sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
import browser_agent as ba
import qa_reliability as qr
import qa_fixtures as qf
import ci_metrics as cm
import test_browser_agent as fixtures


class ReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.BrowserAgentTests();self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.f=self.fixture

    def new_run(self, name, result=True):
        env=copy.deepcopy(self.f.env)
        env['runtime']={'browser_version':'test-browser-1','model':'test-model','skill_revision':'test-skill-1'}
        run=self.f.root/name
        ba.init_run(self.f.catalog,env,run,'QA-20261025-'+name,'critical')
        if result:
            (run/'screenshots/one.png').write_bytes(b'unit fixture only')
            value=copy.deepcopy(self.f.result);value['run_id']='QA-20261025-'+name
            value['session']['context_id']='test-context-'+name
            ba.record(run,value)
        return run

    def test_numeric_and_type_safe_grading(self):
        self.assertEqual(qr.grade({'operator':'decimal-equals','value':'13.50'},'13.5'),'MATCH')
        self.assertEqual(qr.grade({'operator':'equals','value':True},1),'MISMATCH')
        self.assertEqual(qr.grade({'operator':'equals','value':{'flag':[True]}},{'flag':[1]}),'MISMATCH')
        for value in ['NaN','Infinity',True,'13,500']:
            with self.assertRaises(ValueError): qr.grade({'operator':'decimal-equals','value':'13.5'},value)

    def test_false_match_rejected_by_recorder(self):
        self.f.catalog['cards'][0]['checks'][0]['grader']={'operator':'equals','value':'independent expected'}
        run=self.new_run('11',False)
        (run/'screenshots/one.png').write_bytes(b'unit fixture only')
        result=copy.deepcopy(self.f.result)
        template=ba.result_template(run,'CASE-01@pc')
        for key in ['run_id','card_fingerprint','catalog_fingerprint']:result[key]=template[key]
        result['checks'][0]['observed_value']='wrong actual'
        with self.assertRaisesRegex(ba.ContractError,'disagrees'): ba.record(run,result)
        result['checks'][0]['status']='MISMATCH'
        self.assertEqual(ba.record(run,result)['verdict'],'FAIL')

    def test_plan_keeps_p0_gaps_and_failed_noncritical(self):
        second=copy.deepcopy(self.f.catalog['cards'][0]);second.update(id='CASE-02',priority='P2',profiles=['full'],journey='J02')
        self.f.catalog['cards'].append(second);self.f.catalog['cards'][0]['spec_gaps']=['missing basis']
        result=qr.plan(self.f.catalog,iter(['J02']),iter(['CASE-02']))
        self.assertEqual(result['selected_ids'],['CASE-02','CASE-01'])
        self.assertIn('changed-journey',result['cards'][0]['reasons'])
        with self.assertRaises(ValueError):qr.plan(self.f.catalog,['TYPO'])

    def test_missing_trials_remain_in_denominator(self):
        run=self.new_run('12')
        result=qr.benchmark([run],3)
        self.assertAlmostEqual(result['first_pass_coverage'],1/3)
        self.assertFalse(result['all_planned_trials_pass'])
        with self.assertRaises(ValueError):qr.benchmark([run,run],3)

    def test_retry_preserves_first_failure_and_defect(self):
        run=self.new_run('13',False);(run/'screenshots/one.png').write_bytes(b'unit fixture only')
        value=copy.deepcopy(self.f.result);value['run_id']='QA-20261025-13'
        value['checks'][0]['status']='MISMATCH';ba.record(run,value)
        value['checks'][0]['status']='MATCH';ba.record(run,value)
        other=self.new_run('14')
        result=qr.benchmark([run,other],2)
        self.assertEqual(result['first_pass_coverage'],0.5)
        self.assertEqual(result['complete_trial_rate'],1)
        self.assertFalse(result['all_planned_trials_pass'])
        self.assertEqual(len(qr.defects(run)['drafts']),1)

    def test_different_runtime_not_compared(self):
        one=self.new_run('15');two=self.new_run('16')
        path=two/'manifest.json';value=ba.read_json(path);value['environment']['runtime']['model']='other';ba.write_json(path,value)
        with self.assertRaisesRegex(ValueError,'incomparable'):qr.benchmark([one,two],2)

    def test_shared_context_cannot_be_counted_as_independent_trials(self):
        one=self.new_run('22');two=self.new_run('23',False)
        (two/'screenshots/one.png').write_bytes(b'unit fixture only')
        value=copy.deepcopy(self.f.result);value['run_id']='QA-20261025-23';value['session']['context_id']='test-context-22'
        ba.record(two,value)
        with self.assertRaisesRegex(ValueError,'reuse a browser context'):qr.benchmark([one,two],2)

    def test_invalid_blocked_timing_is_unknown(self):
        run=self.new_run('21',False)
        result=ba.result_template(run,'CASE-01@pc');result.update(blocked_reason='no fixture',started_at='yesterday',finished_at='today')
        ba.record(run,result)
        self.assertIsNone(qr.benchmark([run],3)['trials'][0]['observed_attempt_seconds'])

    def test_not_run_needs_no_session_for_benchmark(self):
        run=self.new_run('24',False)
        result=ba.result_template(run,'CASE-01@pc');result.update(preconditions_met=True,not_run_reason='budget exhausted');result.pop('session')
        ba.record(run,result)
        self.assertEqual(qr.benchmark([run],3)['trials'][0]['first_verdicts']['CASE-01@pc'],'NOT_RUN')


@contextmanager
def fixture_server(mode='normal'):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_POST(self):
            if mode=='invalid':
                self.send_response(200);self.end_headers();self.wfile.write(b'not-json');return
            self.reply({'leaseKey':self.path.split('/')[3].split('?')[0], 'owner':{'password':'private-test-secret'}})
        def do_DELETE(self): self.reply({'remaining':0})
        def do_GET(self): self.reply(2 if mode=='remaining' else 0)
        def reply(self,value):
            self.send_response(200);self.end_headers();self.wfile.write(json.dumps(value).encode())
    server=HTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:yield 'http://127.0.0.1:'+str(server.server_port)
    finally:server.shutdown();server.server_close();thread.join()


class LeaseTests(unittest.TestCase):
    def test_concurrent_operation_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'lease.json'
            with qf.lease_lock(path):
                with self.assertRaisesRegex(ValueError,'already running'):
                    qf.prepare(path,'http://127.0.0.1:18080','QA-20261025-20','test-token')
            self.assertFalse(path.exists())

    def test_public_origin_cli_rejects_without_creating_lease(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'lease.json'
            result=subprocess.run([sys.executable,qf.__file__,'prepare','--origin','https://dev.example.test','--run-id','QA-20261025-20','--lease-file',str(path)],capture_output=True,text=True)
            self.assertEqual(result.returncode,2)
            self.assertFalse(path.exists())
            self.assertIn('public DEV/prod unsupported',result.stderr)

    def test_only_loopback_origin(self):
        for url in ['https://dev.example.test','http://localhost:8080','http://127.0.0.1:8080/path','http://user@127.0.0.1:80','http://127.0.0.1:80?x=1']:
            with self.assertRaises(ValueError):qf.validate_origin(url)

    def test_lifecycle_and_private_secrets(self):
        with tempfile.TemporaryDirectory() as directory,fixture_server() as origin:
            path=Path(directory)/'lease.json'
            receipt=qf.prepare(path,origin,'QA-20261025-17','test-token')
            self.assertNotIn('private-test-secret',json.dumps(receipt))
            self.assertEqual(path.stat().st_mode&0o777,0o600)
            with self.assertRaises(FileExistsError):qf.prepare(path,origin,'QA-20261025-17','test-token')
            self.assertEqual(qf.operate(path,'cleanup','test-token')['status'],'cleaned')
            self.assertNotIn('private-test-secret',path.read_text())

    def test_invalid_response_retains_intent_and_never_auto_retries(self):
        with tempfile.TemporaryDirectory() as directory,fixture_server('invalid') as origin:
            path=Path(directory)/'lease.json'
            with self.assertRaises(ValueError):qf.prepare(path,origin,'QA-20261025-18','test-token')
            self.assertEqual(qf.load(path)['status'],'prepare-unknown')
            with self.assertRaises(ValueError):qf.operate(path,'paid-order','test-token')

    def test_cleanup_requires_readback_zero(self):
        with tempfile.TemporaryDirectory() as directory,fixture_server('remaining') as origin:
            path=Path(directory)/'lease.json'
            qf.prepare(path,origin,'QA-20261025-19','test-token')
            with self.assertRaises(ValueError):qf.operate(path,'cleanup','test-token')
            self.assertEqual(qf.load(path)['status'],'cleanup-unknown')


class MetricsTests(unittest.TestCase):
    def test_retry_uses_attempt_start_without_inventing_queue_time(self):
        run={'id':1,'run_attempt':2,'status':'completed','created_at':'2026-10-24T00:00:00Z','run_started_at':'2026-10-25T00:00:00Z'}
        jobs={'total_count':1,'jobs':[{'id':2,'run_id':1,'run_attempt':2,'name':'test','status':'completed','conclusion':'success','started_at':'2026-10-25T00:00:05Z','completed_at':'2026-10-25T00:01:05Z'}]}
        result=cm.measure(run,jobs)
        self.assertEqual(result['elapsed_to_last_job_seconds'],65)
        self.assertIsNone(result['initial_wait_seconds'])

    def test_timing_is_not_cost_or_pass_count(self):
        run={'id':1,'run_attempt':1,'status':'completed','created_at':'2026-10-25T00:00:00Z'}
        jobs={'total_count':1,'jobs':[{'id':2,'run_id':1,'run_attempt':1,'name':'test','status':'completed','conclusion':'success','started_at':'2026-10-25T00:00:05Z','completed_at':'2026-10-25T00:01:05Z'}]}
        result=cm.measure(run,jobs)
        self.assertEqual((result['job_seconds_sum'],result['initial_wait_seconds']),(60,5))
        self.assertIsNone(result['test_counts'])
        jobs['total_count']=2
        self.assertIsNone(cm.measure(run,jobs)['job_seconds_sum'])
        self.assertIsNone(cm.measure(run,jobs)['initial_wait_seconds'])
        jobs['jobs'][0]['run_attempt']=2
        with self.assertRaises(ValueError):cm.measure(run,jobs)


if __name__=='__main__':unittest.main()
