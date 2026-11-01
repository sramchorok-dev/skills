# 설치된 로컬 실행기로 운영 대기 시간 줄이기

실행 머신에 검증된 `gardenstep-local-deploy`와 `gardenstep-fast-deploy`가 설치되어 있을 때만 적용한다. 이 공용 저장소는 개인 SSH 키·호스트 설정·Docker 인증·로컬 runner를 배포하지 않는다. 기본 GitHub 경로는 로컬 실행기 없이 사용 가능하다.

## 준비: 배포 창 밖에서 테스트

```bash
# 실제 설치 위치로 지정한다. 팀원 PC에 있다고 가정하지 않는다.
GSDEPLOY="/absolute/path/to/installed/gsdeploy"
GSFAST="/absolute/path/to/installed/gsfast"
# 기존 gsfast는 heavy lock과 멈춤 감시를 제공한다.
"$GSFAST" test server fe
```

`gsfast test`는 origin/dev HEAD의 테스트 증거를 만든다. 운영 main의 tree와 cicd.yml blob이 다르면 재사용되지 않는다. merge 결과가 dev tree와 같을 때만 사전 준비의 효과가 있다. test는 서버 배포를 하지 않지만 무거운 로컬 작업이므로 동시 빌드와 겹치지 않게 한다.

## 실행 직전: 정확한 main 재확인

```bash
git -C "$SERVICE_REPO" fetch origin main dev
python3 "$RELEASE_SKILL/scripts/release.py" plan \
  --repo "$SERVICE_REPO" --target prod --executor "$GSDEPLOY" \
  --evidence "$EVIDENCE_JSONL"
```

`EVIDENCE_JSONL`은 기존 실행기가 만든 ledger다. 파일을 직접 만들어 PASS를 가장하지 않는다. helper의 MATCH는 후보 일치 확인이며 실행기가 최종적으로 다시 검사한다. 증거가 없으면 필수 테스트가 실행되므로 빨라진다고 보고하지 않는다. 기존 실행기는 만료 시간을 강제하지 않으므로 의존성·외부 계약·검증 환경이 바뀌거나 증거 신뢰가 불분명하면 새 테스트를 수행한다.

같은 서비스·SHA의 GitHub 배포가 active인지 확인한다. active면 기다리거나 승인된 대체 절차로 중단한 뒤 진행하고 둘을 동시에 실행하지 않는다. main 머지는 기본적으로 GitHub 배포를 시작하므로 로컬 경로를 고르기 전에 이 조건을 계획한다.

## 승인된 운영 실행

```bash
# plan이 출력한 full SHA/서비스와 실제 원격 main이 일치해야 한다.
"$GSDEPLOY" deploy server --sha "$PROD_SHA" --target prod \
  --confirm "DEPLOY-PROD-${PROD_SHA:0:7}" --reuse-tested --dry-run
# 현재 대화에서 해당 운영 배포가 승인되고 dry-run 검토까지 끝났을 때
"$GSDEPLOY" deploy server --sha "$PROD_SHA" --target prod \
  --confirm "DEPLOY-PROD-${PROD_SHA:0:7}" --reuse-tested
```

FE/admin은 서비스 인자를 바꾼다. 각 실행기의 필수 drift·DB snapshot·Figma·감사·health/revision 조건은 유지한다. raw gsdeploy에는 gsfast의 전체 stall watchdog이 없으므로 장기 무출력을 추적하며 host 변경 중인지 확인 없이 강제 종료/재실행하지 않는다. FE의 Figma 예외 인자를 자동으로 추가하지 않는다.

AI 운영에는 위 명령을 사용하지 않는다. 기존 `production.yml`을 실행한다. 사용자에게 제시하는 시간은 새 측정 전까지 ‘테스트를 미리 수행해 운영 대기 구간을 줄임’으로 표현한다. 서비스의 기본 Actions YAML 자체를 최적화한 것은 아니다.
