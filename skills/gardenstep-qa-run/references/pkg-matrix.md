# PKG-MATRIX 일괄 실행과 A-11 문구 검사

패키지 5종을 크기·벽 방향별로 한 번에 돌려 배치도 상태·견적·높낮이·안내 조건을 표로 만든다.
조합 목록의 정본은 QA 시트 `07 데이터세트`의 **PKG-MATRIX** 행이다(시트가 우선). 이 저장소의
`assets/pkg-matrix-example.csv`는 형식 예시일 뿐이다.

이 결과는 **API 수준**이다. 화면 문구·배치(라벨, 보는 쪽 표시, 금액 카드 순서, 상담 버튼)는 브라우저로 따로
본다. 표의 값만으로 화면 TC를 PASS로 적지 않는다.

## 1. 준비

1. 시트 `07` PKG-MATRIX 조합을 CSV로 저장한다. 머리줄:
   ```
   combo_id,sku,width_m,depth_m,wall,light,floor,climate_zone,conditions,flower_chips,seed,expect,source
   ```
   - `wall`: `BACK|LEFT|RIGHT|CORNER|NONE`
   - 빈 칸 기본값(설계 화면과 같음): `floor` SOIL, `seed` 20260825, `light`는 조건에 SHADE가 있으면 SHADE,
     C3이면 PARTIAL_SHADE, 나머지 SUN. `flower_chips` 빈 칸 = 색 미선택(전체 색).
   - `conditions`·`flower_chips`는 `|`로 구분. `climate_zone`(예: `6b`)은 DEV `GET /tier2/climate-regions`에서
     시험 지역의 값을 확인해 넣는다. 비우면 null로 보낸다.
   - `expect`·`source`는 그대로 결과에 복사된다(판정 메모·근거 문서).
2. (높이 밴드 검사) 시트 상품등록 탭에서 `productCode,band,heightCm`, 대표수종 탭에서 `package,rank,productCode`
   CSV를 뽑아 둔다. 없으면 `height_band_violations`는 `unchecked`로 나온다 — 0건이 아니다.
3. DEV 주소와 배포 SHA를 확인한다([environment.md](environment.md)). 주소는 이 저장소에 적지 않는다.

## 2. 실행

```bash
python3 <skill>/scripts/pkg_matrix.py --base-url <DEV API 주소> --combos pkg-matrix.csv \
  --out runs/<Run ID>-pkg-matrix.tsv [--catalog bands.csv --reps reps.csv] [--save-json runs/<Run ID>-json]
```

- 호출하는 것: `POST /tier2/layout/preview-jobs`(+ 진행 중이면 `GET …/{jobId}` 폴링), `POST /tier2/pricing/quote`.
  설계 화면이 주문 전에 부르는 공개 조회뿐이다. 장바구니·주문·결제·로그인은 하지 않는다.
- 운영으로 보이는 주소(호스트에 `dev`·`localhost`·`127.0.0.1`이 없음)는 멈춘다. 이름에 dev가 없는 DEV면
  `--allow-host <호스트>`로 명시한다.
- 한 번에 한 요청만 보낸다. 429가 오면 `Retry-After`만큼, 없으면 2·4·8…초(최대 60초) 기다려 다시 보낸다
  (`--max-retries`, 기본 5). 끝내 429면 그 조합은 `HTTP_429`로 남는다 — 병렬로 바꾸거나 다른 키로 우회하지 않는다.
- `--save-json`은 조합별 원본 응답(증거)이다. 공개 시트에 원본을 붙이지 않는다.

## 3. 결과 열

