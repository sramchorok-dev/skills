---
date: 2026-11-17
branch: feat/ai-native-sdlc-1117
pr:
type: feat
risk: infra
rollback: revert
tests: [test_sdlc.py, test_hooks.py, test_repository_tools.py]
adr: none
---

# 요청부터 독립 리뷰·DEV 증거까지 같은 계약으로 검사한다

## 무엇이 바뀌었나

팀 SDLC 스킬·명령·독립 리뷰어, intent/spec/plan 템플릿과 v1 JSON 계약을 추가한다.
필수검사 누락·실패·skip/cancel·다른 SHA·같은 리뷰 세션을 거부하고, 자료 설치/인증/실제읽기를 구분한다.
로컬 PASS는 입력 정합성일 뿐이며 인증된 승인·실행 증거를 대신하지 않는다.
활성 팀 문서의 JD 단독 승인과 사람 상호리뷰 의무를 동등권한·담당자 판단으로 바꾼다.

## 왜

사용자가 모든 Chorok 프로젝트에 AI-native SDLC를 적용하도록 인터뷰로 계획을 확정하고 끝까지 구현하도록 지시했다.
완료 보고의 신뢰성·요구사항 정확성·팀 인계를 우선하며 기존 규칙 보존은 제약이 아니라고 정했다.

## 확인한 것

- 저장소/기존 스킬/신규 검사기 전체 단위 테스트 209개 통과, 구조 검사 6개 스킬 통과.
- 합성 드라이런 9개 기대 판정 일치. 보호 코드 4종을 실제 제거한 임시본을 회귀 테스트가 assertion failure로 탐지.
- 실제 Claude Skill 호출 5개 확인. 첫 정책 평가 3/5에서 사람 본인승인 오독을 발견해 본문 보강; 본문 보강 후 재평가 5/5 통과. 합성 5사례이며 실제 업무 20~50개 corpus나 DEV 검증을 대체하지 않음.
- test-audit 스크립트 PASS이나 repo_kind=unknown으로 정책 매트릭스 적용 없음. 위 Python 단위·mutation 검증으로 보완.
- 실제 공용 승인 서버/팀원별 인증/실제 DEV/운영 검증은 이 패키지 검사로 수행하지 않았다.

### 독립 리뷰 후 보완

judge 이름·버전이 unknown인 평가가 통과하던 결함을 수정했다. unknown/none/n-a/not-applicable와 앞뒤 공백 사례를 실패로 재현한 뒤 공용 검사기 32개 회귀 통과. 모델·프롬프트 placeholder도 공백을 정규화해 판정한다.
