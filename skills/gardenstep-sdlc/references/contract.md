# 증거 v1 · 저장소 v2 계약과 신뢰 경계

manifest/policy/evidence/source-evidence는 `schema_version: 1`, repository는 `schema_version: 2`다. 정본 스키마는 이 스킬의 `schemas/`에 있다. JSON 중복 key·알 수 없는 필드·공백값·잘못된 UTC 시각을 거부한다.

- manifest: 문서 SHA256, 서비스 git SHA40, 하네스 버전, 작성 세션, 요구사항↔출처↔필수검사 매핑.
- policy: 사람이 승인한 기준으로 고정한 manifest SHA256와 필수 검사/출처 목록, DEV 필요 여부.
- evidence: 정확한 manifest와 서비스 조합, 검사별 명령·시각·실행기·도구·모델/프롬프트/judge 버전, 원시 결과 식별자와 hash, 성공/실패/skip/cancel 건수.
- source-evidence: connector 설치·인증·실제 읽기의 별도 관측. doctor는 인증을 수행하지 않으며 개인 자격 파일도 읽지 않는다.
- repository: 서비스의 명령·미검증 항목·공용 패키지 고정 SHA. 정적 구조 검사는 명령을 실행하지 않는다.

manifest hash는 `json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)`의 UTF-8 SHA256이다. `sdlc.py hash manifest.json`으로 구한다.
새 필드·의미 변경은 schema_version을 올린다. 기존 v1을 조용히 재해석하지 않는다.

## 입력 판정과 인증은 다르다

`validate_bundle(manifest, evidence, policy)`는 `{status, authority:"local-validation-only", errors, ...}`를 반환한다.
파일을 제공한 사람이 모든 값을 위조할 수 있으므로 이것은 승인·서명 검증기가 아니다.
GitHub Issue/PR의 사람 승인과 원래 검사 목록, 실제 workflow run/SHA, 내려받은 artifact bytes/hash, 필요한 runtime 결과를 대조한다.
manifest에 임의로 적은 모델명·세션 ID는 실행 provenance가 아니다. 실제 실행 기록과 대조한다.
별도 control 서버나 passkey는 도입하지 않는다. 무보호 branch의 관리자 직접 쓰기까지 막는다는 보장은 없고, 이 한계는 선택한 GitHub 기록·CI·수동 승인 모델의 범위다.

필수 목록은 정확히 일치해야 한다. 빈 실행·exit0+실패·skip/cancel·모든 비PASS·unknown check·같은 작성/리뷰 세션·DEV 버전 변경을 차단한다.
비LLM 검사는 model.name=deterministic, version=실제 검사기 버전, prompt_version=not-applicable로 남긴다. eval/review의 모델·프롬프트는 실제 고정 버전을 적는다.
judge가 결정적이면 judge_name=deterministic와 실제 judge_version을 적는다. 버전 불명은 실제 증거가 아니다.

## doctor 수집 계약

source-evidence의 account_ref는 내부 비식별 식별자다. 계정 이메일·토큰·쿠키를 넣지 않는다.
읽기 PASS는 revision(없으면 observation hash 기반 ID), observed_at(UTC), content_sha256, 접근 제한 artifact_uri와 complete=true, missing_parts=[]가 필요하다.
본문·첨부·하위문서·pagination 일부만 읽었으면 missing_parts에 남긴다. 부재/NOT_RUN을 완료로 계산하지 않는다.
설치가 됐다는 것과 인증에 성공한 것, 실제 지정 원자료를 읽은 것은 별개다. 만료와 허용 scope는 각자의 실제 커넥터/브라우저 읽기로 확인한다.

이 패키지의 샘플은 합성 데이터다. 고객 원문·개인 DM·실제 검증 artifact는 이 public 저장소에 넣지 않는다.
