# 레포별 테스트 위치·명령·함정

스크립트와 CI는 계속 바뀐다. 명령을 실행하기 전에 각 레포의 `package.json`·`build.gradle`·`.github/workflows/cicd.yml`을 다시 확인한다. 워크스페이스 루트(`chorok/`)는 git 레포가 아니다 — 반드시 레포 디렉터리로 들어가서 실행한다.

## `gardenstep` (FE, Next.js 16 · Playwright만)

| 항목 | 값 |
|---|---|
| 브라우저 spec | `tests/e2e/tier2-<대상>.spec.ts` — 로컬 서버 필요 |
| 순수 로직 spec | `tests/e2e/tier2-<대상>.unit.spec.ts` — `page` 픽스처 금지 |
| 헬퍼 | `tests/e2e/helpers/tier2.ts`, `helpers/address.ts` |
| 규칙 문서 | `tests/e2e/README.md` (jotai 시드는 full load 전, 셀렉터 예외 2가지, remote 가드 spec은 CI 목록에도 추가) |
| 실행 | `TIER2_FLAG_ON=true npx playwright test tests/e2e/tier2-<대상>.spec.ts` (서버 `npm run dev` 선행) |
| 순수 로직만 | `npx playwright test tests/e2e/tier2-<대상>.unit.spec.ts` |
| CI 게이트 | `test` 잡: flag-off(3001) → remote(3002) → Inicis/Toss/payment-disabled/beta-lab 그룹 → build → start(3000) → `npm test`. PR은 test만, push는 배포까지 |
| 함정 | CI에 lint/`tsc --noEmit` 스텝이 없다(2026-09-16 기준). 새 remote 가드 spec은 `cicd.yml` remote 스텝 목록에도 넣어야 실제로 돈다. `page.route`로 API를 모킹하고 실 서버는 쓰지 않는다 |

## `gardenstep_admin` (Admin, Next.js · node --test + Playwright)

| 항목 | 값 |
|---|---|
| 순수 로직 | `lib/<대상>.test.ts` — `node --test`, import에 `.ts` 확장자 |
| 브라우저 spec | `tests/e2e/<화면>.spec.ts` — `webServer`가 3100 포트 자동 기동, `NEXT_PUBLIC_API_URL=http://api.example.test`를 `page.route`로 전부 모킹 |
| 실행 | `npm test` · `npm run test:e2e` · `npx tsc --noEmit` · `npm run lint`(경고 0) |
| CI 게이트 | typecheck → lint → unit → build → Playwright. 전부 통과해야 `deploy` |
| 함정 | `STATUS_TRANSITIONS`는 서버 `ALLOWED_TRANSITIONS`의 부분집합 — 서버가 상태를 추가하면 여기 테스트도 바뀐다. 권한 경로(비로그인·비관리자)는 spec마다 필수 |

## `gardenstep-server` (Spring Boot 3.5 · Java 21 · JUnit 5)

| 항목 | 값 |
|---|---|
| 단위 | `src/test/java/.../<패키지>/<Name>Test.java`, `@DisplayName("[단위] …")`, 계산은 mock 없이 |
| API | `<Name>ControllerTest` · `<Name>ApiTest` · `<Name>SecurityTest` — `@AutoConfigureMockMvc`, 정상 1 + 4xx 1 |
| 통합 | `<Name>IntegrationTest` — `IntegrationTestSupport`(서비스+리포지토리) 또는 `PersistenceTestSupport`(`@Import` 최소 빈) 상속. 실 MySQL 8.4 + Redis |
| 계약·구조 | `<Name>ContractTest`, `architecture/Tier2ArchitectureTest.java`(ArchUnit: enum name 저장, List 컨버터 금지, 컨트롤러→리포지토리 금지, 트랜잭션 안 외부 I/O 금지) |
| 로컬 준비 | `docker compose -f docker-compose.test.yml up -d mysql-test redis-test` |
| 실행 | `./gradlew test --tests 'ai.gardenstep.gardenstepserver.application.tier2.<패키지>.*'` · 전체 `./gradlew test` (JaCoCo 리포트 생성, 임계치 없음) |
| CI 게이트 | `dependency-audit`(Trivy·환경 계약) → `test`(MySQL/Redis 서비스) → push면 `build`·`deploy` |
| 함정 | `docs/`는 gitignore — 문서는 워크스페이스 `chorok/docs/`에. `@SpringBootTest`를 새로 만들지 말고 Support를 상속(2026-09-09 OOM 사례로 heap 2g). LLM·외부 호출은 트랜잭션 밖. Liquibase 변경은 `src/test/resources/db/changelog/*-migration-test.yaml` 패턴 |

## `gardenstep-ai` (챗봇 서버)

서버와 같은 규칙. CI `test` 잡이 MySQL/Redis 서비스로 `./gradlew test`. `schema-validate.yml`이 별도로 돈다. 2026-08-25 감사 기준 잔여 P1: PII 스크러버·이미지 잡 실행 계층 테스트 0건.

## 레포 간·배포 후

| 항목 | 값 |
|---|---|
| DEV 실계정 스모크 | 워크스페이스 `tests/dev-account-e2e/run.sh` — CI 밖, 머지·배포 후 수동. 계정 정본 `docs/ops/dev-qa-accounts.md` |
| 실행 증거 게이트 | `chorok-completion-qa` 스킬 — TC·통합/빌드·E2E·라이브 스모크 실행 결과를 영수증으로. 이 스킬(test-audit)은 **코드 자체**를 본다 |
| 계약 변경 | 상태 어휘(ADR-0002), 이벤트 이중 발행(ADR-0006), 카탈로그 계약(ADR-0007)은 `chorok/docs/adr/`. 양쪽 레포 테스트 + 배포 순서 |
