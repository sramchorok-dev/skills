# Gardenstep 테스트 규칙 v1

적용: `gardenstep`(FE) · `gardenstep_admin` · `gardenstep-server` · `gardenstep-ai`. 확정 2026-09-16, PR 검증 문구 개정 2026-09-21. 정본은 이 파일이며, 각 레포 PR 템플릿과 CI `test-gate`가 이 규칙을 집행한다.

## DEV 시범 적용 범위

DEV의 실행 시점은 `docs/verification-policy.md`와 completion-qa의 DEV fast deployment 절을 따른다.
테스트 품질 기준은 유지하되 전체 검증을 배포 전에 동기적으로 기다리는 조건으로 삼지 않는다.
`--dev-pilot`은 PR 본문의 미완료를 WARN으로 드러낸다. 사후 자동 접수 미구현 구간은 명시한다.
운영 대상은 아래 기존 게이트를 유지한다. 현재 서비스 CI의 needs는 별도 수정 전까지 바뀌지 않는다.

## 0. 한 줄 원칙

**바뀐 사용자 동작 하나에 사용자 경로 테스트 하나. 계산이 바뀌면 순수 로직 테스트 하나. 둘 다 없는 PR은 리뷰를 시작하지 않는다.**

## 1. 왜 E2E 중심인가

- AI로 만든 코드는 내부 구조가 자주 바뀐다. 구현에 묶인 단위 테스트는 코드와 함께 버려진다. 사용자 경로 테스트는 구현이 바뀌어도 살아남는다.
- 작성자 혼자 확인하기 어려운 것은 "화면과 API가 실제로 사용자에게 동작하는가"다. E2E가 그 증거를 만든다.
- 세 레포 모두 Playwright·MockMvc·실 MySQL 통합 인프라가 CI에 이미 있다. 추가 비용 없이 바로 쓴다.

## 2. 테스트 3층

| 층 | 무엇을 증명하나 | FE(`gardenstep`) | Admin | Server |
|---|---|---|---|---|
| **사용자 경로(E2E)** | 사용자·운영자·API 소비자에게 보이는 동작 | `tests/e2e/tier2-<대상>.spec.ts` (Playwright, route 모킹) | `tests/e2e/<화면>.spec.ts` | `*ControllerTest`·`*ApiTest`·`*SecurityTest` (MockMvc), `*IntegrationTest` (실 MySQL/Redis) |
| **순수 로직** | 금액·수량·상태 전이·날짜·변환 | `tests/e2e/<대상>.unit.spec.ts` (`page` 없음) | `lib/<대상>.test.ts` (`node --test`) | `@DisplayName("[단위] …")` mock 없는 JUnit |
| **계약·구조** | 레포 간 어휘와 아키텍처 규약 | `tier2-event-names.unit.spec.ts`, `tier2-order-status.unit.spec.ts` | `lib/orderStatus.test.ts` 전이표 | `*ContractTest`, `Tier2ArchitectureTest` (ArchUnit) |

Mock은 **우리가 소유하지 않는 경계**에서만 쓴다: PG·S3·SES·LLM·외부 API·브라우저 밖 네트워크. 우리 서비스가 우리 서비스를 부르는 자리를 mock으로 막고 호출 여부만 확인하는 테스트는 남겨도 되지만 **게이트 증거로 인정하지 않는다**.

## 3. PR 승인 게이트 — 필수 테스트 매트릭스

변경 유형은 diff의 파일 경로로 정해진다. 한 PR에 여러 유형이 섞이면 모두 적용된다.

