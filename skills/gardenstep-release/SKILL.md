---
name: gardenstep-release
description: Gardenstep DEV·운영 배포를 준비하고 빠른 실행 경로와 후검증을 연결한다. 빠른 배포, 운영 배포 준비, 동일 소스 테스트 재사용, 후검증 상태 확인 요청에 사용한다. 운영 실행은 명시된 대상·범위의 배포 지시가 있을 때만 한다.
---

# Gardenstep 공용 배포

필수: Python 3.10+, Git, 인증된 gh. 로컬 빠른 경로는 별도로 설치된 gsdeploy 실행기가 필요하다.

같은 변경을 여러 번 배포하지 않고, 완료된 검증을 정확한 소스·워크플로에 한해서 재사용한다. **스킬 설치만으로 서버 CI가 빨라지거나 운영 검증이 제거되지는 않는다.** 기본은 GitHub Actions, 설치된 로컬 실행기가 있을 때만 로컬 빠른 경로를 선택한다. 개인 호스트·SSH 키·토큰은 이 스킬에 포함하지 않는다.

## 1. 계획

1. 서비스 worktree의 AGENTS·현재 workflow·운영 런북과 열린 PR을 읽는다. dev/main을 fetch한다.
2. 승인된 변경을 환경별로 묶고 실제 실행 SHA와 비교해 이미 반영된 서비스는 제외한다. GitHub 실행 성공만으로 현재 서버 SHA를 추정하지 않는다.
3. `scripts/release.py plan --repo <서비스 경로> --target dev|prod`로 정확한 SHA/tree/workflow를 기록한다. 실제 확인한 값만 `--running-sha`에 넣는다. helper는 원격 배포·머지·알림을 실행하지 않는다.
4. DEV는 짧은 범위 검토 후 배포·후검증을 분리한다. 운영은 기존 필수 검증과 승인 범위를 유지한다. 준비·설명 요청을 운영 실행 지시로 해석하지 않는다.

## 2. 경로 선택과 실행

| 경로 | 적용 | 실행 |
|---|---|---|
| GitHub 기본 | 모든 팀원, FE·BE·admin·AI | 대상 브랜치 PR을 검토해 승인 범위 내에서 머지하고 기존 배포 workflow를 추적 |
| 로컬 빠른 DEV | gsfast/gsdeploy가 설치·설정된 실행 머신 | 변경 서비스만 배치. 기존 gsfast가 잠금·타임아웃·순서를 관리 |
| 로컬 빠른 운영 | gsdeploy가 설치된 실행 머신, FE·BE·admin | 미리 통과한 동일 tree/workflow 테스트 증거를 `--reuse-tested`로 재사용. 빌드·감사·배포·기동·revision·기존 Figma/DB 조건은 유지 |
| AI 운영 | GitHub production.yml | 로컬 gsdeploy 운영은 미지원. AI를 FE/BE 로컬 명령에 섞지 않는다 |

로컬 빠른 경로의 실제 명령·전제는 [references/local-fast.md](references/local-fast.md)를 읽는다. 실행기가 없으면 설치됐다고 가정하거나 개인 파일을 복사하지 말고 GitHub 경로를 사용한다. 이 공용 스킬은 로컬 실행기 배포 패키지가 아니다.

GitHub 경로에서는 `dev → main` 머지가 운영 배포를 시작한다. 로컬 경로를 고른 뒤 같은 SHA의 GitHub 배포가 진행 중이면 중복 실행하지 않는다. Actions 중단/대체가 필요한 상황은 사용자에게 구체적 실행 계획을 제시하고 이미 승인된 범위에서만 처리한다. `[skip ci]`나 무조건 `--skip-tests`로 운영 검증을 우회하지 않는다.

선행 테스트는 배포 전에 미리 끝내고 변경 PR을 한 번에 묶는다. 운영용 환경값이 포함된 FE/admin 이미지는 DEV 이미지를 그대로 승격하지 않는다. DB/API 의존성에 따라 순서를 정하고 한 서비스 실패 시 후속 배포를 멈춘다. 대기 중인 운영 실행을 반복 발행하지 않는다.

## 3. 후검증 — 세 상태로 보고

| 시점 | 실행·담당 | 완료 증거 |
|---|---|---|
| 배포 직후 | 배포 작업자 | 실제 SHA/이미지, health, 배포 이력. 이것이 배포 성공 |
| DEV 자동 사후 | 저장소 isolated regression + 배포 작업자의 결과 확인 | 정확한 deployment ID/attempt/SHA를 가진 identity artifact와 전체 CI 성공 |
| 실제 사용자 경로 | 변경 작업자 또는 지정 QA 담당 | 해당 revision의 DEV 브라우저 결과, 시각 변경이면 승인 Figma와 대조 기록 |

`release.py postqa --repo sramchorok-dev/<repo> --deployment-id <id> --attempt <n> --sha <full-sha>`는 DEV FE·BE·AI 결과를 읽고 identity를 검증한다. workflow가 dev HEAD에서 실행되므로 Actions headSha만 대조하지 않는다. 이 helper는 읽기 전용이며 누락 실행을 새로 발행하거나 Telegram 메시지를 보내지 않는다.

- PASS: 자동 회귀의 범위만 통과. 실환경 브라우저/Figma 완료와 다르다.
- PENDING/RUNNING: 대기·진행. 담당과 다음 확인 시각을 남긴다.
- FAIL: 실행 링크에서 원인을 확인하고 수정→배포→새 버전 검증. 기존 실패를 삭제하거나 성공으로 덮지 않는다.
- MISSING/AMBIGUOUS/UNVERIFIED/ERROR: 접수·중복·신원 증거·접근 문제를 조사한다. 무작정 dispatch하지 않는다.

로컬 검수는 `qa_queue.py assign`으로 담당·다음 영업일까지의 기한·팀 PR/issue 링크를 지정한다. `handoff`를 PR 검증 섹션에 반영하고 전용 `gardenstep-qa-run`으로 실제 검수한다. 비시각 변경은 사유 있는 Figma N/A, 기능 검수는 유지한다. PC가 꺼진 동안 중앙 자동 감시가 되는 것은 아니다.

운영은 기존 사전 필수 gate를 유지하고, 배포 후 실제 운영 revision/health와 안전한 핵심 경로를 확인한다. DEV postqa를 운영 검증으로 표기하지 않는다. rollback은 각 서비스 런북과 사용자 승인 범위를 따른다.

## 보고 형식

`서비스 | SHA | 빌드 | 배포/health | 자동 회귀 링크·판정 | 실환경/Figma | 담당·기한 | 다음 조치`

배포 성공, 자동 회귀 PASS, 사용자 경로 검수 완료를 각각 적는다. 소요 시간은 준비 테스트와 실제 배포 시간을 나눠 보고하며 이번 실행으로 측정하지 않은 단축 시간을 약속하지 않는다.
