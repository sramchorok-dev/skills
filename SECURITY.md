# Security

이 저장소는 공개 저장소다. API key, AWS credential, 고객 데이터, 개인정보, 내부 전용 문서를 Issue·Pull Request·커밋에 포함하지 않는다.

보안 문제는 공개 Issue 대신 [GitHub private vulnerability report](https://github.com/sramchorok-dev/skills/security/advisories/new)로 전달한다.

외부 시스템에 쓰는 bundled script는 대상 계정과 환경을 확인하고, dry-run 또는 검증 모드와 실제 변경 모드를 분리해야 한다.
