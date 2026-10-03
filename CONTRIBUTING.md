# Contributing

## 스킬 설계

1. 반복되는 실제 업무 한 가지를 스킬 하나로 정의
2. 사용자 요청에서 발동 문구·입력·완료 조건 추출
3. `skills/<name>/SKILL.md` 작성
4. 결정적 작업의 bundled script와 단위 테스트 추가
5. `evals/evals.json`에 정상·비게시·실패 사례 포함
6. `catalog.json`과 README 목록 갱신

## SKILL.md frontmatter

```yaml
---
name: kebab-case-name
description: 무엇을 수행하고 어떤 사용자 표현에서 발동하는지 설명
compatibility: 선택 사항
---
```

본문은 실행 순서, 입력, 안전 경계, 검증, 완료 보고를 중심으로 작성한다. 환경별 긴 설명과 명령 목록은 `references/`로 분리한다.

## 플러그인 (hook·명령)

- hook 스크립트는 `hooks/`, 배선은 `hooks/hooks.json`, 슬래시 명령은 `commands/*.md`(frontmatter `description` 필수).
- 정책(docs/adr/0002): 편집 도구는 보호 파일만 `deny`, Bash는 `deny` 없이 `ask`. hook은 예외가 나도 작업을 막지 않는다(exit 0).
- 동작 테스트는 `tests/test_hooks.py`에 JSON stdin → 결정 출력 형태로 추가한다. 막아야 할 것과 막지 말아야 할 것을 함께 쓴다.
- 플러그인에 들어가는 것(`hooks/`, `commands/`, `skills/`, `scripts/hook_stats.py`)을 바꾸면 `.claude-plugin/plugin.json`의 `version`을 올린다. 올리지 않으면 팀원 캐시가 갱신되지 않고 PR CI(`scripts/check_plugin_version.py`)가 실패한다.
- 새 규칙에는 고정 ID를 붙이고 결정 로그(`c.log_decision`)에 남긴다. 로그에는 규칙 ID·레포 이름·시각만 쓴다 — 명령·파일 내용·경로를 넣지 않는다.
- 이 저장소는 공개이며 팀원 머신에서 실행된다. 호스트명·계정·비밀값을 넣지 않는다.

## 검증

```bash
python3 scripts/validate_skills.py
python3 -m unittest discover -s tests -v
python3 -m unittest discover -s skills/<name>/tests -v
git diff --check
```

Pull Request에는 문제, 최종 동작, 실행한 검증, 외부 시스템 변경 여부를 적는다.
