# 로컬 디자인 QA 큐 (실험)

팀 레포의 UI 변경을 감지하면 해시 기반 작업을 로컬 SQLite에 접수한다. 코드는 PENDING/RUNNING/BLOCKED/STALE만 관리하며 검증 통과를 자동 주장하지 않는다. 기존 브라우저 QA run은 link-run으로 연결하고 실제 summary 검증을 수행한다. 변경 범위·revision을 자동 대조하지 않으므로 큐의 통과 판정에는 사용하지 않는다.

```
python3 <skills-root>/hooks/qa_queue.py plan --repo <worktree>
python3 <skills-root>/hooks/qa_queue.py enqueue --repo <worktree>
python3 <skills-root>/hooks/qa_queue.py status --repo <worktree>
python3 <skills-root>/hooks/qa_queue.py start --repo <worktree> --id <task-id>
python3 <skills-root>/hooks/qa_queue.py block --repo <worktree> --id <task-id>
python3 <skills-root>/hooks/qa_queue.py link-run --repo <worktree> --id <task-id> --run <existing-run>
```

Claude는 `hooks/hooks.json`의 SessionStart/Stop에서 실행한다. Codex는 `python3 scripts/install_codex_hooks.py install`로 기존 user hooks.json을 보존하며 추가한다. Codex의 `/hooks`에서 새 정의를 검토·신뢰해야 실행된다. 제거는 `uninstall`이다. 수동 실행/단위 테스트만 확인했고 실제 양쪽 세션 동작은 미검증이다.

큐는 파일 해시·로컬 경로·상태만 보관한다. 소스 내용과 비밀은 저장하지 않는다. 작업이 바뀌면 이전 대기 작업을 STALE로 처리한다. `gardenstep-qa-run`의 실제 실행·증거와 큐 완료 상태 연결, 충돌/중단 복구, Figma 영향 범위 매핑은 후속 작업이다. 이 큐를 배포 차단 조건 또는 사후 QA 완료 증거로 사용하지 않는다.

## 영향 매핑

서비스 레포의 `docs/qa/local-design-map.json`이 정본이다. 각 rule의 `paths` glob, `cards`, `figma_nodes`, `viewports`는 모두 명시한다. 누락된 파일·매핑은 BLOCKED다. 매핑 파일도 변경 대상이므로 자기 자신에 적용할 규칙을 포함한다. 실제 프로젝트 카탈로그와 Figma 정본을 확인한 후 작성하며, 이 저장소에 내부 노드를 넣지 않는다.

```json
{"schema_version":1,"rules":[{"paths":["components/card.tsx"],"cards":["CARD-ID"],"figma_nodes":["NODE-ID"],"viewports":["pc","mobile"]}]}
```

`link-run`은 qa-run의 summary를 다시 계산해 증거 위변조를 검사하고, 변경 파일 매핑·전체 선택 셀·FE revision·clean tree를 대조한다. 현재 Figma 대조 receipt를 검증할 수 없어 성공한 브라우저 run도 BLOCKED로 남긴다. FAIL과 NOT_RUN을 PASS로 바꾸지 않는다.
