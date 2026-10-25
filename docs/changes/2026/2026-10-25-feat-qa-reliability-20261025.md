---
date: 2026-10-25
branch: feat/qa-reliability-20261025
pr:
type: feat            # feat | fix | refactor | perf | migration | chore | docs | test | ci
risk: normal          # normal | money | migration | security | infra
rollback: revert       # image | rds-snapshot | config | revert | n/a
tests: [test_reliability.py, test_browser_agent.py]             # 이 변경을 지키는 테스트 파일 (예: [OrderControllerTest, cart.spec.ts])
adr: none             # none | docs/decisions/NNNN-....md
---

# QA 반복 실행 판정과 fixture 수명 관리 도구 추가

## 무엇이 바뀌었나

- 출처 기반 값 비교로 거짓 MATCH를 거절한다.
- P0를 보존한 실행 계획, 반복 실행의 첫 성공·회복·미실행, 과거 실패 초안을 제공한다.
- 기존 loopback 전용 lease 계약의 생성·정리·잔여 확인을 지원하고 공개 DEV는 거절한다.
- 저장된 GitHub Actions 실행별 시간만 집계하며 비용이나 검증 수치를 추정하지 않는다.

## 왜

사용자가 주요 기능의 넓은 QA 커버리지와 CI 간소화를 요청했고, Best Practice 기반 개선안을 제안한 뒤 “진행해주고 결과 알려줘”라고 실행을 지시했다. 수동 agent QA는 CI에 넣지 않고 현재 브라우저는 Ego Lite를 사용한다.

## 확인한 것

- Python CLI/계약·순수 계산·실제 loopback HTTP 전송 테스트. 전체 스킬 및 저장소 검증 실행.
- 신·구 스킬의 합성 입력 3건 오프라인 비교. 실제 서비스 합격률로 사용하지 않음.
- 공개 화면은 읽기 전용 관찰. 독립 브라우저/실제 fixture 서버가 없어 acceptance와 실제 lease 통합은 BLOCKED.
- 서비스 코드·CI 워크플로·운영 환경 변경 없음.