| 변경 유형 | 필수 (없으면 FAIL) | 권장 (없으면 WARN, 리뷰어 판단) |
|---|---|---|
| FE 화면·컴포넌트·훅·atom (`app/ containers/ components/ hooks/ atoms/ store/`) | 브라우저 spec: **도달 1 + 핵심 인터랙션 1 + 실패 경로 1** | 영향받는 모바일 뷰포트 1 |
| FE 새 라우트 (`app/**/page.tsx` 추가) | 위 + `tier2-flag-off.spec.ts`에 404 케이스 | — |
| FE 순수 로직 (`lib/ utils/ api/ constants/ actions/`) | `.unit.spec.ts`, 기대값은 스펙·손계산 | — |
| Admin 화면 | 브라우저 spec: **비로그인/권한 없음 1 + 성공 1 + 실패 1** | — |
| Admin 순수 로직 (`lib/`) | `lib/*.test.ts` | — |
| Server 컨트롤러·DTO (`presentation/`) | MockMvc: **정상 응답 1 + 4xx 1** (권한 있는 API는 401/403 포함) | — |
| Server 서비스·도메인 계산 | mock 없는 `[단위]` | — |
| Server 영속·트랜잭션·동시성·스케줄러 | `*IntegrationTest` (Support 상속, 실 MySQL/Redis) | — |
| Server Liquibase (`db/changelog/`) | 통합 테스트 + 마이그레이션 검증 | 롤백 순서 PR 본문 기재 |
| 레포 간 계약 (주문 상태·이벤트명·DTO 필드) | **양쪽 레포 각각** 테스트 + PR 상호 링크 + 배포 순서 | — |
| 버그 수정 | **재현 테스트** — 수정 전 실패 증거(커밋 순서 또는 PR 검증 한 줄) | — |
| 결제·환불·금액·재고·권한·개인정보 | 위 전부 + 실패·경합·멱등 케이스 + **리드 승인 필수** | — |
| 문서·설정·CI만 | 없음 (CI 초록이면 통과) | — |

승인 조건 (전부 충족):

1. PR 본문 **검증** 섹션에 확인한 동작·테스트 방식과 환경·결과를 짧게 적는다 (양식: `assets/pr-test-receipt.md`). 기존 `🧪 테스트 영수증` 제목도 점검기가 계속 허용한다.
2. CI `test` 잡 초록. `test-gate`(이 스킬의 스크립트) 판정 PASS 또는 WARN.
3. WARN 항목은 리뷰어가 사람 눈으로 확인했다.
4. 리뷰어 1명 승인. 결제·환불·금액·재고·권한·스키마는 리드 승인.

## 4. 작성 규칙 (전부 MUST)

1. **제목은 "조건이면 기대 결과다" 한국어 문장.** `test('재고 1개 상품은 두 번째 담기에서 stock_limit을 돌려준다')`. 서버는 `@DisplayName("[단위|통합|API] …")`.
2. **셀렉터는 `data-testid`만.** 예외는 FE `tests/e2e/README.md` §2의 두 가지뿐(문구 자체가 검증 대상, 접근성 계약 자체가 검증 대상).
3. **하드 대기 금지.** `waitForTimeout`·`Thread.sleep`·테스트 안 `setTimeout` 금지. Playwright 자동 대기, Awaitility, `StepVerifier`를 쓴다.
4. **값을 단언한다.** 기대값은 스펙·기획서·손계산에서 온다. 구현 함수를 다시 불러 비교하지 않는다. `toBeTruthy()`·`assertTrue(true)`·스냅샷 단언 금지. mock 호출 여부만 단언한 테스트는 증거가 아니다.
5. **사용자 경로 spec마다 실패 경로 1개.** 4xx·빈 상태·권한 없음·만료·네트워크 오류 중 하나. 제목에 드러나게 쓴다.
6. **격리.** 테스트끼리 순서 의존 금지. 시드는 테스트 안에서(FE는 full load 전 localStorage 시드). CI에서 실서버·실계정·실PG 금지 — route 모킹 또는 stub provider.
7. **skip/only/Disabled.** `.only` 금지. skip은 `test.skip(환경조건, '이슈번호 + 사유')` 가드만 허용. `@Disabled("이슈번호 + 사유")` 필수.
8. **같은 여정이 두 번 나오면 헬퍼로.** FE `tests/e2e/helpers/`, Admin spec 상단 `session()` 패턴, Server `support/`.
9. **파일 하나 = 화면·도메인 하나. 테스트 하나 = 시나리오 하나.** 단언은 여러 개여도 되지만 시나리오는 하나.
10. **테스트 데이터에 실제 개인정보·키 금지.** 합성 데이터만.

## 5. AI 생성 테스트 추가 확인

AI는 "통과하는 테스트"를 잘 만든다. 우리는 "구현이 틀리면 떨어지는 테스트"가 필요하다.

