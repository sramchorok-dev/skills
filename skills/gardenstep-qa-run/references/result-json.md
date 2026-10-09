# 결과 JSON 형식 (`qa_record.py add` 입력)

TC 하나 × 분기(뷰포트·성공/실패) 하나 = 파일 하나. 예: `results/A-02-m.json`

```json
{
  "tc_id": "A-02",
  "tc_version": "1.1",
  "viewport": "모바일 390×844 · Chromium 새 세션",
  "preconditions_met": true,
  "checks": [
    {
      "id": "C1",
      "criterion": "탭 홈·식물/자재·AI 설계·둘러보기·마이 5슬롯",
      "status": "일치",
      "observed": "하단 탭 5개: 홈 / 식물·자재 / AI 설계 / 둘러보기 / 마이",
      "evidence": ["shots/QA-20261010-01/A-02-m-C1.png"]
    },
    {
      "id": "C2",
      "criterion": "드로어 공개 메뉴와 로그인 링크",
      "status": "불일치",
      "observed": "드로어에 '로그인' 링크 없음. 메뉴: 맞춤 식물·자재 구매 / 시공 견적 / 정원 둘러보기 / 이용 방법",
      "evidence": ["shots/QA-20261010-01/A-02-m-C2.png"]
    }
  ],
  "issue_id": "",
  "note": ""
}
```

| 키 | 필수 | 뜻 |
|---|---|---|
| `tc_id`, `tc_version` | 예 | TC 카드 제목의 ID와 `v` 뒤 숫자 |
| `viewport` | 예 | 크기 + 브라우저 + 세션. `[자동실행 · …]` 표시는 스크립트가 붙이므로 쓰지 않는다 |
| `preconditions_met` | 예 | 선행조건을 갖췄으면 `true`. `false`면 `blocked_reason` 필수, `checks`는 생략 |
| `checks[].status` | 예 | `일치` / `불일치` / `확인불가` 중 하나 |
| `checks[].observed` | 예 | 실제로 본 문구·값. "정상", "OK"처럼 쓰지 않는다 |
| `checks[].evidence` | 일치·불일치면 예 | 스크린샷·로그 경로 목록 |
| `issue_id` | FAIL이면 권장 | 04 탭의 기존 이슈 ID. 없으면 비워 두고 결함 초안을 쓴다 |
| `note` | 아니오 | 판정에 영향은 없지만 사람이 알아야 할 것(예: "TC 갱신 필요? 10/9 견적 2번 구성 결정") |
| `not_run_reason` | 아니오 | 이번에 일부러 실행하지 않은 TC. 결과 NOT_RUN |
| `na_reason`, `na_decided_by` | 아니오 | 사람이 범위에서 뺀 TC만. 둘 다 있어야 N/A |

판정은 스크립트가 정한다:

| 상황 | 결과 |
|---|---|
| `preconditions_met: false` | BLOCKED |
| 불일치 1개 이상 | FAIL |
| 불일치 없음 + 확인불가 1개 이상 | BLOCKED |
| 모두 일치 + 모두 증거 있음 | PASS |
