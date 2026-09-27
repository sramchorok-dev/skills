# 0004. AI 코드 리뷰는 claude-code-action으로 시범 운영하고 수치로 확정한다

- 상태: proposed
- 날짜: 2026-09-27
- 결정: JD

## 맥락

PR 첫 피드백을 사람 리뷰 전에 몇 분 안에 받고 싶다. 팀 전원이 Claude 구독을 쓰고, 저장소는 GitHub 무료 플랜 private이다.
후보로 alibaba/open-code-review(OCR)를 검토했다.

## 결정

- 주력 후보: `anthropics/claude-code-action@v1`. 공식 `code-review` 플러그인(결함, 한국어)과 테스트 매핑표(바뀐 동작 ↔ 테스트) 두 단계. 템플릿: [`templates/repo/.github/workflows/claude-review.yml`](../../templates/repo/.github/workflows/claude-review.yml).
- 시범: 레포 1곳, PR 10건. OCR은 로컬 delegation 모드(추가 비용 없음)로 같은 PR에 돌린다.
- 측정: 도구별 "반영된 코멘트 수 / 전체 코멘트 수", 놓친 결함, 리뷰 1건당 시간·비용. 결과로 이 ADR을 accepted 또는 superseded로 바꾼다.
- AI 리뷰는 머지를 막지 않고 사람 리뷰를 대신하지 않는다.

## 검토한 대안

| 대안 | 버린 이유 (시범 전 판단) |
|---|---|
| open-code-review 주력 | 기본 설정이 테스트 파일을 리뷰에서 제외한다 — 팀이 가장 원하는 테스트 충분성 검증과 맞지 않는다. 2026-05 공개로 릴리스 변동이 크고, 예제가 `pull_request_target`를 써 server CI 금지 검사와 충돌한다. 효과 수치는 벤더 발표뿐이다 |
| Claude Code 관리형 Code Review | Team/Enterprise 구독 전용, 리뷰당 별도 과금 |
| CodeRabbit | private 저장소는 유료 좌석 |
| Copilot code review | Copilot 좌석이 별도로 필요하다 |

## 결과

- 좋아지는 것: 팀 규칙(AGENTS.md·testing-policy)을 그대로 읽는 리뷰어, 구독 재사용.
- 감수하는 것: OAuth 토큰은 발급자 구독 한도를 쓴다. Actions 분 소모(무료 플랜 한도 확인 필요). 코멘트가 시끄러우면 무시하는 습관이 생기므로 심각도 높은 것만 보고하게 한다.
- 다시 볼 조건: 시범 결과, 또는 OCR이 테스트 파일 리뷰·한국어 출력을 안정적으로 지원할 때.
