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

## 검증

```bash
python3 scripts/validate_skills.py
python3 -m unittest discover -s tests -v
python3 -m unittest discover -s skills/<name>/tests -v
git diff --check
```

Pull Request에는 문제, 최종 동작, 실행한 검증, 외부 시스템 변경 여부를 적는다.
