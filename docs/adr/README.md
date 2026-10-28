# 팀 ADR (Architecture Decision Records)

여러 레포와 팀 작업 방식에 걸친 결정만 여기에 둔다. 레포 하나에 한정된 결정은 그 레포의 `docs/decisions/`에 둔다.

## 언제 쓰나 — 기본값은 "쓰지 않는다"

아래 셋 중 **둘 이상**일 때만 ADR을 쓴다. 나머지는 PR 변경기록(`docs/changes/`)의 `## 왜`로 충분하다.

1. **되돌리기 비싸다** — 스키마·데이터·외부 계약(PG·알림톡·API)·인프라·배포 방식
2. **넓게 영향을 준다** — 레포 2개 이상, 또는 팀 전체의 작업 방식
3. **대안을 진지하게 검토했다** — 반년 뒤 "왜 이렇게 했지?"라는 질문이 예상된다

## 기준을 세는 법

- 이 변경이 **실제로 만드는 사실**로만 센다. 가능성은 세지 않는다.
- 스키마 변경은 기준 1을 혼자 충족한다. ADR이 되려면 기준 2(레포 2개 이상·팀 작업 방식) 또는 3(진지하게 검토한 대안)이 더 필요하고,
  둘 다 사람이 아는 사실이다. 에이전트는 사람에게 확인하기 전에는 충족으로 세지 않는다.
- ADR을 쓰지 않기로 했으면 변경기록에 `adr: none (기준 1개: 이유)`로 판정을 남긴다. 위험도 높은 변경의 경고가 이 한 줄로 사라진다.

## 쓰는 법

- 만들기: `change_record.py new-adr --title "결정 한 문장"` — 다음 번호로 [틀](0000-template.md)을 채워 만든다.
- 파일: `NNNN-짧은-제목.md`. 레포 하나의 결정은 그 레포 `docs/decisions/`, 팀 결정은 여기.
- 헤더의 `- 기준:`에 충족한 기준을 **둘 이상** 적는다(되돌리기 비쌈 · 넓은 영향 · 대안 검토).
- 한 페이지(80줄)를 넘기지 않는다. 결정·이유·대안·결과만.
- 채택된 ADR은 **불변**이다. 결정이 바뀌면 새 ADR을 쓰고 옛 ADR의 `- 상태:` 한 줄만 `superseded by NNNN`으로 바꾼다.
- 상태: `proposed`(시범·측정 중) → `accepted` → `superseded` / `deprecated`.
- 이 PR의 변경기록 `adr:`에 경로를 적는다. 기록과 ADR은 서로를 가리킨다.

## CI가 검사하는 것 (`change-gate`)

새로 **추가한** ADR에만 적용한다(옛 ADR 소급 없음).

| 규칙 | 실패하면 |
|---|---|
| `- 기준:`에 기준 둘 이상 | 하나뿐이면 변경기록 `## 왜`로 충분하다 |
| 번호는 디렉터리의 다음 순번 | 동시 PR이 같은 번호를 쓰는 사고를 막는다 |
| `- 상태`(proposed·accepted)·`날짜`·`결정`, 맥락·결정·결과가 채워짐 | 틀만 복사한 ADR |
| `검토한 대안` 표에 한 행 이상, `다시 볼 조건` | 대안 없는 결정은 ADR이 아니다 |
| 80줄 이하 | 읽히지 않는 ADR |
| 기존 ADR은 `- 상태:` 줄만 수정 가능 (`superseded by NNNN`은 그 번호 파일이 있어야 함) | 역사 다시 쓰기 |
| ADR을 추가하면 변경기록 `adr:`가 그 경로를 가리킴 / `adr:` 경로는 실제 파일 | 기록과 ADR 단절 |

경고만 한다(실패 아님): `risk: migration·infra·security` 또는 마이그레이션 파일 변경인데 `adr: none` / 한 PR에 ADR 2개 이상.

변경기록 쪽 남발 방지: `## 왜`가 10자 미만이거나 "개선·정리·리팩터링" 같은 말뿐이면 실패한다. 이슈 링크(`#123`, URL)가 있으면 통과한다.

## 히스토리 찾기

레포마다 기록은 그 레포에 두고, 조회만 한곳에서 한다.

```bash
# 워크스페이스 루트에서: 세 레포의 기록을 origin/dev 기준으로 검색
python3 skills/gardenstep-change-log/scripts/history.py --ref origin/dev 쿠폰 할인
python3 skills/gardenstep-change-log/scripts/history.py --risk migration --since 2026-09-01
python3 skills/gardenstep-change-log/scripts/history.py --kind adr
```

## 목록

| 번호 | 결정 | 상태 |
|---|---|---|
| [0001](0001-agents-md-single-source.md) | 에이전트 지침은 레포별 `AGENTS.md` 하나로 둔다 | accepted |
| [0002](0002-guardrails-plugin.md) | 규칙은 skills 저장소 플러그인으로 배포한다. 편집은 차단, Bash는 확인 | accepted |
| [0003](0003-change-record-per-pr.md) | PR마다 변경기록 파일 하나, ADR은 기준을 충족할 때만 | accepted |
| [0004](0004-ai-code-review.md) | AI 코드 리뷰는 claude-code-action으로 시범 운영하고 수치로 확정한다 | proposed |
| [0006](0006-adr-rules-enforced-by-ci.md) | ADR 남발 방지 규칙을 `change-gate`가 검사하고, 기록은 레포에 두되 조회는 모은다 | accepted |

테스트 규칙은 ADR이 아니라 [`testing-policy.md`](../../skills/gardenstep-test-audit/references/testing-policy.md)가 정본이다.

- [0005 수동 브라우저 인수 검수와 CI 선택](0005-browser-acceptance-and-ci-selection.md) — 2026-10-24