- **결함 감지 1회.** 구현 한 곳을 일부러 망가뜨린다(숫자 바꾸기·조건 뒤집기·early return). 방금 만든 테스트가 빨간불이 되는지 본다. PR의 `결함 감지` 줄에 무엇을 바꿔 어떤 테스트가 실패했는지 한 줄 적는다. 기존 `뮤테이션 확인` 줄도 허용한다. 안 떨어지면 그 테스트는 아직 없는 것이다.
- **기대값 출처 확인.** 테스트가 구현을 import해 기대값을 계산하면 다시 쓴다.
- **mock 경계 확인.** AI가 우리 코드끼리 mock을 걸었으면 통합 테스트로 바꾼다.
- **제목 다시 읽기.** 영어·모호한 제목(`works`, `renders correctly`)은 사람이 다시 쓴다.
- **리팩터링 때 테스트가 통째로 바뀌었다면** 구현에 묶인 테스트였다는 신호다. 사용자 경로 기준으로 다시 쓴다.

## 6. 승인 절차 · 면제 · 위반

- 순서: PR 검증 작성 → CI 초록 → `gardenstep-test-audit` PASS/WARN → 리뷰 → 승인 → 머지.
- CI 빨간불 또는 FAIL 판정 PR은 **리뷰를 시작하지 않는다.** 리뷰어 시간을 지킨다.
- **면제**: `test-exempt` 라벨 + PR 검증의 `면제` 줄에 사유 + 리드 승인. 후속 이슈 필수. 문구·스타일만 바뀐 PR이 여기 해당한다.
- **핫픽스**: 머지 후 24시간 안에 테스트 PR을 올린다.
- **위반 머지**(빨간 X 상태 머지, 검증 결과 없음): `dev`에서 즉시 revert한다. 재발 방지는 이 문서 개정으로 한다.

## 7. 강제 수단 — 지금 가능한 것과 다음 단계

2026-09-16 확인: `sramchorok-dev`는 GitHub 무료 플랜이라 private 레포에 **브랜치 보호·필수 상태 체크·CODEOWNERS 강제가 켜지지 않는다**(API 403). "반드시"를 기계로 만들려면 아래 순서로 간다.

| 단계 | 수단 | 효과 |
|---|---|---|
| 1 (지금) | 각 레포 CI에 `test-gate` 잡 추가 (`assets/test-gate.yml`). PR마다 이 스킬 스크립트 + 검증 섹션 검사 → 빨간 X + Step Summary | 위반이 PR 화면에 보인다. 팀 규칙 "빨간 X 머지 금지·위반 시 revert"와 결합 |
| 1 (지금) | PR 템플릿에 짧은 검증 섹션 (`assets/pr-test-receipt.md`) | 무엇을 테스트했는지 PR에서 바로 읽는다 |
| 1 (지금) | 팀원 각자 이 스킬 설치 → PR 열기 전 자기 점검 | 리뷰 라운드 감소 |
| 2 | GitHub Team 업그레이드 (4명 기준 월 $16) → required checks(`test`, `test-gate`) + required review 1 + CODEOWNERS(결제·스키마 경로 리드) | 머지 버튼이 실제로 잠긴다 |

배포 게이트는 이미 있다: `dev`/`main` push에서 `test` 잡이 실패하면 `deploy`가 돌지 않는다.

## 8. 엄격함을 유지하면서 효율을 지키는 장치

- 필수는 **바뀐 동작**에만 붙는다. 전체 커버리지 % 목표는 두지 않는다.
- 스멜 판정도 **바뀐 줄**에만 붙는다. 손대지 않은 줄의 오래된 경고는 "기존 부채"로 보이기만 한다. 기존 부채는 PR 차단 사유가 아니며, 그 파일을 만질 때 여유가 있으면 한두 개 같이 고친다(보이스카우트 규칙). 대량 정리 PR은 만들지 않는다.
- 빠른 층부터: `.unit.spec` → 해당 spec 파일 하나 → CI는 §8.1의 필수 선택 집합 또는 전체 suite를 실행한다.
- 서버 통합 테스트는 `IntegrationTestSupport`/`PersistenceTestSupport`를 상속해 컨텍스트 캐시를 공유한다. 새 컨텍스트 하나가 suite를 분 단위로 늘린다.
- 시간 예산: spec 하나 30초(`playwright.config.ts` timeout), FE `test` 잡 25분 상한.
- 리뷰어는 스크립트 결과부터 본다. 사람 눈은 스크립트가 못 보는 6가지(SKILL.md 3단계)에만 쓴다.

