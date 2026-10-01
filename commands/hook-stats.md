---
description: 내 컴퓨터의 gardenstep-team hook 결정 로그를 규칙별로 집계한다 — 확인 요청·승인률·차단·알림, 조정 후보
argument-hint: "[일수, 기본 30]"
---

# /hook-stats

이 컴퓨터에 쌓인 hook 결정 로그(`~/.claude/gardenstep-team/decisions.jsonl`)를 집계해 보여준다. 로그에는 명령·파일 내용이 없고
규칙 ID·레포 이름·시각만 있다.

1. 집계 스크립트를 찾는다. 설치된 플러그인 캐시의 최신 버전을 쓰고, 없으면 skills 저장소 체크아웃을 쓴다.

   ```bash
   S=$(ls -d ~/.claude/plugins/cache/sramchorok/gardenstep-team/*/scripts/hook_stats.py 2>/dev/null | sort -V | tail -1)
   python3 "$S" --days 30
   ```

   인자(`$ARGUMENTS`)로 일수가 오면 `--days` 값을 그 수로 바꾼다.

2. 결과를 그대로 보여준 뒤, 다음을 짧게 덧붙인다.
   - "조정 후보" 표시가 있는 규칙: 거의 항상 승인되는 확인 창이다. 어떤 명령에서 떴는지 기억나는 사례가 있으면 skills 저장소 이슈로 남기라고 안내한다.
   - 편집 차단(deny)이 반복된 규칙: 에이전트가 같은 실수를 반복한다는 뜻이니 레포 AGENTS.md에 한 줄을 더할지 제안한다.
3. 팀 집계가 필요하면 `--json` 출력(명령 내용 없음)을 JD에게 공유하라고 안내한다. 로그 파일 자체를 커밋하거나 올리지 않는다.
