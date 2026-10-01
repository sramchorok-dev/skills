---
date: 2026-10-02
branch: feat/team-plugin-v0.2
pr:
type: feat
risk: normal
rollback: revert
tests: [test_hooks.py, test_repository_tools.py]
adr: none
---

# 플러그인 v0.2 — [skip ci] 확인, 결정 로그·통계, 버전 검사, 업데이트 안내

## 무엇이 바뀌었나

- 커밋 메시지·PR 제목에 `[skip ci]`(및 `[ci skip]`·`[no ci]` 등)가 있으면 실행 전에 확인을 요청한다.
- hook 결정(확인·차단·알림·Stop 되돌림, 확인 후 실행)을 각자 컴퓨터의 `~/.claude/gardenstep-team/decisions.jsonl`에 규칙 ID·레포 이름·시각만 남긴다. `/hook-stats`로 규칙별 승인률과 조정 후보를 본다.
- PR CI가 플러그인 파일을 바꾸고 `version`을 올리지 않은 PR을 실패시킨다.
- 세션 시작 시 main에 새 버전이 있으면(하루 한 번, 2초 제한) 업데이트 명령을 안내한다.

## 왜

- 2026-09-30 FE #336·#337·#340이 `[skip ci]` 제목으로 머지돼 PR CI·이미지 빌드·DEV 배포가 한 번도 돌지 않았다(10/2 점검에서 발견, #337 이미지는 로컬 빌드로 별도 확인).
- 11월 "확인 창 빈도 측정·조정" 계획에 필요한 데이터가 쌓이지 않고 있었다.
- 자동 업데이트가 기본 꺼짐이라 팀원이 v0.1.0에 머물고, version을 안 올리면 변경이 아예 전달되지 않는다.
- JD 승인(2026-10-02): 위 개선을 skills 저장소에서 진행.

## 확인한 것

- `python3 -m unittest discover -s tests` 46개 통과, `validate_skills.py`, `claude plugin validate .`, `check_plugin_version.py --base origin/main` 통과.
- 결함 감지: 로그 호출 제거, skip-ci 정규식 훼손, 로그 키 추가, 버전 비교 완화, 업데이트 안내 비활성, 조정 후보 기준 훼손을 각각 넣으면 해당 테스트가 실패.
- E2E: `claude -p --plugin-dir`로 `[skip ci]` 커밋 → 확인 요청, 로그에 `skip-ci`만 기록, 커밋 미생성.
