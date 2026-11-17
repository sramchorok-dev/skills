# 테스트와 평가

결정적 tests는 사용자 동작·계산·권한·실패 경계를 확인한다. 비결정적 evals는 모델의 답변·도구 선택·정책 준수를 확인한다.
평가 입력·실행 코드·채점 기준은 저장소에서 버전 관리하고, 튜닝에 사용하지 않은 입력과 공격 사례를 분리한다.
개발 하네스 eval과 제품 AI eval은 별도 집합이다. 구성/모델/프롬프트 변경에 해당 회귀를 실행한다.

각 필수 검사에 실제 명령·종료값·건수·서비스/하네스/모델/프롬프트/judge 버전·원시 결과를 남긴다.
exit0만으로 성공을 판정하지 않는다. 빈 결과·FAIL·skip/cancel·누락은 필수 gate를 통과하지 못한다.
버그는 수정 전 실패 재현→수정 후 성공을 기록한다. 보호 로직을 제거한 변이가 탐지되는지도 검사한다.
변경 경로와 영향받는 핵심 경로를 실제 DEV에서 확인한다. 모의 성공·격리 test 성공은 실제 DEV 증거와 별개다.

공용 검사기 자체 검증:

```bash
python3 -m unittest discover -s skills/gardenstep-sdlc/tests -v
python3 skills/gardenstep-sdlc/scripts/sdlc.py dry-run
python3 skills/gardenstep-sdlc/scripts/mutation_check.py
```

위 명령은 로컬·합성 검사다. 실제 모델의 skill triggering·판정 품질·팀원 인증·공용 서비스는 실행하지 않는다.
검사기 PASS만으로 인증된 증거 또는 사람 승인을 만들지 않는다.
