---
name: gardenstep-qa-run
description: Run Gardenstep Tier2 QA test cases on the DEV environment exactly as the QA sheet ("Tier2 QA · TC와 실행 기록") defines them, and produce paste-ready '02 실행기록' rows (Run ID, SHA, verdict, 실제 결과, 증거) plus '04 결함과결정' drafts. Use this whenever someone asks to QA, 재검수, 재시험, run or check TC IDs like A-01/G-03/P-22, verify an R-issue fix (R52 등) on DEV, fill the QA execution log, or check a screen against the QA sheet — even if they only say "DEV에서 확인해줘" or "QA 돌려줘". Built so a small model (Haiku) can execute TCs one at a time with scripted parsing and verdicts. Not for writing automated test code (use gardenstep-test-audit) or for judging whether a code change is complete (use gardenstep-completion-qa).
---

# Gardenstep DEV QA 실행

QA 시트의 TC를 **DEV에서 한 개씩** 실행하고, 시트에 그대로 붙여 넣을 실행기록 행을 만든다.
판정은 스크립트가 항목 결과로 계산한다. 사람이 시트를 보고 바로 믿을 수 있어야 하므로, 본 것만 적고
못 본 것은 못 봤다고 적는다.

## 0. 시작 전에 받을 것

다음이 없으면 추측하지 말고 사용자에게 한 번에 물어본다.

1. **QA 시트 파일**: Google Sheets에서 받은 xlsx(권장) 또는 `01 TC정의` 탭 CSV 경로
2. **실행할 TC**: TC ID 목록, 영역(예: P), 우선순위(P0), 또는 이슈 ID(예: R52)
3. **Run ID**: `QA-YYYYMMDD-NN`. 시트 `00 먼저읽기`의 회차를 따른다. 없으면 오늘 날짜 + 사용자에게 번호 확인
4. **실행자(책임자) 이름**: 시트 규칙상 실행자 칸에는 사람만 적는다. 모델이 실행해도 책임자 이름을 받는다.
5. **DEV 주소·QA 계정**: 시트 `03 사전준비` 또는 사용자가 알려 준 비공개 문서에서 읽는다.
   이 저장소는 공개라 주소·계정을 여기 적지 않는다. 비밀번호는 출력·기록·스크린샷에 남기지 않는다.

## 1. TC 카드 만들기

```bash
python3 <skill>/scripts/tc_cards.py <시트.xlsx> --ids A-01,G-03     # 또는 --area P --priority P0 / --issue R52
```

카드에는 절차, **합격 기준 항목 [C1]…[Cn]**, 연결 이슈 상태, 자동화 여부가 나온다.
`[Cn]` 하나가 판정 단위다. 항목이 너무 크면 나눠서 확인하되 번호는 유지한다.

## 2. 실행 환경 기록

```bash
python3 <skill>/scripts/qa_record.py init --out runs/<Run ID>.tsv --run-id <Run ID> \
  --env "DEV FE <sha7>, BE <sha7>, Admin <sha7>" --runner <책임자> --tool "Claude+<브라우저 도구>"
```

`--tool`을 주면 파라미터 칸이 `[자동실행 · Claude+…]`로 시작한다. 시트는 이 표시로 모델이 실행한 행을
사람이 실행한 행과 구분한다. 사람이 직접 실행한 결과를 옮겨 적을 때만 `--tool`을 뺀다.

SHA는 [references/environment.md](references/environment.md)의 명령으로 확인한다. 확인하지 못하면
`--env "DEV 확인 불가(사유)"`라고 적는다. 지어낸 SHA는 결과 전체를 못 쓰게 만든다.

## 3. TC 하나씩 실행

카드 하나마다 아래 순서를 끝까지 하고 다음 카드로 넘어간다. 여러 TC를 머릿속에 동시에 들고 있으면
항목을 빠뜨리기 쉽다.

1. **선행조건 확인**: 준비 데이터·계정·선행 TC(예: P-22의 P-05)가 갖춰졌는지 본다. 없으면 실행하지 말고
   BLOCKED로 기록한다(무엇이 없었는지 적는다). 공유 DEV 데이터(가격·재고·진열·판매 상태)를 바꿔서
   맞추지 않는다 — 다른 사람의 QA를 망가뜨린다.
