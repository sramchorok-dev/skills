import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('release',Path(__file__).resolve().parents[1]/'scripts/release.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)

class ReleaseTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
  self.git('init','-q');self.git('config','user.name','test');self.git('config','user.email','test@example.invalid')
  self.git('remote','add','origin','https://github.com/sramchorok-dev/gardenstep.git')
  p=self.root/'.github/workflows';p.mkdir(parents=True);(p/'cicd.yml').write_text('name: test\n');(p/'production.yml').write_text('name: production\n')
  self.git('add','.');self.git('commit','-qm','base')
  self.git('update-ref','refs/remotes/origin/main','HEAD');self.git('update-ref','refs/remotes/origin/dev','HEAD')
 def tearDown(self):self.temp.cleanup()
 def git(self,*args):return subprocess.run(['git','-C',str(self.root),*args],check=True,capture_output=True,text=True).stdout.strip()
 def test_plan_is_readonly_and_does_not_guess_live_sha(self):
  result=r.plan(self.root,'prod')
  self.assertEqual(result['branch'],'main');self.assertEqual(result['deployment_need'],'UNKNOWN_CHECK_LIVE_REVISION')
  self.assertFalse(result['actual_deploy_executed']);self.assertIsNone(result['local_dry_run_argv'])
  self.assertEqual(self.git('status','--porcelain'),'')
 def test_unchanged_only_with_observed_full_sha(self):
  sha=self.git('rev-parse','HEAD');self.assertEqual(r.plan(self.root,'dev',sha)['deployment_need'],'UNCHANGED')
  with self.assertRaises(ValueError):r.plan(self.root,'dev','short')
 def test_production_command_reuses_evidence_never_skips_tests(self):
  exe=self.root/'gsdeploy';exe.write_text('must not execute')
  command=r.plan(self.root,'prod',executor=exe)['local_dry_run_argv']
  self.assertIn('--reuse-tested',command);self.assertIn('--dry-run',command);self.assertNotIn('--skip-tests',command)
  self.assertIn('DEPLOY-PROD-'+self.git('rev-parse','HEAD')[:7],command)
 def test_ai_prod_rejects_local_route(self):
  self.git('remote','set-url','origin','git@github.com:sramchorok-dev/gardenstep-ai.git')
  exe=self.root/'gsdeploy';exe.touch()
  with self.assertRaises(ValueError):r.plan(self.root,'prod',executor=exe)
  self.assertEqual(r.plan(self.root,'prod')['workflow'],'.github/workflows/production.yml')
 def test_evidence_requires_same_tree_workflow_and_all_jobs(self):
  p=self.root/'evidence.jsonl';entry={'repo':'gardenstep','tree':'tree','workflow_blob':'wf','result':'success','jobs':['test']}
  p.write_text(json.dumps(entry)+'\n');self.assertIsNone(r.evidence_for(p,'gardenstep','tree','wf',['test','test-matrix']))
  entry['jobs'].append('test-matrix');p.write_text(json.dumps(entry)+'\n')
  self.assertIsNotNone(r.evidence_for(p,'gardenstep','tree','wf',['test','test-matrix']))
  self.assertIsNone(r.evidence_for(p,'gardenstep','changed','wf',['test']))
  self.assertIsNone(r.evidence_for(p,'gardenstep','tree','changed',['test']))
 def test_postqa_requires_exact_identity_not_success_label(self):
  row={'displayTitle':'postqa-123-2','databaseId':456,'attempt':3,'status':'completed','conclusion':'success','url':'https://github.com/x'}
  self.assertEqual(r.qa_verdict([row],'123','2','a'*40)['status'],'UNVERIFIED')
  identity={'sha':'a'*40,'deployment_run_id':'123','deployment_attempt':'2','qa_run_id':'456','qa_run_attempt':'3'}
  self.assertEqual(r.qa_verdict([row],'123','2','a'*40,identity)['status'],'PASS')
  identity['sha']='b'*40;self.assertEqual(r.qa_verdict([row],'123','2','a'*40,identity)['status'],'UNVERIFIED')
  self.assertEqual(r.qa_verdict([row,row],'123','2','a'*40)['status'],'AMBIGUOUS')
  self.assertEqual(r.qa_verdict([],'123','2','a'*40)['status'],'MISSING')
  row['conclusion']='cancelled';self.assertEqual(r.qa_verdict([row],'123','2','a'*40)['status'],'FAIL')
  row['status']='queued';self.assertEqual(r.qa_verdict([row],'123','2','a'*40)['status'],'PENDING')
 def test_foreign_repo_rejected(self):
  self.git('remote','set-url','origin','https://github.com/other/gardenstep.git')
  with self.assertRaises(ValueError):r.plan(self.root,'prod')
if __name__=='__main__':unittest.main()
