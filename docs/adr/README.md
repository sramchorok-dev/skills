# 팀 ADR (Architecture Decision Records)

여러 레포와 팀 작업 방식에 걸친 결정만 여기에 둔다. 레포 하나에 한정된 결정은 그 레포의 `docs/decisions/`에 둔다.

## 언제 쓰나 — 기본값은 "쓰지 않는다"

아래 셋 중 **둘 이상**일 때만 ADR을 쓴다. 나머지는 PR 변경기록(`docs/changes/`)의 `## 왜`로 충분하다.

1. **되돌리기 비싸다** — 스키마·데이터·외부 계약(PG·알림톡·API)·인프라·배포 방식
2. **넓게 영향을 준다** — 레포 2개 이상, 또는 팀 전체의 작업 방식
3. **대안을 진지하게 검토했다** — 반년 뒤 "왜 이렇게 했지?"라는 질문이 예상된다

## 쓰는 법

- 파일: `NNNN-짧은-제목.md`, 번호는 순서대로. [0000-template.md](0000-template.md)를 복사한다.
- 한 페이지를 넘기지 않는다. 결정·이유·대안·결과만.
- 결정이 바뀌면 기존 ADR을 고치지 않는다. 새 ADR을 쓰고 옛 ADR의 상태를 `superseded by NNNN`으로 바꾼다.
- 상태: `proposed`(시범·측정 중) → `accepted` → `superseded` / `deprecated`.

## 목록

| 번호 | 결정 | 상태 |
|---|---|---|
| [0001](0001-agents-md-single-source.md) | 에이전트 지침은 레포별 `AGENTS.md` 하나로 둔다 | accepted |
| [0002](0002-guardrails-plugin.md) | 규칙은 skills 저장소 플러그인으로 배포한다. 편집은 차단, Bash는 확인 | accepted |
| [0003](0003-change-record-per-pr.md) | PR마다 변경기록 파일 하나, ADR은 기준을 충족할 때만 | accepted |
| [0004](0004-ai-code-review.md) | AI 코드 리뷰는 claude-code-action으로 시범 운영하고 수치로 확정한다 | proposed |

테스트 규칙은 ADR이 아니라 [`testing-policy.md`](../../skills/gardenstep-test-audit/references/testing-policy.md)가 정본이다.
