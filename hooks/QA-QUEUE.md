# 로컬 디자인 QA 큐 (실험)

팀 레포의 UI 변경을 감지하면 해시 기반 작업을 로컬 SQLite에 접수한다. PENDING/RUNNING/BLOCKED/STALE/FAIL/PASS 상태로 검증을 추적한다. PASS는 범위와 기록된 관찰이 모두 충족된 경우다. 기존 브라우저 QA run은 link-run으로 연결하고 실제 summary 및 영향 범위·revision을 검증한다.

```
python3 <skills-root>/hooks/qa_queue.py plan --repo <worktree>
python3 <skills-root>/hooks/qa_queue.py enqueue --repo <worktree>
python3 <skills-root>/hooks/qa_queue.py status --repo <worktree>
python3 <skills-root>/hooks/qa_queue.py start --repo <worktree> --id <task-id>
python3 <skills-root>/hooks/qa_queue.py block --repo <worktree> --id <task-id>
python3 <skills-root>/hooks/qa_queue.py link-run --repo <worktree> --id <task-id> --run <existing-run>
python3 <skills-root>/hooks/qa_queue.py link-design --repo <worktree> --id <task-id> --receipt <receipt.json>
```

Claude는 `hooks/hooks.json`의 SessionStart/Stop에서 실행한다. Codex는 `python3 scripts/install_codex_hooks.py install`로 기존 user hooks.json을 보존하며 추가한다. Codex의 `/hooks`에서 새 정의를 검토·신뢰해야 실행된다. 제거는 `uninstall`이다. 격리 모의 세션에서 Claude와 Codex 실행을 확인했다. Codex 모의에는 trust 우회 옵션을 사용했으며 일반 세션 신뢰 여부는 별도 확인한다.

큐는 파일 해시·로컬 경로·상태만 보관한다. 소스 내용과 비밀은 저장하지 않는다. 작업이 바뀌면 이전 대기 작업을 STALE로 처리한다. `gardenstep-qa-run`의 기록된 실행 결과와 검수 증거를 연결한다. 실제 Figma 원본 접근, 충돌/중단 복구와 서비스별 영향 범위 매핑은 별도 확인한다. 이 큐를 배포 차단 조건 또는 사후 QA 완료 증거로 사용하지 않는다.

## 영향 매핑

서비스 레포의 `docs/qa/local-design-map.json`이 정본이다. 각 rule의 `paths` glob, `cards`, `figma_nodes`, `viewports`는 모두 명시한다. 누락된 파일·매핑 및 rule의 open_questions(미확정 기준)은 BLOCKED다. 매핑 파일도 변경 대상이므로 자기 자신에 적용할 규칙을 포함한다. 실제 프로젝트 카탈로그와 Figma 정본을 확인한 후 작성하며, 이 저장소에 내부 노드를 넣지 않는다.

```json
{"schema_version":1,"rules":[{"paths":["components/card.tsx"],"cards":["CARD-ID"],"figma_nodes":["NODE-ID"],"viewports":["pc","mobile"],"checks":["title-visible"]}]}
```

`link-run`은 qa-run의 summary를 다시 계산해 증거 위변조를 검사하고, 변경 파일 매핑·전체 선택 셀·FE revision·clean tree를 대조한다. Figma receipt 없이 성공한 브라우저 run은 BLOCKED로 남긴다. FAIL과 NOT_RUN을 PASS로 바꾸지 않는다.

## Figma 대조 기록 v1

`link-design`은 receipt의 SHA·노드×viewport 범위·출처/조회시각·항목별 기대/실제값·양쪽 비어있지 않은 캡처를 검사하고 파일 해시를 남긴다. 원본/화면 캡처는 receipt와 같은 private 디렉터리 하위에 둔다. `cells`는 node별·viewport별 `node`, `node_url`(같은 Figma 파일의 `node-id` 포함 HTTPS 링크), `viewport`, `verdict`(MATCH/MISMATCH/UNKNOWN), `checks`(각 `item`, `expected`, `actual`), `figma_screenshot`, `actual_screenshot`을 가진다. 최상위 필드는 `schema_version: 1`, `revision`, `source_url`, `source_checked_at`, `observed_at`, `cells`다. 기존 Figma 정본·승인예외·요소 비교 기준은 `gardenstep-qa-run/references/design-parity.md`를 따른다.

이 기록의 MATCH는 사람이 제공한 실제 관찰이며 기계가 스크린샷의 진실성을 보증하지 않는다. screenshot이 생성되었다는 사실만으로 기대값과 동일함을 추론하지 않는다. 각 매핑에서 요구한 checks 전부를 매 node·viewport cell에 기록해야 한다. 원본을 실제로 관찰한 검수자가 source_observer와 independent_source_observation=true를 기록한다. 시간대 포함 ISO 시각, Figma HTTPS URL, PNG/JPEG 전체 디코딩, 파일 및 node-id 일치와 각 셀의 증거를 검사한다. Pillow는 `python3 -m pip install -r requirements-qa.txt`로 설치한다. QA와 Figma 두 영수증이 모두 충족되면 PASS다. 독립 관찰과 스크린샷 진위는 검수자의 증언이며 프로그램이 보증하지 않는다. 출처 미접근·기준 미확정은 BLOCKED다. link-design 이후 link-run을 호출한다.