## 8.1 변경 영향 선택과 성공 PR 재사용 (2026-10-24)

전체 검증을 기본값으로 두되, 아래 증거가 있는 결정적 suite만 선택 실행을 허용한다. 브라우저 에이전트의
수동 DEV 실행은 CI에 연결하지 않으며 §3 사용자 경로 spec·순수 로직·계약 검사를 대체하지 않는다.

- 변경 경로→필수 suite 분류표를 버전 관리하고 선택/제외 이유·전체 목록·분류 결과를 실행 artifact에 남긴다.
  분류 실패·알 수 없는 변경·공통 코드·의존성/빌드설정·금액/권한/인증/개인정보/재고/결제·마이그레이션은 전체
  fallback이다. docs/design처럼 테스트 입력인 자료는 일반 문서 제외에 넣지 않는다.
- 선택 집합의 결과가 모두 존재해야 gate가 성공한다. 예상 프로필/테스트 누락·취소·실패를 빈 성공으로 처리하지
  않는다. 명시 전체 검증 경로를 유지하며 main·직접 push·확인 불가능한 실행은 전체 검증한다.
- 먼저 shadow 분류와 기존 전체 결과를 대조한다. false negative가 없는 근거 없이 실행 범위를 줄이지 않는다.
  현재 FE는 12프로필 전부 실행을 유지한다. 제안 제외는 보고만 하며 skipped=[] 계약이다.
- 동일 코드를 다시 실행하지 않는 DEV push 재사용은 정확한 PR merge commit·동일 git tree·동일 저장소 head·동일
  workflow·completed success·최신 필수 test job 성공까지 확인해야 한다. API 실패·필수 증거 부족은 전체 실행한다.
  main은 재사용하지 않는다. Admin PR 새 커밋은 이전 PR 검증을 취소할 수 있으나 배포/롤백 그룹과 분리한다.
- 전수 도면 조합을 분리해도 대표 계산·BOM·금액·기후/크기 경계·실패/자원제한 회귀는 상시 실행한다.
  분리 집합의 실제 실행 목록·결과가 검증되어야 하며 자동 skip만으로 CI가 녹색이 되어서는 안 된다.
- 하나의 workflow에서 반복하던 동일 계약 검사를 1회로 모을 수 있다. 최종 test 집계가 그 결과를 의존해야
  하며 계약 검사 실패/누락은 배포를 차단한다.

선택 실행 정책의 성공 기준은 실행 건수 감소가 아니라 필수 동작 보존과 추적 가능한 누락0이다. 전체 경과와
runner 합계는 따로 측정한다. 외부 계정/실서비스를 쓰는 브라우저 agent 셋은 수동 인수 검수이며 이 정책의 CI
대역 테스트와 다른 증거로 보고한다. ADR: `docs/adr/0005-browser-acceptance-and-ci-selection.md`.


## 9. FAQ

- **문구·스타일만 바꿨는데 FE-E2E가 걸려요.** 문구가 검증 대상이면 `toContainText` 갱신. 동작 변화가 없으면 `test-exempt` + 사유. 리뷰어가 동의하면 통과.
- **테스트가 너무 오래 걸려요.** 파일 단위로 돌린다. CI는 §8.1에 따라 핵심 상시 + 영향 집합을 실행하며 불명확하면 전체 실행한다. 서버는 `--tests '패키지.*'`.
- **mock을 어디까지?** 우리 밖(PG·S3·SES·LLM·외부 API)만. 우리 코드끼리는 통합으로.
- **기존 테스트가 깨졌어요.** 동작 변경이 의도면 테스트를 스펙 기준으로 고치고 PR 검증에 이유를 쓴다. 의도가 아니면 버그다.
- **CI에서만 실패해요.** 하드 대기·순서 의존·환경 가드 누락을 먼저 의심한다. `retries: 2`는 플레이크를 숨길 뿐 고치지 않는다.
- **레포 간 계약을 바꿨어요.** 상태·이벤트명·DTO 필드는 양쪽 테스트 + 배포 순서. FE `orderStatus` ↔ Server `customerPhase` 같은 매핑은 둘 다 고친다.