2. **새 세션**: 시크릿/새 브라우저 컨텍스트, 카드의 뷰포트(PC 1280×720, 모바일 390×844 등).
3. **절차를 그대로**: 카드 절차 순서대로. 다른 경로로 같은 화면에 가지 않는다.
   절차의 버튼·화면이 없으면 화면에 보이는 가장 가까운 진입점을 **한 번만** 써 보고, 그 사실을 `note`에
   "TC 갱신 필요? 절차 n의 '…'가 없어 '…'로 진행"처럼 적는다. 진입점을 찾느라 여러 번 탐색하지 않는다.
4. **항목마다 관찰**: 화면 문구는 DOM 텍스트로 글자 그대로 옮긴다(띄어쓰기·문장부호 포함).
   눈대중으로 "비슷함"을 일치로 적지 않는다. 항목마다 스크린샷을 남긴다.
   판정 근거는 **DEV 화면과 시트 기준**뿐이다. 코드·주석·자동화 테스트는 옛 내용일 수 있어 근거로 쓰지 않는다.
   요소가 한 화면에만 없으면, 그 요소가 있어야 할 다른 화면 1~2곳도 열어 보고 `note`에 적는다
   (예: "홈에서만 없음, /shop·/design에는 있음"). 사람이 의도된 예외인지 회귀인지 빨리 가른다.
   브라우저 다루는 요령: [references/browser.md](references/browser.md)
5. **결과 JSON 작성**: [references/result-json.md](references/result-json.md) 형식. 항목마다
   `일치` / `불일치` / `확인불가` 중 하나와 실제로 본 값, 증거 경로.
6. **기록**:
   ```bash
   python3 <skill>/scripts/qa_record.py add --run runs/<Run ID>.tsv results/<TC>-<뷰포트>.json
   ```
   스크립트가 판정을 계산한다: 불일치가 하나라도 있으면 FAIL, 확인불가가 있으면 BLOCKED, 모두 일치이고
   증거가 있을 때만 PASS. 거부되면 메시지대로 JSON을 고쳐 다시 실행한다. 판정을 원하는 쪽으로 바꾸려고
   항목 상태를 고치지 않는다.
7. PC/모바일·성공/실패 분기가 있으면 **분기마다 행을 따로** 만든다.

판정이 애매한 상황(기준과 Figma가 다름, 기준이 최근 결정보다 오래됨, 화면은 맞는데 데이터가 이상함)은
[references/verdict-rules.md](references/verdict-rules.md)를 읽고 따른다.

## 4. 결함 초안

FAIL 행마다 `04 결함과결정` 초안을 쓴다. 이미 같은 현상의 이슈가 있으면 새로 만들지 않고 그 ID를
`issue_id`에 넣는다. 형식: [assets/defect-template.md](assets/defect-template.md).
원인·담당자를 추측해 단정하지 않는다. 현상·재현 절차·기대/실제·증거만 쓴다.

## 5. 마무리 보고

```bash
python3 <skill>/scripts/qa_record.py summary --run runs/<Run ID>.tsv
```

보고는 대화 응답으로 한다(파일을 따로 쓸 수 없는 환경도 있다). 보고에는 다음을 넣는다.

- 집계 한 줄(PASS·FAIL·BLOCKED·NOT_RUN·N/A)과 TSV 경로. 사람이 `02 실행기록`에 붙여 넣는다
  (이 스킬은 시트를 직접 고치지 않는다).
- FAIL·BLOCKED 목록과 결함 초안
- 실행하지 못한 범위와 이유(외부 결제·실알림·실기기 등)
- **이번 실행이 DEV에 만든 데이터**(상담 접수·견적·장바구니·주문 등)와 식별 값. 다른 사람이 보고 정리할 수 있게 한다
- 재시험이면 연결 이슈의 다음 상태 제안: [references/verdict-rules.md](references/verdict-rules.md) 10번
- 기준 자체가 낡았거나 서로 다르다고 본 TC는 "TC 갱신 필요?"로 따로 모아 근거와 함께 적는다 —
  기준을 고치는 결정은 사람이 한다.

## 하지 않는 것

- 운영(PROD) 화면·관리자에서 실행하지 않는다. 주소가 운영이면 멈추고 묻는다.
- 실제 카드 결제·환불은 TC가 요구하고 사용자가 이번 대화에서 지시한 경우에만, DEV 테스트 상점에서 한다.
- 자동화 테스트 통과, 과거 PASS, 사전판정 메모를 이번 실행 결과로 옮기지 않는다.
- 전화번호·이메일·주문 토큰·비밀번호를 결과·스크린샷 이름에 남기지 않는다(스크립트가 막는다).
