---
date: {{date}}
branch: {{branch}}
pr:
type: {{type}}            # feat | fix | refactor | perf | migration | chore | docs | test | ci
risk: normal          # normal | money | migration | security | infra
rollback: image       # image | rds-snapshot | config | revert | n/a
tests: []             # 이 변경을 지키는 테스트 파일 (예: [OrderControllerTest, cart.spec.ts])
adr: none             # none | docs/decisions/NNNN-....md
---

# {{title}}

## 무엇이 바뀌었나

<!-- 사용자·운영자가 체감하는 동작 변화부터. 파일 목록이 아니라 동작. 2~5줄 -->

## 왜

<!-- 사용자·이슈·회의에서 받은 이유. 에이전트는 추측해서 쓰지 않는다. 이슈 링크 권장 -->

## 확인한 것

<!-- PR 본문 `## 검증`과 같은 내용. 무엇을 어떤 환경에서 확인했는지 -->
