<!--
  각 레포 PR 템플릿의 "Verification" 자리에 이 섹션을 넣는다.
  (gardenstep-server: .github/PULL_REQUEST_TEMPLATE/dev_general.md, main_general.md, main_hotfix.md
   gardenstep / gardenstep_admin: .github/pull_request_template.md 신설)
  CI test-gate가 "테스트 영수증" 제목, 백틱 안 테스트 파일 경로의 존재, 뮤테이션 줄을 검사한다.
  줄 머리 라벨(바뀐 사용자 동작·E2E·순수 로직·뮤테이션 확인·실행·면제)은 바꾸지 않는다.
-->

## 🧪 테스트 영수증

- 바뀐 사용자 동작: <!-- 사용자·운영자·API 소비자 관점 한 문장. 예: 쿠폰 코드를 입력하면 할인된 합계가 보인다 -->
- E2E: `tests/e2e/tier2-<대상>.spec.ts` — "<성공 경로 테스트 제목>" / "<실패 경로 테스트 제목>"
  <!-- 서버: `src/test/java/.../<Name>ControllerTest.java` — "[API] …" (200) / "[API] …" (4xx), 통합은 `<Name>IntegrationTest.java` -->
- 순수 로직: `tests/e2e/tier2-<대상>.unit.spec.ts` — "<제목>" <!-- 없으면 "해당 없음 — 계산 변경 없음" -->
- 뮤테이션 확인: <!-- <파일>의 <무엇>을 <어떻게> 바꾸자 "<테스트 제목>" 실패. 예: coupon.ts의 percent 10→20으로 바꾸자 "10% 쿠폰은…" 실패 -->
- 실행: `<명령>` → <N> passed <!-- 예: `TIER2_FLAG_ON=true npx playwright test tests/e2e/tier2-coupon.spec.ts` → 3 passed -->
- 면제: 없음 <!-- 면제면 사유 + 후속 이슈 번호. `test-exempt` 라벨도 붙인다 -->
