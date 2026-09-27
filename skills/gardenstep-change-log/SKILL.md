---
name: gardenstep-change-log
description: Gardenstep 레포에서 PR마다 남기는 변경기록(docs/changes/YYYY/YYYY-MM-DD-<브랜치>.md)을 만들고 검사하며, 이 변경이 ADR까지 필요한지 판정할 때 사용한다. "변경기록 써줘", "change log", "왜 바꿨는지 기록", "PR 올리기 전 정리", "ADR 필요해?", "결정 기록 남겨"처럼 변경의 날짜·내용·사유를 남기거나 결정 문서가 필요한지 묻는 요청, 그리고 /ship-pr 절차에서 발동한다.
compatibility: Python 3.10+, git. 각 서비스 레포 디렉터리에서 실행
---

# Gardenstep 변경기록

PR 하나 = 기록 파일 하나. 파일명이 `날짜-브랜치`라 두 PR이 같은 파일을 건드리지 않고, squash 머지 뒤에도
트리에 남는다. 형식 결정: skills 저장소 `docs/adr/0003-change-record-per-pr.md`.

## 1. 기록 만들기

`SKILL_DIR`은 이 `SKILL.md`가 있는 디렉터리다.

```bash
python3 "$SKILL_DIR/scripts/change_record.py" new --repo . --type feat --title "<달라진 동작 한 줄>"
```

이미 이 브랜치의 기록이 있으면 새로 만들지 않고 경로만 출력한다. 템플릿: [assets/change-record.md](assets/change-record.md).

## 2. 채우기

| 칸 | 누가 | 기준 |
|---|---|---|
| `## 무엇이 바뀌었나` | 에이전트 초안 → 작성자 확인 | diff가 아니라 **동작** 변화. 2~5줄 |
| `## 왜` | **사람** | 사용자·이슈·회의에서 받은 이유. 대화에 이유가 없으면 사용자에게 묻는다. 추측·일반론 금지 |
| `## 확인한 것` | 에이전트 | PR 본문 `## 검증`과 같은 내용 |
| `type` / `risk` | 에이전트 | 결제·금액·재고·권한 = `money`, 스키마 = `migration` |
| `rollback` | 에이전트 → 작성자 확인 | Liquibase 파일이 바뀌면 `rds-snapshot` (이미지 롤백 불가) |
| `tests` | 에이전트 | 이 변경을 지키는 테스트 파일 이름 |
| `pr` | `/ship-pr` | PR 생성 후 `set-pr --pr <번호>` |

"왜"를 지어내면 이 디렉터리 전체를 믿을 수 없게 된다. 이유를 모르면 비워 두고 사용자에게 한 문장으로 묻는다.

## 3. ADR이 필요한가

기본값은 **ADR 없음** — 변경기록의 `## 왜`로 충분하다. 아래 셋 중 **둘 이상**이면 ADR을 제안한다.

1. 되돌리기 비싸다 — 스키마·데이터·외부 계약(PG·알림톡·API)·인프라·배포 방식
2. 레포 2개 이상 또는 팀 작업 방식 전체에 영향을 준다
3. 진지하게 검토한 대안이 있고, 반년 뒤 "왜 이렇게 했지?"라는 질문이 예상된다

ADR 위치는 레포의 기존 디렉터리(`docs/decisions/`, 없으면 새로 만든다), 팀 공통 결정은 skills 저장소
`docs/adr/`. 한 페이지를 넘기지 않는다. ADR을 쓰면 변경기록 `adr:`에 경로를 적는다.
형식·목록: skills 저장소 `docs/adr/README.md`.

## 4. 검사

```bash
python3 "$SKILL_DIR/scripts/change_record.py" check --repo .
```

검사 항목: 기록 존재, frontmatter 필수 값·허용 값, `무엇`·`왜` 내용, 마이그레이션 변경의 rollback.
종료 코드 1 = 실패. CI(`change-gate`)와 PR 게이트 hook이 같은 검사를 쓴다.

## 완료 보고

- 기록 경로, `왜`의 출처(사용자 발화·이슈 번호), ADR 판정(없음 / 제안 + 이유)
- `check` 결과 한 줄
