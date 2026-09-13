---
name: gardenstep-report-wiki
description: Gardenstep/Chorok HTML 보고서를 공개 DEV Report Wiki에 검증·등록·배포한다. 사용자가 "보고서 올려", "HTML wiki에 등록", "remote에 공개", "누구나 볼 수 있게", "리포트 위키 게시"처럼 Gardenstep 보고서의 공개 업로드나 링크 생성을 요청할 때 사용한다. 제목·설명·날짜 자동 추출, 공개 안전 검사, S3 registry 병합, CloudFront 갱신, 공개 URL 확인까지 수행한다.
compatibility: Python 3.10+, AWS CLI, gardenstep-dev AWS profile
---

# Gardenstep Report Wiki 게시

완성된 HTML 보고서 한 개를 `https://cdn-dev.gardenstep.ai/report-wiki/index.html`에 게시한다. 제목·설명·날짜는 HTML과 파일 수정 시각에서 자동 추출하므로 Agent가 최소 인자로 실행할 수 있다.

## 게시 계약

- 공개 범위: `chorok` HTML 보고서만
- 공개 열람: 로그인 없음
- 쓰기 권한: AWS profile `gardenstep-dev`
- 저장소: `s3://gardenstep-dev/report-wiki/`
- 목록 갱신: S3 ETag 조건부 병합, 충돌 시 최대 3회 재시도
- 완료 조건: CloudFront invalidation 완료, index·registry·report 공개 readback

## 실행

`SKILL_DIR`은 이 `SKILL.md`가 있는 디렉터리다.

공개 의도가 현재 대화에 명시된 경우 다음 명령으로 바로 게시한다. “공개”, “remote”, “누구나 볼 수 있게”, “위키에 올려”는 게시 승인으로 본다.

```bash
python3 "$SKILL_DIR/scripts/publish_report.py" "/absolute/path/report.html" \
  --tags "챗봇,구매" \
  --ack-public \
  --deploy \
  --json
```

공개 의도가 없는 단순 준비·검사 요청에는 `--deploy`를 빼고 실행한다. 이 모드는 원격 상태를 바꾸지 않는다.

```bash
python3 "$SKILL_DIR/scripts/publish_report.py" "/absolute/path/report.html" \
  --tags "아키텍처" \
  --ack-public \
  --json
```

HTML에 적절한 `<title>`이나 `<meta name="description">`이 없으면 `--title`, `--desc`, `--date YYYY-MM-DD`를 보완한다.

## 공개 전 검사

1. HTML 완성본과 실제 화면 확인
2. 개인정보·고객 사진·상담 원문·내부 전용 계약·가격·취약점 제외
3. API key·password·private key·환경 변수 값 제외
4. 외부 공개 가능한 이미지·링크만 포함
5. 스크립트의 비밀값 검사 통과

`--ack-public`은 위 검사를 수행했다는 Agent의 확인이다. 사용자가 이미 공개 게시를 요청했다면 같은 승인을 다시 묻지 않는다.

## 결과 확인

명령의 JSON receipt에서 `status=published`, `wiki_url`, `report_url`을 확인한다. 가능하면 실제 브라우저에서 다음 항목을 추가 확인한다.

- index 카드 노출과 검색
- report 직접 링크 HTTP 200
- 모바일 가로 overflow 없음
- console·page error 없음
- 이미지 decode 실패 없음

최종 응답에는 Wiki 주소, 직접 보고서 주소, 검사·브라우저·readback 결과를 포함한다.

## 실패 처리

- AWS 계정 불일치: 게시 중단, 현재 profile 확인
- 비밀값 탐지: 원본 수정 전 게시 중단, 탐지 항목만 보고
- registry 412 반복: 다른 게시 완료 후 같은 명령 재실행
- invalidation/readback 실패: 완료 판정 금지, S3 object와 CloudFront 상태 확인
- 삭제·대량 교체: 별도 사용자 지시 전 실행 금지
