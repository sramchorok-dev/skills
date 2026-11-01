# sramchorok-dev Skills

업무 생산성을 위한 공통 Agent 스킬 저장소. Claude Code, Codex, OpenCode에서 같은 스킬을 재사용한다.

## 무엇이 들어 있나

| 구성 | 경로 | 용도 |
|---|---|---|
| 팀 가이드 | [docs/team-agent-guide.md](docs/team-agent-guide.md) | 에이전트 코딩 규칙 전체 — **처음이면 여기부터** |
| 팀 ADR | [docs/adr/](docs/adr/README.md) | 팀 공통 결정 (꼭 필요한 것만) |
| Claude Code 플러그인 `gardenstep-team` | `.claude-plugin/`, `hooks/`, `commands/` | 가드레일 hook, `/ship-pr`, `/hook-stats`, 아래 스킬 |
| 레포 적용 템플릿 | [templates/repo/](templates/repo/) | AGENTS.md, `.claude/settings.json`, PR 템플릿, CI(change-gate, AI 리뷰) |

## 스킬 목록

| 스킬 | 분야 | 용도 |
|---|---|---|
| [`gardenstep-change-log`](skills/gardenstep-change-log/) | 품질 | PR마다 `docs/changes/` 변경기록(날짜·무엇·왜) 생성·검사, ADR 필요 판정 |
| [`gardenstep-completion-qa`](skills/gardenstep-completion-qa/) | 품질 | 변경 동작별 TC·빌드·E2E·라이브 증거로 완료 판정 |
| [`gardenstep-qa-run`](skills/gardenstep-qa-run/) | 품질 | 수동 browser-use E2E·시트 TC·Figma 일치 검증: 버전 카드·항목 증거·재개·커버리지·정리 기록 |
| [`gardenstep-report-wiki`](skills/gardenstep-report-wiki/) | 보고·공유 | Gardenstep HTML 보고서 공개 DEV Wiki 게시 |
| [`gardenstep-test-audit`](skills/gardenstep-test-audit/) | 품질 | PR 테스트 코드의 팀 규칙 준수 점검·판정 (E2E 필수, 스멜, 영수증) |

## 설치

**Claude Code** — 플러그인으로 설치한다 (hook + 명령 + 스킬). 레포에 `.claude/settings.json`이 있으면 폴더 신뢰 수락 시 자동 설치된다.

```text
/plugin marketplace add sramchorok-dev/skills
/plugin install gardenstep-team@sramchorok
```

**Codex · OpenCode** — 스킬만 설치한다.

```bash
git clone https://github.com/sramchorok-dev/skills.git
cd skills
python3 scripts/install.py
```

설치기는 `~/.agents/skills/`에 저장소 스킬을 symlink한다. `~/.agents/sync.py`가 있으면 dry-run 후 Claude Code·Codex·OpenCode로 동기화한다. Claude Code에서 플러그인과 설치기를 함께 쓰면 스킬이 두 번 보이니 하나만 쓴다.

## 사용

Agent에게 자연어로 요청한다.

```text
이 HTML 보고서를 Gardenstep Report Wiki에 누구나 볼 수 있게 올려줘.
```

직접 실행:

```bash
python3 skills/gardenstep-report-wiki/scripts/publish_report.py ./report.html \
  --tags "챗봇,아키텍처" --ack-public --deploy --json
```

공개 Wiki: <https://cdn-dev.gardenstep.ai/report-wiki/index.html>

테스트 점검 (레포 디렉터리에서):

```bash
python3 ~/.agents/skills/gardenstep-test-audit/scripts/audit_tests.py --repo . --base origin/dev            # PR·브랜치
python3 ~/.agents/skills/gardenstep-test-audit/scripts/audit_tests.py --repo . --base origin/dev --working-tree  # 커밋 전
python3 ~/.agents/skills/gardenstep-test-audit/scripts/audit_tests.py --repo . --all-tests                    # 기존 테스트 전체 스멜
```

팀 테스트 규칙 정본: [skills/gardenstep-test-audit/references/testing-policy.md](skills/gardenstep-test-audit/references/testing-policy.md)

## 새 스킬 추가

```text
skills/<skill-name>/
├── SKILL.md
├── scripts/       # 선택
├── references/    # 선택
├── assets/        # 선택
├── tests/         # 동작 검증
└── evals/evals.json
```

`catalog.json`에 항목을 추가하고 다음 검증을 통과한다.

```bash
python3 scripts/validate_skills.py
python3 -m unittest discover -s tests -v
```

hook·스킬·명령을 바꾸면 `.claude-plugin/plugin.json`의 `version`을 올린다. 상세 규약: [CONTRIBUTING.md](CONTRIBUTING.md)

### DEV 로컬 QA 어댑터 (시범)

이 브랜치의 QA 훅은 Claude·Codex 모두 SessionStart/Stop 접수와 인계 알림만 제공한다. Claude 플러그인 전체 가드레일이 Codex에도 설치되는 것은 아니다. 실제 규칙은 [검증 정책](docs/verification-policy.md), 명령·진단·Figma N/A는 [QA 큐 가이드](hooks/QA-QUEUE.md)를 따른다.

```bash
python3 -m venv .venv-qa
.venv-qa/bin/python -m pip install -r requirements-qa.txt
.venv-qa/bin/python scripts/install_claude_hooks.py install
.venv-qa/bin/python scripts/install_codex_hooks.py install
.venv-qa/bin/python scripts/qa_doctor.py
```

기존 플러그인의 QA 훅과 사용자 설정의 QA 훅은 하나만 활성화한다. 설치 디렉터리/venv를 이동하면 재설치한다. Codex는 `/hooks` 신뢰 검토, 두 도구 모두 일반 세션 접수를 확인한다. QA는 담당·기한·팀 PR/issue 링크를 지정하고 인계표를 공유한다. 원격 게시나 Telegram 전송은 위 명령에서 실행하지 않는다.
