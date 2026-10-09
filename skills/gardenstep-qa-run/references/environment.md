# 실행 환경(배포 SHA) 확인

실행기록의 `환경/FE·BE·Admin SHA`는 "어느 코드로 시험했는가"의 유일한 근거다. 이게 틀리면 FAIL을 고친 뒤
재시험해도 어느 버전에서 고쳐졌는지 알 수 없다.

## 지금 DEV에 떠 있는 SHA

DEV는 `dev` 브랜치 push마다 자동 배포된다. 배포가 실패하면 **직전 성공 버전이 그대로 떠 있다**. 그래서
"가장 최근 push"가 아니라 "가장 최근 **성공한** 배포"의 SHA를 쓴다.

```bash
for repo in gardenstep gardenstep-server gardenstep_admin; do
  sha=$(gh run list -R sramchorok-dev/$repo --branch dev --event push --workflow cicd.yml \
        --status success --limit 1 --json headSha,createdAt \
        --jq '.[0] | "\(.headSha[0:8]) (\(.createdAt))"')
  echo "$repo: ${sha:-확인 불가}"
done
```

- 결과 순서대로 FE, BE, Admin이다 → `--env "DEV FE <sha>, BE <sha>, Admin <sha>"`
- `gh` 권한이 없거나 결과가 비면 사용자에게 SHA를 묻는다. 그래도 모르면 `DEV 확인 불가(gh 권한 없음)`.
- 최근 성공 배포 시각이 시험 직전(수 분 이내)이면 배포가 끝났는지 한 번 더 확인한다. 배포 중에는 화면이
  섞여 보일 수 있다.

## 재시험할 때

이슈의 수정 PR이 DEV에 들어갔는지 먼저 본다. 수정 커밋이 위 SHA의 조상이 아니면 아직 반영 전이다.

```bash
git -C <레포> fetch origin dev -q
git -C <레포> merge-base --is-ancestor <수정 커밋> <DEV SHA> && echo 반영됨 || echo 아직 반영 전
```

반영 전이면 재시험하지 말고 "DEV 미반영"으로 보고한다.
