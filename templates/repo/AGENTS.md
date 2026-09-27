# <레포 이름> — 에이전트 작업 지침

<!--
작성 규칙 (적용 후 이 주석은 지운다)
- 40줄 이하. 줄마다 "지우면 에이전트가 실수하는가?"를 묻고, 아니면 지운다.
- 가끔 필요한 긴 절차는 스킬로, 매번 막아야 하는 것은 hook으로 옮긴다 (sramchorok-dev/skills 플러그인).
- 비밀값·호스트명·계정 정보는 적지 않는다.
- CLAUDE.md는 만들지 않는다. Claude Code는 CLAUDE.md가 없을 때 AGENTS.md를 읽는다 (skills docs/adr/0001).
-->

<한 줄: 이 레포가 무엇이고 누가 쓰는가>

## 명령

| 목적 | 명령 |
|---|---|
| 설치 | `<command>` |
| 빠른 테스트 (변경 파일) | `<command>` |
| 전체 테스트 | `<command>` |
| 빌드 | `<command>` |

## 작업 흐름

- 기본 브랜치는 `dev`. 새 작업은 `feat/<짧은-이름>`·`fix/<짧은-이름>` 브랜치에서 한다. `main`·`release/*`에 직접 push하지 않는다.
- 동작을 바꾸면 테스트를 먼저 쓰고 실패를 확인한 뒤 구현한다. 규칙 정본: skills `gardenstep-test-audit`의 `references/testing-policy.md`.
- PR은 `/ship-pr`로 연다: 테스트 점검 → 변경기록(`docs/changes/`) → PR 본문 `## 검증`.
- 변경기록의 "왜"는 사용자·이슈에서 받는다. 모르면 묻고, 추측해서 쓰지 않는다.
- ADR은 기준(되돌리기 비쌈·여러 레포 영향·검토한 대안)에 맞을 때만 `<ADR 디렉터리>`에 쓴다.

## 이 레포의 규칙

<!-- 이 레포에서 에이전트가 실제로 틀렸던 것 / 틀리기 쉬운 것만. 3~7줄 -->
- <규칙 — 이유 한 구절>

## 하지 않는 것

- 운영 DB 쓰기, 운영 배포·롤백 실행, 비밀값 파일 편집. 필요하면 JD에게 요청한다.
- 이미 `dev`에 들어간 마이그레이션 파일 수정 (해당 레포만).

## 더 읽을 것

- 도메인 용어: `CONTEXT.md` (있을 때)
- 팀 가이드: https://github.com/sramchorok-dev/skills/blob/main/docs/team-agent-guide.md
