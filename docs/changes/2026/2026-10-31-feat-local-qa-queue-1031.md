---
date: 2026-10-31
branch: feat/local-qa-queue-1031
pr: null
type: feat
risk: normal
rollback: revert
tests: [test_qa_queue.py, test_qa_review_fixes.py, test_qa_run_link.py]
adr: docs/adr/0007-dev-fast-deploy-qa-pilot.md
---

# 로컬 QA 접수·책임·증거 추적

## 무엇이 바뀌었나

- UI 변경을 로컬 SQLite에 PENDING으로 등록하고 중복을 제거한다.
- Claude·Codex 세션 훅이 요청을 등록하고 미지정·기한 초과를 알린다. 실제 QA 실행과 판정은 별도다.
- 담당·기한·공유 링크를 지정하고 인계표를 출력한다. 비시각 변경은 사유 있는 디자인 N/A를 지원한다.
- rule별 검수 범위를 보존하고 환경 오류로 과거 PASS를 덮어쓰지 않는다. 설치기는 Python 경로를 고정하며 doctor가 실제 어댑터를 점검한다.

## 왜

- JD가 10/31 요청한 Claude·Codex 공통 로컬 QA 및 배포/사후 검증 개선.
- 11/1 셀프리뷰 후 JD가 발견 사항 수정을 요청했다.

## 확인한 것

- 테스트 저장소에서 UI 변경·중복·변경 후 별도 접수·타 레포 거부 검증.
- 격리 모의와 일반 세션에서 Claude·Codex 접수를 확인했다. 실제 Figma 원본 판정은 별도다. 로컬 배포 worker는 관리자 개인 설치이며 이 스킬의 설치 범위가 아니다.
