---
date: 2026-10-31
branch: feat/local-qa-queue-1031
pr: null
type: feat
risk: normal
rollback: revert
tests: [test_qa_queue.py]
adr: none
---

# 로컬 디자인 QA 요청 큐 초안

## 무엇이 바뀌었나

- UI 변경을 로컬 SQLite에 PENDING으로 등록하고 중복을 제거한다.
- Claude 세션 훅이 요청을 등록한다. 실제 QA 실행과 판정은 별도다.

## 왜

- JD가 10/31 요청한 Claude·Codex 공통 로컬 QA 및 배포/사후 검증 개선.

## 확인한 것

- 테스트 저장소에서 UI 변경·중복·변경 후 별도 접수·타 레포 거부 검증.
- Codex/Claude 실제 세션 실행, 기존 QA 연결과 설치, 실패 복구는 미검증이다.