| 열 | 뜻 |
|---|---|
| `layout_job` | `SUCCEEDED` / `FAILED:<코드>` / `TIMEOUT`(90초) / `HTTP_<n>[:코드]` |
| `layout_status` | `READY` / `REVIEW_REQUIRED` / `UNAVAILABLE` |
| `quote` | `OK` / `HTTP_409:<코드>`(결제 막힘) / 그 밖 |
| `set_plan_amount` | 식물+바크(할인 반영) 줄 |
| `guide_amount` | 정원 조성 가이드 줄(`SERVICE`·`GARDEN_GUIDE_V1`) 또는 `guideAmount` |
| `option_amount`·`package_amount`·`total_amount` | 추가 옵션, 패키지 금액(가이드 포함), 결제 금액 |
| `shipping_amount`·`delivery_label` | 결제에 붙는 택배비, 배달비 안내 문구(별도 결제) |
| `species`·`plants`·`trees` | 품종 수, 큰나무 뺀 본수, 큰나무 수(이름) |
| `height_band_violations` | 대체·순위 자리 품목이 대표와 밴드가 다르고 키 차이 15cm 초과. `-` 없음, `unchecked` 확인 못 함 |
| `fill_count` | 나머지 자리 채우기(`FILL`) 품목 수 |
| `internal_text` | 응답 사유·진단·경고에 엔진 내부 문구가 있으면 그 문구 |
| `wide_notice` | 「공간이 넓어 같은 식물이 여러 번 반복돼요」 표시 조건(`shortageRepeat`) |
| `max_same_species_clusters`·`wide_rule_ok` | 같은 품종 최대 덩이 수, 「3덩이 이상일 때만 안내」와 맞는지 |
| `tree_issue` | 나무 원 겹침(`overlap`)·화단 밖(`outside`) |

## 4. TC로 옮기기

조합 결과 한 줄이 실행기록 한 행이 아니다. TC 카드의 합격 기준 항목마다 해당 조합을 근거로 `checks`를 쓴다.

| TC | 보는 열 |
|---|---|
| B-08·B-14 높낮이·밴드 대체 | `height_band_violations`(`unchecked`면 확인불가) |
| B-15 C2 나무수국은 군락만 | C2 조합의 `trees`에 나무수국이 없어야 한다 |
| B-16 깨지는 크기 → 상담 | `layout_status`≠READY 또는 `quote`=409이고 `internal_text`=`-`. 화면의 안내 한 줄·버튼은 브라우저로 |
| B-17 재고 0 → 대체 → 상담 | 대체 후 READY, 대체도 없으면 REVIEW_REQUIRED. DEV 재고는 바꾸지 않는다 — 격리 데이터가 없으면 BLOCKED |
| B-18·D-08·E-15 금액 | `set_plan_amount`+`guide_amount`+`option_amount`=`package_amount`, 패키지만이면 `shipping_amount` 0 |
| B-19 카탈로그 데이터 | 품종 구성(`--save-json`의 bom)과 시트 값 대조 |
| QA-72 넓은 공간 안내 | `wide_rule_ok` |

## 5. A-11 문구 검사

```bash
python3 <skill>/scripts/copy_policy.py --base-url <DEV FE 주소> --out runs/<Run ID>-a11.tsv
python3 <skill>/scripts/copy_policy.py --html-dir saved-dom/ --out runs/<Run ID>-a11.tsv   # 브라우저 DOM
```

- 금지 문구와 예외(약관·개인정보·푸터 사업자 정보·함께하는 곳)는 `assets/copy-policy.json`. 기준은 시트 A-11이
  정본이다 — 다르면 시트를 따르고 JSON을 고치자고 보고한다.
- 위반이 있으면 종료 코드 1. 줄마다 경로·문구·앞뒤 20자가 나온다.
- `LOW_TEXT` 페이지는 검사하지 못한 것이다(브라우저에서 그려지는 화면). 브라우저에서
  `document.documentElement.outerHTML`을 저장해(파일 이름: 경로의 `/`를 `_`로, 예 `_policy_returns.html`)
  `--html-dir`로 다시 돌린다. LOW_TEXT가 남은 채로 A-11을 PASS로 적지 않는다.
