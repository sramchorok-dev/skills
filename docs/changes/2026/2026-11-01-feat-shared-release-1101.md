---
date: 2026-11-01
branch: feat/shared-release-1101
pr: null
type: feat
risk: normal
rollback: revert
tests: [skills/gardenstep-release/tests/test_release.py]
---

# 공용 빠른 배포·후검증 스킬

## 무엇이 바뀌었나
- gardenstep-release가 기본 GitHub 경로와 설치된 로컬 실행기의 테스트 재사용 경로를 안내한다.
- 읽기 전용 planner가 환경·SHA/tree/workflow·증거 후보를 대조하고 dry-run 명령을 만든다.
- 후검증 조회는 배포 ID·attempt·SHA 및 QA artifact를 대조하고 자동 회귀와 실환경 검수를 구분한다.
- 로컬 실행기·개인 인프라 설정을 팀 저장소에 복사하지 않는다. 운영 게이트 변경 없음.

## 왜
- JD가 후검증 방법을 보고서에서 한눈에 보고 싶고 빠른 운영 배포 스킬을 공용으로 추가하자고 요청했다.

## 확인한 것
- 임시 Git 저장소의 계획, 테스트 재사용 일치/불일치, AI 운영 로컬 경로 거부, 후검증 identity/중복/누락/실패 판정.
- 실제 서비스 배포·후검증 dispatch·Telegram 전송은 수행하지 않았다.
