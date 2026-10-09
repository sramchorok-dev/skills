---
date: 2026-10-09
branch: feat/qa-run-skill
pr:
type: feat
risk: normal
rollback: revert
tests: [test_qa_scripts.py, test_repository_tools.py]
adr: none
---

# DEV QA 실행 스킬 `gardenstep-qa-run` — 작은 모델도 QA 시트 기준대로 TC를 실행·기록

## 무엇이 바뀌었나

- 새 스킬 `gardenstep-qa-run`: QA 시트(`Tier2 QA · TC와 실행 기록`)의 TC를 DEV에서 한 개씩 실행하고 `02 실행기록`에 붙여 넣을 TSV 행과 `04 결함과결정` 초안을 만든다.
- `tc_cards.py`: 시트 xlsx(표준 라이브러리만) 또는 CSV에서 TC를 골라 절차·합격 기준 항목 [C1…]·연결 이슈·자동화 여부를 카드로 출력한다.
- `qa_record.py`: 항목별 일치/불일치/확인불가로 판정을 계산한다(불일치→FAIL, 확인불가→BLOCKED, 모두 일치+증거→PASS). 증거 없는 판정, 사람 판단 없는 N/A, 추측한 SHA, 전화번호·이메일·토큰이 든 결과를 거부한다.
- 플러그인 버전 0.3.0, README·catalog에 스킬 추가.

## 왜

- JD 요청(2026-10-09): "작은 모델(ex. 5.5 haiku)이 꼼꼼히 우리 스펙에 맞게 QA를 할 수 있는 문서 및 skill(이건 우리 공용 skill 문서에 올리자) — 최신의 skill creator skill로 최적화".
- QA 운영 가이드의 판정 규칙(자동화 통과·과거 PASS를 이번 결과로 옮기지 않음, FAIL·BLOCKED·NOT_RUN을 분모에서 빼지 않음)을 사람이 아닌 모델이 실행해도 지켜지게 하려는 것.

## 확인한 것

- `python3 -m unittest discover -s skills/gardenstep-qa-run/tests` 25건 통과(카드 분할·시트 읽기·판정·민감정보 거부·TSV 왕복).
- `python3 scripts/validate_skills.py`, 저장소 테스트 통과.
- 10/7 QA 시트 스냅샷으로 `tc_cards.py` 실제 출력 확인(A-01·G-05·P-22, 이슈 필터).
- skill-creator(anthropics/skills 10/5 최신과 동일본) 방식으로 Haiku가 실제 DEV에서 3개 시나리오(A-01·A-02 실행, 낡은 G-03 재시험, "실행 없이 PASS로" 압박)를 스킬 사용/미사용으로 실행·채점. 3회 반복 개선 후 스킬 22/22(100%), 미사용 18/22(82%). 미사용은 띄어쓰기가 다른 문구를 PASS로 올리고, 옛 로컬 파일의 SHA를 적고, 낡은 TC 절차를 표시하지 않았다.
