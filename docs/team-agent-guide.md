# 에이전트 코딩 팀 가이드

새 작업의 정본은 [팀 AI-native SDLC v1](sdlc/README.md)이다.
JD와 푸름은 동등하며, 담당자 한 사람이 요청·요구사항·계획과 운영 반영을 판단한다.
사람 상호 리뷰는 선택이다. 작성자와 별도 세션의 에이전트 리뷰와 필수 실제 DEV 증거는 필요하다.

## 시작

1. 승인된 공용 패키지 revision으로 설치한다. Claude는 `gardenstep-team` 플러그인, Codex는 `scripts/install.py`로 스킬을 설치한다.
2. `/sdlc <Change-ID 또는 요청>`으로 intent/spec/plan과 출처를 연결한다.
3. 승인된 plan으로 worktree에서 구현하고 tests/evals를 실행한다.
4. 독립 리뷰와 실제 DEV 검증을 공용 환경에서 수행한다.
5. 인증된 증거가 모두 성공할 때 DEV 검증 완료다. 운영은 정확한 대상에 대한 사람 승인과 실제 확인이 추가된다.

## 기존 자산

- `gardenstep-test-audit`: 테스트 코드 품질. `gardenstep-completion-qa`: 실행 증거 확인.
- `gardenstep-qa-run`: 실제 브라우저 QA. `gardenstep-change-log`: 과거 기록과 기존 PR gate 호환.
- `/ship-pr`: 배치된 SDLC 계약을 확인해 PR을 준비한다. PR 생성은 운영 승인이 아니다.
- 훅은 로컬 사전 통제다. 자격이 노출된 경로를 서버 승인 장치처럼 막는다고 주장하지 않는다.

## 설치·운영 상태

고정 패키지 설치와 실제 서비스/runner 배치는 구분한다. GitHub 관리자가 branch를 직접 바꾸는 것까지 무보호 저장소에서 막을 수 없다.
에이전트에게 사람의 gh/SSH/AWS 자격을 노출하지 않는다. 권한 경계가 미배치면 그 사실을 미완료로 남긴다.
기존 운영 자격을 되살리는 rollback은 하지 않는다. 배포·DB·운영 복구는 승인된 전환/릴리스 절차를 따른다.

역사 결정은 [ADR](adr/README.md)에 남아 있다. 새 활성 정책과 충돌하는 옛 JD 단독 승인·상호 리뷰 필수 규칙은 대체됐다.
