# 0003. PR마다 변경기록 파일 하나, ADR은 기준을 충족할 때만

- 상태: accepted
- 날짜: 2026-09-27
- 결정: JD

## 맥락

변경의 "왜"가 PR 본문·커밋·메신저에 흩어져 있었고, squash 머지 뒤에는 커밋 본문의 이유도 사라졌다.
출시·롤백 때 어떤 변경이 마이그레이션을 포함하는지 한눈에 볼 곳도 없었다.

## 결정

- 모든 PR은 `docs/changes/YYYY/YYYY-MM-DD-<브랜치>.md` 파일 하나를 추가한다.
- frontmatter: `date`, `branch`, `pr`, `type`, `risk`, `rollback`, `tests`, `adr`. 본문: `## 무엇이 바뀌었나` / `## 왜` / `## 확인한 것`.
- **`## 왜`는 사람이 준 이유만 쓴다.** 에이전트는 모르면 묻고, 추측하지 않는다.
- Liquibase 파일을 바꾸면 `rollback`에 실제 복구 방법(`rds-snapshot` 등)을 적는다.
- ADR은 [README](README.md)의 기준(되돌리기 비쌈·넓은 영향·대안 검토 중 둘 이상)을 충족할 때만 쓴다.
- 도구: `gardenstep-change-log` 스킬(`change_record.py new|check|set-pr`), CI `change-gate`, PR 게이트 hook.

## 검토한 대안

| 대안 | 버린 이유 |
|---|---|
| 단일 `CHANGELOG.md` | PR마다 같은 줄을 고쳐 충돌한다. "왜"를 담기 어렵다 |
| Conventional Commits + 자동 생성 | 무엇은 남지만 왜는 squash로 사라진다 |
| Changesets | npm 패키지 전제라 Java 레포에 맞지 않는다 |
| 모든 결정을 ADR로 | 문서가 많아져 아무도 읽지 않게 된다 |
| 레포를 가로지르는 중앙 저장소 한 곳 | 변경마다 다른 저장소에 PR을 하나 더 내야 해서 지켜지지 않는다 |

## 결과

- 좋아지는 것: 파일명이 날짜·브랜치라 충돌이 없고, 트리에 남아 squash 뒤에도 사라지지 않는다. 출시 때 `risk: migration`만 모아 볼 수 있다.
- 감수하는 것: 오타 수정 PR에도 두세 줄 기록이 필요하다. `/ship-pr`이 초안을 만들어 부담을 줄인다.
- 다시 볼 조건: 기록의 "왜"가 형식적으로 채워지는 경우가 반복될 때.
