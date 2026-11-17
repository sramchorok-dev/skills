# 기존 파일을 보존하는 scaffold

Python 3.10+와 표준 라이브러리만 사용한다. 실제 네트워크 호출, 계정 생성, 모델 호출, git/원격 변경은 수행하지 않는다.
기존 파일이 하나라도 충돌하면 어떤 파일도 쓰기 전에 실패한다. 기존 프로젝트는 별도 빈 초안 디렉터리에 생성하고 승인된 전환 계획에 따라 병합한다.
같은 디렉터리에 재실행하거나 `--force`로 덮어쓰는 기능은 없다. 같은 출력 경로를 여러 프로세스가 동시에 수정하지 않는다.

1. `assets/profile.example.json`을 별도 파일로 복사해 실제 합의로 채운다. 멤버 ID·권한, 저장소 범위, 원자료 접근 범위, 비용을 명시한다. 비밀값·토큰·쿠키는 넣지 않는다.
2. 요청자의 원문과 정정을 `request.txt`에 담는다. 요약문으로 원문을 대체하지 않는다.
3. 빈 절대경로 디렉터리를 만든다. 기본 실행은 생성 예정 목록만 출력한다.
4. 그 목록을 확인하고 `--apply`로 문서를 생성한다. 사용자에게 이미 받은 생성 권한을 다시 묻을 필요는 없다.

```bash
python3 "$SKILL_DIR/scripts/scaffold.py" --root /absolute/draft --profile /absolute/profile.json --request-file /absolute/request.txt --change-id 2026-01-01-sdlc
python3 "$SKILL_DIR/scripts/scaffold.py" --root /absolute/draft --profile /absolute/profile.json --request-file /absolute/request.txt --change-id 2026-01-01-sdlc --apply
cd /absolute/draft
python3 -m unittest discover -s tests/sdlc -v
python3 scripts/sdlc/check_change.py --root . --change docs/changes/2026-01-01-sdlc
```

마지막 명령은 최초 생성 직후 **실패가 정상**이다. spec/plan의 TODO와 비어 있는 테스트 연결을 실제 내용으로 채우기 전에는 통과하지 않는다.
이 게이트는 요구사항→테스트 파일/케이스 연결의 정적 정합성만 검사한다. 테스트 실행 결과, skip/xfail, 권한, 승인, 원격 증거는 검사하지 않는다.
해당 언어의 실제 runner와 신뢰된 CI 정책을 붙이고, 검사 자체의 부정 테스트도 CI에 연결한다.

## 입력 형식

예시 JSON의 키를 유지한다. 알 수 없는 키는 오타나 비밀값 혼입을 드러내기 위해 거부한다.
- `mode`: `new` 또는 `migration`; `maturity`: `prototype`, `team`, `production`.
- `members`: 명시적 `id`, `approvals` 배열. intent/spec/plan에 적어도 한 명의 담당자가 있어야 한다. production 권한은 빈 채로 둘 수 있다.
- `human_peer_review`: `optional` 또는 `required`; `agent_review`: 예시의 동일 모델 허용 또는 `separate-session-different-model-required`.
- `repositories`: 적용 대상 이름 목록. 다른 조직의 시스템을 목표 달성에 필요하다는 이유로 자동 추가하지 않는다.
- `canonical_records`: 팀 기록의 정본 위치를 사람이 읽을 수 있는 문자열로 적는다. 생성 경로 자체는 항상 `docs/changes/<id>`다. 공용 기록 repo를 쓰면 생성한 문서 위치를 계획에 맞춰 옮긴다.
- `sources`: provider/locator/scope/owner. 샘플을 읽기 전 상태는 NOT_RUN이다. 출처가 없으면 빈 배열이다.
- `subscription_policy`: `keep-current` 또는 이미 승인된 `upgrade-approved`. 비용 수치는 팀이 정한 통화 단위를 계획에 명시한다. 생성기는 과금 서비스를 만들지 않는다.

## 출력

AGENTS/CLAUDE/REVIEW, docs/sdlc의 팀/전환/활성화/권한 문서, testing/glossary/ADR 진입점, 세 변경 문서·출처·테스트 매핑, eval 진입점, 정적 검사·검사 테스트를 만든다.
`.sdlc/bootstrap.json`은 생성 파일의 SHA-256 목록이다. 승인 증명서가 아니다.
시각을 제외한 문서 출력은 같은 입력에 대해 같다. `project_ready`는 항상 false이며 사람이 실제 검증 결과로 별도 판정한다.

## 변경 문서의 최소 문법

```markdown
## R1: 로그인한 사용자가 결과를 조회할 수 있다
```

```json
{"schema_version": 1, "requirements": [{"id": "R1", "verification": "automated", "tests": [{"path": "tests/test_results.py", "case": "test_authenticated_result"}]}]}
```

수동 검증은 `verification: "manual"`, `owner`, `reason`을 기록한다. 자동 검사를 수동으로 바꾸는 권한은 이 파일로 부여되지 않으며, 승인된 정책에서 검토한다.
정적 연결만으로 테스트 품질·성공·완료를 주장하지 않는다.
