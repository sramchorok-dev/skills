# Agent Instructions

이 저장소는 sramchorok-dev의 업무 생산성용 공통 Agent 스킬 모음이다.

## 작업 원칙

- `skills/<name>/SKILL.md`를 스킬 정본으로 사용한다.
- 스킬 이름과 디렉터리 이름을 일치시킨다.
- 반복적·결정적 작업은 `scripts/`, 긴 자료는 `references/`, 출력 원본은 `assets/`에 둔다.
- SKILL.md는 500줄 이하로 유지하고 세부 내용은 bundled resource로 분리한다.
- 비밀값, 개인 식별 정보, 고객 원문, 로컬 `.env`를 커밋하지 않는다.
- 외부 게시·전송·삭제는 사용자의 현재 대화 지시 범위에서만 수행한다.
- 기존 스킬 변경 전 관련 테스트와 `evals/evals.json`을 읽는다.

## 완료 조건

1. `python3 scripts/validate_skills.py`
2. `python3 -m unittest discover -s tests -v`
3. 변경 스킬의 `tests/` 실행
4. `git diff --check`
5. README·catalog 일치

배포 기능이 있는 스킬은 dry-run/검증과 실제 배포를 분리하고, 대상 계정·환경·공개 readback을 확인한다.
