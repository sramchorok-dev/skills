# 테스트 스멜 카탈로그

`scripts/audit_tests.py`가 찾는 규칙과, 스크립트가 못 찾아 사람이 봐야 하는 규칙. 각 항목은 나쁜 예 → 좋은 예 → 왜.

## 스크립트가 찾는 것

### S-ONLY · S-FIXME · S-SKIP (FAIL)

```ts
test.only('…')                 // ❌ 나머지 테스트가 조용히 안 돈다
test.skip('만료 쿠폰', …)       // ❌ 사유 없는 skip — 영원히 안 돈다
test.skip(process.env.TIER2_REMOTE_MODE !== 'true', 'remote 서버 계약 검증'); // ✅ 환경 가드 + 사유
```

Java: `@Disabled` 단독은 FAIL, `@Disabled("CHR-123 재고 계약 확정 후 복구")`는 WARN(이슈 닫히면 제거).

### S-HARD-WAIT (FAIL)

```ts
await page.waitForTimeout(1000);                       // ❌ 느린 CI에서 깨지고 빠른 로컬에선 숨는다
await expect(page.getByTestId('tier2-order-done')).toBeVisible({ timeout: 10_000 }); // ✅ 상태를 기다린다
```

Java: `Thread.sleep(500)` → `Awaitility.await().untilAsserted(...)`, Reactor는 `StepVerifier`.

### S-SELECTOR (FAIL) · S-SELECTOR-EXCEPTION (WARN)

```ts
page.locator('.coupon-btn')      // ❌ 스타일 바꾸면 깨진다
page.locator('#total')           // ❌
page.getByTestId('tier2-coupon-apply') // ✅ 컴포넌트에 data-testid="tier2-coupon-apply" 추가
page.getByRole('navigation', { name: '모바일 하단 메뉴' }) // ⚠️ 접근성 계약 자체가 검증 대상일 때만
page.getByText('9,000원')        // ⚠️ 문구 자체가 검증 대상일 때만 (금액·법적 고지)
```

### S-TAUTOLOGY (FAIL) · S-WEAK-ASSERT (WARN)

```ts
expect(true).toBe(true);         // ❌ 아무것도 증명하지 않는다
expect(result).toBeTruthy();     // ⚠️ 객체는 항상 truthy — 무엇인지 말하지 않는다
expect(result.total).toBe(9000); // ✅ 값
expect(result).toEqual({ total: 9000, applied: true }); // ✅ 모양
```

### S-NO-ASSERT (FAIL)

```ts
test('페이지에 들어간다', async ({ page }) => {
  await page.goto('/coupon');
  await page.getByTestId('tier2-coupon-apply').click();   // ❌ 클릭했다는 것만 안다
});
test('쿠폰 적용 버튼을 누르면 할인 합계가 보인다', async ({ page }) => {
  await page.goto('/coupon');
  await page.getByTestId('tier2-coupon-apply').click();
  await expect(page.getByTestId('tier2-coupon-total')).toHaveText('9,000원'); // ✅
});
```

### S-MOCK-ONLY (WARN — 게이트 증거 불인정)

```java
sut.apply(10000, "A");
then(couponReader).should().read("A");   // ⚠️ "불렀다"만 안다. 결과가 틀려도 통과한다
assertThat(sut.apply(10000, "A").total()).isEqualTo(9000); // ✅ 결과
```

우리 코드끼리 mock을 걸었다면 `*IntegrationTest`로 옮긴다.

### S-UNIT-USES-PAGE (FAIL)

`*.unit.spec.ts`가 `{ page }`를 쓰면 브라우저를 띄운다. 순수 로직 spec의 존재 이유(빠르고 안정)를 없앤다. `page`를 빼거나 브라우저 spec으로 옮긴다.

### S-SELF-REFERENCE (WARN)

```ts
expect(applyCoupon(10000, 'A').total).toBe(applyCoupon(10000, 'A').total); // ⚠️ 항상 통과
expect(applyCoupon(10000, 'A').total).toBe(9000); // ✅ 손계산: 10,000 × 0.9
```

### S-TITLE (WARN)

`test('coupon works')` → `test('10% 쿠폰을 적용하면 10,000원이 9,000원이 된다')`. 제목만 읽고 무엇이 깨졌는지 알 수 있어야 한다. 서버는 `@DisplayName("[단위] …")` — S-DISPLAY-NAME.

### S-CONTEXT-CACHE (WARN)

`@SpringBootTest`를 직접 붙인 새 클래스는 컨텍스트를 하나 더 만든다. `IntegrationTestSupport` 또는 `PersistenceTestSupport`를 상속한다.

### FAIL-PATH (WARN)

브라우저·API spec에 실패 경로가 없다. 제목에 `실패·오류·없·거절·만료·404·403·401·빈·차단·초과·권한` 같은 말이 없고 코드에 `status: 4xx`·`route.abort`·`status().isNotFound()`·`assertThatThrownBy`가 없으면 걸린다. skip된 테스트의 제목은 세지 않는다.

### PR-RECEIPT-* (FAIL / WARN)

PR 본문에 `🧪 테스트 영수증` 섹션이 없거나(FAIL), 적힌 테스트 파일이 레포에 없거나(FAIL), 뮤테이션 확인 줄이 비어 있다(WARN).

## 판정 범위 — 바뀐 줄만

diff 모드에서는 이 PR이 추가·수정한 줄(블록 규칙은 그 테스트 블록에 걸친 줄)에 있는 스멜만 판정에 들어간다. 손대지 않은 줄의 스멜은 "기존 부채" 개수로만 표시한다. 레포 전체를 훑고 싶으면 `--all-tests`를 쓴다.

## 사람이 봐야 하는 것 (스크립트 한계)

| 확인 | 질문 | 흔한 실패 |
|---|---|---|
| 제목이 동작인가 | 제목만 읽고 무엇이 깨졌는지 알겠는가 | "renders correctly", "정상 동작" |
| 기대값 출처 | 이 숫자·문구는 스펙·기획서·손계산에서 왔는가 | 구현을 돌려 나온 값을 그대로 붙여넣음 |
| 실패 경로가 진짜인가 | 실패 케이스가 실제 실패 UI/응답을 단언하는가 | 제목만 "오류"이고 본문은 성공 경로 복사 |
| mock 경계 | mock이 우리 밖(PG·S3·SES·LLM)인가 | 우리 서비스끼리 mock, `page.route`로 우리 lib 함수 대체 |
| 뮤테이션 증거 | 영수증에 "무엇을 망가뜨리니 어떤 테스트가 떨어졌다"가 있는가 | 비어 있거나 "테스트 추가했습니다" |
| 레포 간 계약 | 상태·이벤트명·DTO 필드가 바뀌었으면 상대 레포 테스트·PR 링크·배포 순서가 있는가 | 서버만 바꾸고 FE `orderStatus` 매핑 방치 |
| 격리 | 테스트 순서를 바꿔도 통과하는가, 공용 상태를 다른 테스트가 오염시키지 않는가 | `beforeAll` 시드 + 테스트 간 상태 공유 |
| 결제·금액·재고 | 실패·경합·멱등(같은 요청 2회) 케이스가 있는가 | happy path만 |
