# sramchorok-dev Skills

업무 생산성을 위한 공통 Agent 스킬 저장소. Claude Code, Codex, OpenCode에서 같은 스킬을 재사용한다.

## 스킬 목록

| 스킬 | 분야 | 용도 |
|---|---|---|
| [`gardenstep-report-wiki`](skills/gardenstep-report-wiki/) | 보고·공유 | Gardenstep HTML 보고서 공개 DEV Wiki 게시 |

## 설치

```bash
git clone https://github.com/sramchorok-dev/skills.git
cd skills
python3 scripts/install.py gardenstep-report-wiki
```

설치기는 `~/.agents/skills/`에 저장소 스킬을 symlink한다. `~/.agents/sync.py`가 있으면 dry-run 후 Claude Code·Codex·OpenCode로 동기화한다.

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

상세 규약: [CONTRIBUTING.md](CONTRIBUTING.md)
