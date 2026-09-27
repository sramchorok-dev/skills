# 0001. 에이전트 지침은 레포별 AGENTS.md 하나로 둔다

- 상태: accepted
- 날짜: 2026-09-27
- 결정: JD

## 맥락

팀은 Claude Code를 주로 쓰지만 Codex·OpenCode도 함께 쓴다. 규칙이 개인 워크스페이스 파일에만 있어서
서비스 레포(server·ai·FE·admin)에서 작업하는 팀원의 에이전트는 팀 규칙을 전혀 읽지 못했다.
Claude Code는 v2.1.277부터 CLAUDE.md가 없으면 AGENTS.md를 프로젝트 지침으로 읽는다.

## 결정

- 각 서비스 레포 루트에 `AGENTS.md`를 두고 **CLAUDE.md는 만들지 않는다.** 40줄 이하로 유지한다.
- 담는 것: 명령, 작업 흐름, 에이전트가 실제로 틀리기 쉬운 레포 규칙, 하지 않는 것. 긴 절차는 스킬, 매번 막아야 하는 것은 hook으로 옮긴다([0002](0002-guardrails-plugin.md)).
- 템플릿: [`templates/repo/AGENTS.md`](../../templates/repo/AGENTS.md).

## 검토한 대안

| 대안 | 버린 이유 |
|---|---|
| CLAUDE.md 단독 | Codex·OpenCode가 읽지 않는다 |
| CLAUDE.md + `@AGENTS.md` import | 파일이 둘이 되고, 둘 중 하나만 고치는 실수가 생긴다 |
| 개인 워크스페이스에만 규칙 유지 | 팀원 에이전트에 닿지 않는다 (현재 문제) |

## 결과

- 좋아지는 것: 도구와 관계없이 같은 지침. 레포를 clone하면 규칙이 따라온다.
- 감수하는 것: Claude Code v2.1.281 이상이 필요하다. 작업 디렉터리 **상위**에 CLAUDE.md가 있으면 AGENTS.md가 무시된다 — 이 경우 `/config` → Project instructions를 `claude-md-and-agents-md`로 둔다. 플러그인 SessionStart hook이 이 상황을 감지해 알려준다.
- Next.js 16.3+ 레포(FE·admin)는 `next dev`가 AGENTS.md 끝에 Next.js 관리 블록을 붙이고, AGENTS.md가 없으면 CLAUDE.md(`@AGENTS.md`)까지 만든다. 블록을 포함한 AGENTS.md를 커밋해 두면 CLAUDE.md는 생기지 않는다(`writeAgentFiles()` 실행으로 확인, 2026-09-28).
- 다시 볼 조건: Claude Code의 AGENTS.md 지원 방식이 바뀔 때.
