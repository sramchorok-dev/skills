---
date: 2026-09-28
branch: docs/nextjs-agents-md
pr: 3
type: docs
risk: normal
rollback: revert
tests: []
adr: docs/adr/0001-agents-md-single-source.md
---

# Next.js 레포의 AGENTS.md 관리 블록을 가이드·템플릿·ADR에 적는다

## 무엇이 바뀌었나

- AGENTS.md 템플릿 주석, ADR 0001 결과, 팀 가이드 FAQ에 "Next.js 16.3+의 `next dev`가 AGENTS.md 끝에 관리 블록을 붙이니 함께 커밋한다"를 추가한다.

## 왜

- FE 릴리스 브랜치 동기화 중 AGENTS.md add/add 충돌로 발견. 블록이 없으면 `next dev`마다 트리가 더러워지고, AGENTS.md가 없으면 CLAUDE.md까지 생겨 ADR 0001과 어긋난다.

## 확인한 것

- Next.js 16.3.3 `writeAgentFiles()`를 FE·admin AGENTS.md에 실행: 블록 포함 시 `unchanged`, `claudeMd: skipped`.
