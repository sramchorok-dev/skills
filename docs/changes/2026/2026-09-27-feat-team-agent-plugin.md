---
date: 2026-09-27
branch: feat/team-agent-plugin
pr:
type: feat
risk: normal
rollback: revert
tests: [test_hooks.py, test_repository_tools.py, test_change_record.py]
adr: docs/adr/0001-agents-md-single-source.md
---

# 팀 에이전트 규칙을 Claude Code 플러그인으로 배포한다

## 무엇이 바뀌었나

- 저장소 루트가 Claude Code 마켓플레이스(`sramchorok`)이자 플러그인(`gardenstep-team`)이 된다. 설치하면 가드레일 hook, `/ship-pr` 명령, 스킬 4종이 함께 들어온다.
- hook: 비밀값·운영 설정·적용된 Liquibase changeset 편집 차단, 위험 Bash는 확인 요청, `gh pr create` 게이트, 테스트 스멜·누락 알림, 세션 시작 안내.
- 새 스킬 `gardenstep-change-log`(변경기록 생성·검사), 워크스페이스 전용이던 완료 QA를 `gardenstep-completion-qa`로 공유.
- 팀 가이드, 팀 ADR 4건, 서비스 레포 적용 템플릿(AGENTS.md, `.claude/settings.json`, PR 템플릿, change-gate, AI 리뷰 워크플로)을 추가한다.

## 왜

- 팀 규칙(브랜치·배포·DB·테스트)이 JD 개인 워크스페이스에만 있어 서비스 레포에서 작업하는 에이전트가 읽지 못했다.
- JD 결정(2026-09-27): 지침은 AGENTS.md 하나, 주요 결정·컨벤션은 꼭 필요한 것만 ADR, Bash 가드는 deny 없이 ask, PR마다 날짜·변경·사유 기록.

## 확인한 것

- `python3 scripts/validate_skills.py`, `python3 -m unittest discover -s tests`, `skills/*/tests` 전부 통과. `claude plugin validate .` 통과.
- 결함 감지: stop_hook_active 무시, 새 changeset 허용 분기 제거, ask→allow, '왜' 검사 제거를 각각 넣었을 때 해당 테스트가 실패하고 원복 후 통과.
