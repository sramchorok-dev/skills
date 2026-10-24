"""Public CLI receipts must never infer a PASS from an incomplete observation."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).parents[1] / 'scripts/browser_agent.py'
spec = importlib.util.spec_from_file_location('browser_agent', SCRIPT)
ba = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ba)

class BrowserAgentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.catalog = {'schema_version': 1, 'sources': [{'id': 'source-a', 'fingerprint': 'a' * 64}],
            'routes': [], 'fixtures': ['guest'], 'cards': [{'id': 'CASE-01', 'version': 1, 'title': '빈 카트 복구',
            'sources': ['source-a'], 'priority': 'P0', 'journey': 'J01', 'profiles': ['critical', 'smoke'],
            'role': 'guest', 'viewports': ['pc'], 'environment': ['dev', 'prod-readonly'], 'read_only': True,
            'fixtures': ['guest'], 'steps': [{'id':'S1','action':'장바구니 열기'}],
            'checks': [{'id':'C1','expected':'담긴 상품이 없어요.', 'oracle':'source-a'}, {'id':'C2','expected':'둘러보기 링크', 'oracle':'source-a'}],
            'spec_gaps': [], 'side_effects': [], 'cleanup': ['세션 종료']}], 'viewports': {'pc': {'width':1280,'height':720,'device':'chromium-emulated'}}, 'exclusions': []}
        self.env = {'environment':'dev', 'urls':{'fe':'https://dev.example.test'}, 'revisions':{'fe':'a'*40}, 'runner':'JD','tool':'actual-tool+model','checked_at':'2026-10-24T14:00:00Z','verification':'revision endpoint capture','fixtures':{'guest':'available'}}
        (self.root/'evidence').mkdir();(self.root/'evidence/fixture.txt').write_text('dedicated guest fixture verified')
        self.env['fixture_receipts']={'guest':{'owner':'QA context','source_contract':'fixture guide guest isolation','checked_at':'2026-10-24T14:00:00Z','evidence':['evidence/fixture.txt']}}
        self.run = self.root/'run'
        ba.init_run(self.catalog,self.env,self.run,'QA-20261024-01','critical')
        (self.run/'screenshots'/'one.png').write_bytes(b'nonempty screenshot fixture')
        self.result = ba.result_template(self.run, 'CASE-01@pc')
        self.result.update({'preconditions_met':True,'steps_completed':['S1'],'ui_observation':'Cart page opened through browser', 'started_at':'2026-10-24T14:01:00Z','finished_at':'2026-10-24T14:02:00Z', 'session':{'context_id':'test-context','role_alias':'guest-a','isolation_verified':True,'proof':'dedicated clean session verified empty cart'}})
        for c in self.result['checks']:
            c.update({'status':'MATCH','observed':'actual visible content '+c['id'],'evidence':['screenshots/one.png']})
    def tearDown(self): self.tmp.cleanup()
    def test_전체항목증거가있으면_PASS다(self):
        self.assertEqual(ba.record(self.run,self.result)['verdict'],'PASS')
    def test_기준항목이누락되면_기록을거절한다(self):
        self.result['checks'].pop()
        with self.assertRaises(ba.ContractError): ba.record(self.run,self.result)
    def test_증거파일이없으면_PASS를거절한다(self):
        self.result['checks'][0]['evidence']=['screenshots/missing.png']
        with self.assertRaises(ba.ContractError): ba.record(self.run,self.result)
    def test_카드버전이다르면_기록을거절한다(self):
        self.result['card_fingerprint']='b'*64
        with self.assertRaises(ba.ContractError): ba.record(self.run,self.result)
    def test_준비데이터없으면_BLOCKED다(self):
        self.result.update(preconditions_met=False,blocked_reason='전용 주문 fixture 없음',checks=[])
        self.assertEqual(ba.record(self.run,self.result)['verdict'],'BLOCKED')
    def test_배포버전이다르면_resume을거절한다(self):
        env=copy.deepcopy(self.env);env['revisions']['fe']='b'*40
        with self.assertRaises(ba.ContractError): ba.resume(self.run,self.catalog,env)
    def test_원문이바뀌면_resume을거절한다(self):
        cat=copy.deepcopy(self.catalog);cat['sources'][0]['fingerprint']='b'*64
        with self.assertRaises(ba.ContractError): ba.resume(self.run,cat,self.env)
    def test_미실행은분모에남는다(self):
        c=ba.summary(self.run)
        self.assertEqual((c['selected'],c['counts']['NOT_RUN'],c['pass_coverage']), (1,1,0))
    def test_미확인항목은_BLOCKED며분모에남는다(self):
        self.result['checks'][0].update(status='UNKNOWN',observed='기준자료 미확보',evidence=[])
        ba.record(self.run,self.result); c=ba.summary(self.run)
        self.assertEqual((c['counts']['BLOCKED'], c['execution_coverage']), (1,0))
    def test_증거경로탈출을거절한다(self):
        self.result['checks'][0]['evidence']=['../../outside.png']
        with self.assertRaises(ba.ContractError): ba.record(self.run,self.result)
    def test_중복항목과예상값변조를거절한다(self):
        self.result['checks'][1]['id']='C1'
        with self.assertRaises(ba.ContractError): ba.record(self.run,self.result)
    def test_브라우저단계대신_API로PASS할수없다(self):
        self.result['mode']='api-substitution'
        with self.assertRaises(ba.ContractError): ba.record(self.run,self.result)
    def test_누락된UI단계는_PASS할수없다(self):
        self.result['steps_completed']=[]
        self.assertEqual(ba.record(self.run,self.result)['verdict'],'BLOCKED')
    def test_실패후성공해도첫실패를보존한다(self):
        self.result['checks'][0]['status']='MISMATCH';ba.record(self.run,self.result)
        self.result['checks'][0]['status']='MATCH';ba.record(self.run,self.result)
        self.assertEqual(ba.summary(self.run)['historical_failures'],['CASE-01@pc'])
        self.assertEqual(len(list((self.run/'results').glob('*.json'))),2)
    def test_중복카드ID는스키마오류다(self):
        self.catalog['cards'].append(copy.deepcopy(self.catalog['cards'][0]))
        with self.assertRaises(ba.ContractError): ba.validate_catalog(self.catalog)
    def test_사양공백카드는일치로덮을수없다(self):
        self.catalog['cards'][0]['spec_gaps']=['최신 Figma 미확보']
        other=self.root/'other';ba.init_run(self.catalog,self.env,other,'QA-20261024-02','critical')
        result=ba.result_template(other,'CASE-01@pc');result['preconditions_met']=True
        with self.assertRaises(ba.ContractError): ba.record(other,result)
    def test_읽기운영프로필은쓰기카드를거절한다(self):
        self.catalog['cards'][0]['read_only']=False
        self.catalog['cards'][0]['profiles'].append('prod-readonly')
        env=copy.deepcopy(self.env);env['environment']='prod-readonly'
        with self.assertRaises(ba.ContractError): ba.init_run(self.catalog,env,self.root/'prod','QA-20261024-02','prod-readonly')
    def test_스냅샷변조는요약에서도거절한다(self):
        frozen=ba.read_json(self.run/'catalog.json');frozen['cards'][0]['title']='tampered'
        ba.write_json(self.run/'catalog.json',frozen)
        with self.assertRaises(ba.ContractError): ba.summary(self.run)

    def test_첫단계실패로후속미실행이어도_FAIL을보존한다(self):
        self.result['steps_completed']=[]
        self.result['checks'][0]['status']='MISMATCH'
        self.result['checks'][1].update(status='UNKNOWN',observed='이전 버튼 실패로 후속 확인 불가',evidence=[])
        self.assertEqual(ba.record(self.run,self.result)['verdict'],'FAIL')
    def test_격리근거없이_PASS할수없다(self):
        self.result['session']['isolation_verified']=False
        with self.assertRaises(ba.ContractError): ba.record(self.run,self.result)

    def test_명시된증거가변조되면요약을거절한다(self):
        ba.record(self.run,self.result)
        (self.run/'screenshots'/'one.png').write_bytes(b'changed screenshot')
        with self.assertRaises(ba.ContractError): ba.summary(self.run)
    def test_부분핵심선택을전체완료로세지않는다(self):
        second=copy.deepcopy(self.catalog['cards'][0]);second['id']='CASE-02';self.catalog['cards'].append(second)
        other=self.root/'partial';ba.init_run(self.catalog,self.env,other,'QA-20261024-02','critical',ids=['CASE-01'])
        self.assertFalse(ba.summary(other)['whole_critical_complete'])
    def test_정리자원은자기실행소유만등록한다(self):
        entry=dict(id='order-alias',kind='order',owner='OTHER',created_by_cell='CASE-01@pc',cleanup='UI 취소',status='created')
        with self.assertRaises(ba.ContractError):ba.add_resource(self.run,entry)
    def test_미해결기준을불일치로단정할수없다(self):
        self.catalog['cards'][0]['spec_gaps']=['C2 기준 미정'];self.catalog['cards'][0]['checks'][0]['resolved']=True
        other=self.root/'gaps';ba.init_run(self.catalog,self.env,other,'QA-20261024-02','critical')
        (other/'screenshots'/'one.png').write_bytes(b'gap screenshot')
        result=copy.deepcopy(self.result);template=ba.result_template(other,'CASE-01@pc')
        for key in ['run_id','card_fingerprint','catalog_fingerprint']:result[key]=template[key]
        result['checks'][1]['status']='MISMATCH'
        with self.assertRaises(ba.ContractError):ba.record(other,result)
        result['checks'][0]['status']='MISMATCH';result['checks'][1].update(status='UNKNOWN',observed='기준 미정',evidence=[])
        self.assertEqual(ba.record(other,result)['verdict'],'FAIL')

    def test_매핑없는원문은초기화를거절한다(self):
        self.catalog['sources'].append(dict(id='unmapped',kind='sheet-row',fingerprint='b'*64))
        with self.assertRaises(ba.ContractError):ba.init_run(self.catalog,self.env,self.root/'unmapped','QA-20261024-02','critical')
    def test_NA로실제불일치를숨길수없다(self):
        self.catalog['cards'][0]['na_decision']='DECISION-1'
        other=self.root/'na';ba.init_run(self.catalog,self.env,other,'QA-20261024-02','critical')
        result=copy.deepcopy(self.result);template=ba.result_template(other,'CASE-01@pc')
        for key in ['run_id','card_fingerprint','catalog_fingerprint']:result[key]=template[key]
        result.update(na_reason='제외',na_decision='DECISION-1');result['checks'][0]['status']='MISMATCH'
        with self.assertRaises(ba.ContractError):ba.record(other,result)
    def test_없는정리증거는완료처리할수없다(self):
        entry=dict(id='order-own',kind='order',owner='QA-20261024-01',created_by_cell='CASE-01@pc',cleanup='UI 취소',status='cleaned',evidence='missing-file')
        with self.assertRaises(ba.ContractError):ba.add_resource(self.run,entry)
    def test_보존승인은결정자와범위와파일증거를요구한다(self):
        entry=dict(id='order-own',kind='order',owner='QA-20261024-01',created_by_cell='CASE-01@pc',cleanup='보존',status='retained-approved',evidence='screenshots/one.png')
        with self.assertRaises(ba.ContractError):ba.add_resource(self.run,entry)
    def test_정리증거변조는요약을거절한다(self):
        entry=dict(id='order-own',kind='order',owner='QA-20261024-01',created_by_cell='CASE-01@pc',cleanup='UI 취소',status='cleaned',evidence='screenshots/one.png')
        ba.add_resource(self.run,entry)
        (self.run/'screenshots'/'one.png').write_bytes(b'changed cleanup')
        with self.assertRaises(ba.ContractError):ba.summary(self.run)

    def test_준비됐다는라벨만으로fixture준비를통과하지못한다(self):
        self.env['fixture_receipts']={}
        ready=ba.fixture_readiness(self.catalog,self.env,'critical',self.root)
        self.assertEqual(ready['runnable_cells'],[])
        self.assertEqual(ready['blocked_cells'][0]['missing_fixtures'],['guest'])
        with self.assertRaises(ba.ContractError):ba.init_run(self.catalog,self.env,self.root/'no-proof','QA-20261024-02','critical')
    def test_미준비fixture는run을만들되BLOCKED로남긴다(self):
        self.env['fixtures']['guest']='unverified';self.env['fixture_receipts']={}
        other=self.root/'blocked-fixture';ba.init_run(self.catalog,self.env,other,'QA-20261024-02','critical')
        result=ba.result_template(other,'CASE-01@pc');result['blocked_reason']='계정 준비 증거 없음'
        self.assertEqual(ba.record(other,result)['verdict'],'BLOCKED')

    def test_필수서비스revision이빠지면fixture준비완료가아니다(self):
        self.catalog['cards'][0]['services']=['fe','be']
        ready=ba.fixture_readiness(self.catalog,self.env,'critical',self.root)
        self.assertEqual(ready['runnable_cells'],[])
        self.assertEqual(ready['blocked_cells'][0]['missing_revisions'],['be'])
    def test_fixture준비스냅샷변조를거절한다(self):
        readiness=ba.read_json(self.run/'fixture-readiness.json')
        readiness['fixtures']['guest']['problems']=['changed snapshot']
        ba.write_json(self.run/'fixture-readiness.json',readiness)
        with self.assertRaises(ba.ContractError):ba.record(self.run,self.result)

if __name__ == '__main__': unittest.main()
