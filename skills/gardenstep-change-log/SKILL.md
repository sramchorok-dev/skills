---
name: gardenstep-change-log
description: Gardenstep 레포에서 PR마다 남기는 변경기록(docs/changes/YYYY/YYYY-MM-DD-<브랜치>.md)을 만들고 검사하며, 이 변경이 ADR까지 필요한지 판정할 때 사용한다. "변경기록 써줘", "change log", "왜 바꿨는지 기록", "PR 올리기 전 정리", "ADR 필요해?", "ADR 써줘", "결정 기록 남겨"처럼 변경의 날짜·내용·사유를 남기거나 결정 문서가 필요한지 묻는 요청, "그때 왜 그렇게 했지", "과거 결정 찾아줘", "히스토리 검색"처럼 레포의 변경·결정 이력을 찾는 요청, 그리고 /ship-pr 절차에서 발동한다.
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

(`new`는 마이그레이션 파일 변경을 감지하면 `risk: migration`·`rollback: rds-snapshot`을 미리 채운다. 맞는지 확인한다.
frontmatter의 `#` 주석은 지워도 된다.)

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
`docs/adr/`. 만들기: `python3 "$SKILL_DIR/scripts/change_record.py" new-adr --title "<결정 한 문장>"`
(다음 번호·틀 자동). 헤더 `- 기준:`에 충족한 기준 둘 이상을 적고, 한 페이지(80줄)를 넘기지 않는다.
채택된 ADR은 고치지 않는다 — 새 ADR을 쓰고 옛 ADR의 `- 상태:`만 `superseded by NNNN`으로.
ADR을 쓰면 변경기록 `adr:`에 경로를 적는다. CI가 검사하는 규칙 전체: skills 저장소 `docs/adr/README.md`.

위험도 높은 변경(`migration`·`infra`·`security`)이 `adr: none`이면 `check`가 경고한다. 경고는 "ADR이 필요한지
한 번 따져 보라"는 뜻이다. 기준 둘 이상이 아니면 그대로 둔다 — ADR을 채워 경고를 없애지 않는다.

**기준을 셀 때**
- 기준은 이 변경이 **실제로 만드는 사실**로만 센다. "외부 계약일 수도 있다" 같은 가능성은 세지 않는다.
- 스키마(마이그레이션) 변경은 기준 1(되돌리기 비쌈)을 **혼자 충족한다.** 그래서 ADR이 되는지는 기준 2(다른 레포·팀 작업 방식에
  영향) 또는 기준 3(진지하게 검토한 대안)에 달렸고, 둘 다 **사람만 아는 사실**이다.
- 사람이 없는 실행에서는 기준 2·3을 충족하지 않은 것으로 두고 ADR을 쓰지 않는다. 대신 변경기록에
  `adr: none (기준 1개: 스키마 변경뿐, 다른 레포 영향·검토한 대안은 확인 못 함)`처럼 **판정을 남기고** 완료 보고에서 사람에게 묻는다.

**에이전트가 지키는 것**
- `결정`(결정한 사람)·`기준`(충족한 기준)·`검토한 대안`은 사람에게 확인한 내용만 적는다. 모르면 한 문장으로 묻는다.
  `check`를 통과시키려고 기준 단어를 채워 넣지 않는다 — 기준 둘이 안 되면 ADR을 쓰지 않고 변경기록 `## 왜`에 적는다.
- 이미 채택된 ADR의 본문은 고치지 않는다. 결정이 바뀌면 `new-adr`로 새 ADR을 쓰고 옛 ADR의 `- 상태:`만 바꾼다.
- ADR 파일명은 `NNNN-제목.md`뿐이다. 날짜 이름(`2026-10-03-….md`)으로 결정 문서를 만들지 않는다.
- 번호 충돌(`다음 순번 …`)은 번호를 올려 파일명·제목·변경기록 `adr:`를 함께 바꾼다.

## 3-1. 히스토리 찾기

```bash
python3 "$SKILL_DIR/scripts/history.py" --ref origin/dev 쿠폰 할인   # 단어가 모두 들어간 기록
python3 "$SKILL_DIR/scripts/history.py" --risk migration --since 2026-09-01
python3 "$SKILL_DIR/scripts/history.py" --kind adr
```

워크스페이스 루트에서 실행하면 세 레포를 함께 훑는다(`--root`로 지정 가능). 읽기 전용이다.
과거 결정이 궁금하면 추측하지 말고 먼저 이 명령으로 찾는다.

## 4. 검사

```bash
python3 "$SKILL_DIR/scripts/change_record.py" check --repo .
```

검사 항목: 기록 존재, frontmatter 필수 값·허용 값, `무엇`·`왜` 내용(상투어·10자 미만 거부), 마이그레이션 변경의 rollback,
ADR 규칙(새 ADR 형식·기준·번호, 채택된 ADR 수정 금지, `adr:` 상호 참조).
종료 코드 1 = 실패. CI(`change-gate`)와 PR 게이트 hook이 같은 검사를 쓴다.

## 완료 보고

- 기록 경로, `왜`의 출처(사용자 발화·이슈 번호), ADR 판정(없음 / 제안 + 이유)
- `check` 결과 한 줄
