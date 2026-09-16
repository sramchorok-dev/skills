#!/usr/bin/env python3
"""Gardenstep 테스트 정책 점검기.

PR diff를 읽어 (1) 변경 파일을 분류하고 (2) 변경 유형별 필수 테스트가 함께 왔는지 확인하고
(3) 변경된 테스트 파일에서 바이브코딩 스멜을 찾고 (4) PR 본문의 테스트 영수증을 검사한다.

표준 라이브러리만 사용한다. 정책 정본: ../references/testing-policy.md

사용 예:
  python3 audit_tests.py --repo ../gardenstep --base origin/dev
  python3 audit_tests.py --repo ../gardenstep-server --base origin/dev --pr-body body.md --json
  python3 audit_tests.py --repo . --changed-files changed.txt   # CI/테스트용: git 없이 목록 제공
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

FAIL = "FAIL"
WARN = "WARN"
PASS = "PASS"

# ---------------------------------------------------------------------------
# 레포 종류 · 파일 분류
# ---------------------------------------------------------------------------


def detect_repo_kind(root: Path) -> str:
    if (root / "build.gradle").is_file() or (root / "build.gradle.kts").is_file():
        return "server"
    package = root / "package.json"
    if package.is_file():
        try:
            name = json.loads(package.read_text(encoding="utf-8")).get("name", "")
        except (OSError, json.JSONDecodeError):
            name = ""
        if "admin" in name:
            return "admin"
        return "fe"
    return "unknown"


_DOC_RE = re.compile(r"(^|/)(docs/|[^/]+\.md$|LICENSE$)")
_CI_RE = re.compile(r"^\.github/")


def classify_file(kind: str, path: str) -> str:
    path = path.replace("\\", "/")
    if _CI_RE.match(path):
        return "ci"
    if _DOC_RE.search(path):
        return "docs"
    if kind in ("fe", "admin"):
        return _classify_ts(kind, path)
    if kind == "server":
        return _classify_java(path)
    return "other"


def _classify_ts(kind: str, path: str) -> str:
    if path.startswith("tests/e2e/") or path.startswith("tests/"):
        if path.endswith(".unit.spec.ts"):
            return "test-unit"
        if path.endswith(".spec.ts"):
            return "test-browser"
        return "test-helper"
    if re.search(r"\.test\.tsx?$", path):
        return "test-unit"
    if path.startswith(("app/", "containers/", "components/", "hooks/", "atoms/", "store/")):
        return "source-ui"
    if path.startswith(("lib/", "utils/", "api/", "constants/", "actions/", "types/")):
        return "source-logic"
    if path.endswith((".tsx",)):
        return "source-ui"
    if path.endswith((".ts",)) and not path.endswith(".d.ts") and "/" in path:
        return "source-logic"
    if path.endswith((".yml", ".yaml", ".json", ".mjs", ".cjs", ".js", ".env", ".example")) or path in (
        "Dockerfile",
        "tsconfig.json",
    ):
        return "config" if not path.endswith("package-lock.json") else "other"
    return "other"


def _classify_java(path: str) -> str:
    if path.startswith("src/test/resources/"):
        return "test-fixture"
    if path.startswith("src/test/"):
        name = path.rsplit("/", 1)[-1]
        if "/architecture/" in path or name.endswith("ContractTest.java") or name.endswith("ArchitectureTest.java"):
            return "test-contract"
        if name.endswith(("ControllerTest.java", "ApiTest.java", "SecurityTest.java")) or "/presentation/" in path:
            return "test-api"
        if name.endswith(("IntegrationTest.java", "E2eTest.java")):
            return "test-integration"
        if name.endswith(("Test.java", "Tests.java")):
            return "test-unit"
        return "test-helper"
    if path.startswith("src/main/resources/db/changelog/"):
        return "schema"
    if path.startswith("src/main/resources/") or path in ("build.gradle", "build.gradle.kts", "settings.gradle", "Dockerfile") or path.startswith(
        ("nginx/", "gradle/", "docker-compose")
    ):
        return "config"
    if path.startswith("src/main/java/"):
        name = path.rsplit("/", 1)[-1]
        if "/presentation/" in path or name.endswith("Controller.java"):
            return "source-api"
        return "source-domain"
    return "other"


# ---------------------------------------------------------------------------
# 변경 파일 수집
# ---------------------------------------------------------------------------


def changed_files(root: Path, base: str, head: str = "HEAD") -> list[str]:
    """`git diff --name-status base...head`에서 삭제를 뺀 'STATUS path' 목록."""
    result = subprocess.run(
        ["git", "diff", "--name-status", "--no-renames", f"{base}...{head}"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    entries: list[str] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        status, _, path = line.partition("\t")
        status = status.strip()[:1]
        if status == "D":
            continue
        entries.append(f"{status} {path.strip()}")
    return entries


def parse_changed(entries: list[str]) -> list[tuple[str, str]]:
    parsed: list[tuple[str, str]] = []
    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue
        parts = entry.split(None, 1)
        if len(parts) == 2 and len(parts[0]) == 1 and parts[0].isupper():
            parsed.append((parts[0], parts[1]))
        else:
            parsed.append(("M", entry))
    return parsed


# ---------------------------------------------------------------------------
# 필수 테스트 규칙
# ---------------------------------------------------------------------------

_FAILURE_WORDS = (
    "실패", "오류", "에러", "없으", "없다", "없는", "거절", "거부", "만료", "404", "403", "401", "400", "409",
    "빈 ", "비어", "차단", "불가", "초과", "제한", "취소", "잘못", "유효하지", "권한", "비로그인", "미로그인",
    "error", "fail", "invalid", "empty", "reject", "denied", "forbidden", "unauthorized", "not found", "expired",
    "timeout", "타임아웃", "재시도", "중복",
)
_TS_FAILURE_CODE = re.compile(r"status:\s*(4\d\d|5\d\d)|toHaveURL\([^)]*404|route\.abort\(|\.rejects\.|toThrow")
_JAVA_FAILURE_CODE = re.compile(
    r"status\(\)\.is(4xx|5xx|BadRequest|Forbidden|Unauthorized|NotFound|Conflict|UnprocessableEntity)|"
    r"assertThatThrownBy|assertThrows|isInstanceOf\(\w*Exception|expectError"
)
# skip/fixme 된 테스트의 제목은 실패 경로 증거로 세지 않는다
_TS_TITLE_RE = re.compile(r"\b(?:test|it)(?:\.(?!skip|fixme)\w+)?\(\s*(['\"`])((?:\\.|(?!\1).)*)\1", re.S)
_JAVA_DISPLAY_RE = re.compile(r'@DisplayName\(\s*"((?:\\.|[^"\\])*)"\s*\)')


def _has_failure_path(kind: str, text: str) -> bool:
    titles = [m.group(2) for m in _TS_TITLE_RE.finditer(text)] if kind != "server" else [
        m.group(1) for m in _JAVA_DISPLAY_RE.finditer(text)
    ]
    for title in titles:
        low = title.lower()
        if any(word in low for word in _FAILURE_WORDS):
            return True
    code_re = _JAVA_FAILURE_CODE if kind == "server" else _TS_FAILURE_CODE
    return bool(code_re.search(text))


def _rule(rule_id: str, title: str, level: str, satisfied: bool, evidence: list[str], fix: str) -> dict:
    return {
        "id": rule_id,
        "title": title,
        "level": level,
        "satisfied": satisfied,
        "evidence": evidence,
        "fix": "" if satisfied else fix,
    }


def required_rules(kind: str, root: Path, changed: list[tuple[str, str]]) -> list[dict]:
    by_cat: dict[str, list[str]] = {}
    added: set[str] = set()
    for status, path in changed:
        by_cat.setdefault(classify_file(kind, path), []).append(path)
        if status == "A":
            added.add(path)
    rules: list[dict] = []
    ui = by_cat.get("source-ui", [])
    logic = by_cat.get("source-logic", [])
    browser = by_cat.get("test-browser", [])
    unit = by_cat.get("test-unit", [])

    if kind in ("fe", "admin"):
        prefix = "FE" if kind == "fe" else "ADMIN"
        if ui:
            rules.append(
                _rule(
                    f"{prefix}-E2E",
                    "화면·컴포넌트 동작이 바뀌면 브라우저 spec이 함께 바뀐다",
                    FAIL,
                    bool(browser),
                    browser or ui,
                    "tests/e2e/<화면>.spec.ts에 도달·핵심 인터랙션·실패 경로를 추가한다",
                )
            )
        if logic:
            rules.append(
                _rule(
                    f"{prefix}-UNIT",
                    "순수 로직(lib/utils/api)이 바뀌면 순수 로직 테스트가 함께 바뀐다",
                    FAIL,
                    bool(unit),
                    unit or logic,
                    "FE는 tests/e2e/<대상>.unit.spec.ts, Admin은 lib/<대상>.test.ts에 기대값을 스펙에서 가져와 단언한다",
                )
            )
        if kind == "fe":
            new_pages = [p for p in added if re.match(r"app/.*/page\.tsx$", p)]
            if new_pages:
                flag_off_touched = any(p.endswith("tier2-flag-off.spec.ts") for _, p in changed)
                rules.append(
                    _rule(
                        "FE-FLAG-OFF",
                        "새 라우트는 flag OFF 404 케이스를 tier2-flag-off.spec.ts에 추가한다",
                        WARN,
                        flag_off_touched,
                        new_pages,
                        "플래그 뒤 라우트면 tests/e2e/tier2-flag-off.spec.ts에 경로를 추가하고, 아니면 PR 본문에 사유를 적는다",
                    )
                )
        if kind == "admin" and ui and browser:
            auth_covered = any(
                re.search(r"비로그인|권한|403|401|login|unauthor|forbidden", _read(root / p), re.I) for p in browser
            )
            rules.append(
                _rule(
                    "ADMIN-AUTH",
                    "운영자 화면 spec은 비로그인·권한 없음 경로를 포함한다",
                    WARN,
                    auth_covered,
                    browser,
                    "spec에 비로그인 리다이렉트 또는 403 응답 케이스를 추가한다",
                )
            )
        journey_specs = browser
    else:  # server
        api = by_cat.get("source-api", [])
        domain = by_cat.get("source-domain", [])
        schema = by_cat.get("schema", [])
        api_tests = by_cat.get("test-api", [])
        integration = by_cat.get("test-integration", [])
        unit_tests = by_cat.get("test-unit", [])
        contract = by_cat.get("test-contract", [])
        mockmvc_tests = [p for p in api_tests + integration + unit_tests if "MockMvc" in _read(root / p)]
        if api:
            rules.append(
                _rule(
                    "SRV-API",
                    "API(컨트롤러·DTO)가 바뀌면 MockMvc API 테스트가 함께 바뀐다",
                    FAIL,
                    bool(api_tests or mockmvc_tests),
                    api_tests or mockmvc_tests or api,
                    "src/test/.../presentation/<Name>ControllerTest.java에 정상 응답 1개와 4xx 1개를 MockMvc로 단언한다",
                )
            )
        if domain:
            rules.append(
                _rule(
                    "SRV-DOMAIN",
                    "도메인·서비스가 바뀌면 테스트가 함께 바뀐다",
                    FAIL,
                    bool(api_tests or integration or unit_tests or contract),
                    api_tests + integration + unit_tests + contract or domain,
                    "계산은 mock 없는 [단위], 영속·트랜잭션은 *IntegrationTest(PersistenceTestSupport 상속)로 단언한다",
                )
            )
        if schema:
            rules.append(
                _rule(
                    "SRV-SCHEMA",
                    "Liquibase 변경은 통합 테스트로 스키마 검증을 남긴다",
                    WARN,
                    bool(integration) or any("Migration" in p for p in unit_tests),
                    integration or schema,
                    "*IntegrationTest 또는 src/test/resources/db/changelog/*-migration-test.yaml을 추가한다",
                )
            )
        journey_specs = api_tests + integration

    if journey_specs:
        missing = [p for p in journey_specs if not _has_failure_path(kind, _read(root / p))]
        rules.append(
            _rule(
                "FAIL-PATH",
                "사용자 경로 테스트는 실패·거절 경로를 최소 1개 포함한다",
                WARN,
                not missing,
                missing or journey_specs,
                "4xx 응답·빈 상태·권한 없음·만료 같은 실패 케이스를 제목에 드러나게 추가한다",
            )
        )
    return rules


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


# ---------------------------------------------------------------------------
# 스멜 스캔
# ---------------------------------------------------------------------------


def _smell(path: str, line: int, rule: str, level: str, snippet: str, fix: str) -> dict:
    return {"file": path, "line": line, "rule": rule, "level": level, "snippet": snippet.strip()[:120], "fix": fix}


_TS_LINE_RULES: list[tuple[re.Pattern[str], str, str, str]] = [
    (re.compile(r"\b(?:test|it|describe)\.only\("), "S-ONLY", FAIL, ".only을 지운다 — CI forbidOnly와 별개로 PR에서 금지"),
    (re.compile(r"\btest\.fixme\("), "S-FIXME", FAIL, "fixme 대신 고치거나, 이슈 번호와 사유를 단 조건부 skip으로 바꾼다"),
    (re.compile(r"waitForTimeout\(|\bsleep\("), "S-HARD-WAIT", FAIL, "expect(locator).toBeVisible()/toHaveText() 자동 대기로 바꾼다"),
    (re.compile(r"setTimeout\("), "S-HARD-WAIT", WARN, "테스트 안 타이머는 플레이크 원인 — 관찰 가능한 상태를 기다린다"),
    (re.compile(r"\.locator\(\s*['\"`](?:\.|#|xpath=|css=|//)"), "S-SELECTOR", FAIL, "data-testid를 추가하고 getByTestId로 바꾼다"),
    (re.compile(r"\.getBy(?:Text|Role|Label|Placeholder|Title)\("), "S-SELECTOR-EXCEPTION", WARN, "문구·접근성 자체가 검증 대상일 때만 허용 — 아니면 data-testid"),
    (re.compile(r"expect\(\s*(?:true|false|1|0|'[^']*'|\"[^\"]*\")\s*\)\.(?:toBe|toEqual|toBeTruthy|toBeFalsy)"), "S-TAUTOLOGY", FAIL, "구현 결과를 단언한다 — 상수끼리 비교는 아무것도 증명하지 않는다"),
    (re.compile(r"\.(?:toBeTruthy|toBeDefined|toBeFalsy|toBeUndefined)\(\)"), "S-WEAK-ASSERT", WARN, "값이 무엇인지 단언한다 (toBe/toEqual/toHaveText)"),
    (re.compile(r"\bconsole\.log\("), "S-DEBUG-LOG", WARN, "디버그 출력을 지운다"),
    (re.compile(r"expect\(\s*(\w+)\(([^()]*)\)(?:\.\w+)*\)\.(?:toBe|toEqual)\(\s*\1\("), "S-SELF-REFERENCE", WARN, "기대값은 스펙·손계산에서 가져온다 — 같은 함수를 두 번 부르면 항상 통과한다"),
]

_TS_SKIP_RE = re.compile(r"\b(?:test|it|describe)\.skip\(\s*([^,\n]*)(,|\))")
_TS_TEST_START_RE = re.compile(r"^\s*(?:test|it)(?:\.(?:only|skip|fixme))?\(\s*(['\"`])((?:\\.|(?!\1).)*)\1", re.M)
_TS_ASSERT_RE = re.compile(r"\bexpect\(|\bassert\.|\bassert\(|expectTypeOf\(|toMatchSnapshot")
_KOREAN_RE = re.compile(r"[가-힣]")


def _block_end(text: str, start: int, open_idx: int | None = None) -> int:
    """open_idx(기본: start 이후 첫 '{')부터 짝이 맞는 '}'까지의 끝 인덱스(없으면 len)."""
    if open_idx is None:
        open_idx = text.find("{", start)
    if open_idx < 0:
        return len(text)
    depth = 0
    i = open_idx
    in_str: str | None = None
    while i < len(text):
        ch = text[i]
        if in_str:
            if ch == "\\":
                i += 2
                continue
            if ch == in_str:
                in_str = None
        elif ch in ("'", '"', "`"):
            in_str = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return len(text)


_TS_CALLBACK_RE = re.compile(r"=>\s*(\{)?|function\s*\([^)]*\)\s*(\{)")


def _ts_callback_body(text: str, start: int) -> str:
    """test('제목', <콜백>) 의 콜백 본문. 파라미터 구조분해 `({ page })`의 중괄호를 건너뛴다."""
    match = _TS_CALLBACK_RE.search(text, start)
    if not match:
        return ""
    open_idx = match.start(1) if match.group(1) else (match.start(2) if match.group(2) else -1)
    if open_idx < 0:
        # 식 본문 화살표 함수: `=> expect(x).toBe(1)` — 줄 끝까지
        end = text.find("\n", match.end())
        return text[match.end(): end if end >= 0 else len(text)]
    return text[open_idx: _block_end(text, open_idx, open_idx)]


def _scan_ts(kind: str, path: str, text: str) -> list[dict]:
    smells: list[dict] = []
    lines = text.splitlines()
    for number, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("*"):
            continue
        for pattern, rule, level, fix in _TS_LINE_RULES:
            if pattern.search(line):
                smells.append(_smell(path, number, rule, level, line, fix))
        for match in _TS_SKIP_RE.finditer(line):
            first, closer = match.group(1).strip(), match.group(2)
            is_condition = not first.startswith(("'", '"', "`")) and first != ""
            has_reason = closer == "," and ("'" in line[match.end():] or '"' in line[match.end():])
            if not (is_condition and has_reason):
                smells.append(_smell(path, number, "S-SKIP", FAIL, line, "skip은 `test.skip(조건, '이슈번호 + 사유')` 환경 가드만 허용 — 그 외는 지우거나 고친다"))
    if path.endswith(".unit.spec.ts") and re.search(r"\{\s*page\s*[,}]|\bpage\.", text):
        line_no = next((i for i, l in enumerate(lines, 1) if re.search(r"\{\s*page\s*[,}]|\bpage\.", l)), 1)
        smells.append(_smell(path, line_no, "S-UNIT-USES-PAGE", FAIL, lines[line_no - 1], "unit.spec은 브라우저를 쓰지 않는다 — page 픽스처를 빼거나 브라우저 spec으로 옮긴다"))
    for match in _TS_TEST_START_RE.finditer(text):
        title = match.group(2)
        line_no = text.count("\n", 0, match.start()) + 1
        body = _ts_callback_body(text, match.end())
        if not _TS_ASSERT_RE.search(body):
            smells.append(_smell(path, line_no, "S-NO-ASSERT", FAIL, match.group(0), "expect로 기대 결과를 단언한다 — 단언 없는 테스트는 통과해도 의미가 없다"))
        if not _KOREAN_RE.search(title) and len(title) < 24:
            smells.append(_smell(path, line_no, "S-TITLE", WARN, match.group(0), "제목을 '조건이면 기대 결과다' 한국어 문장으로 쓴다"))
    return smells


_JAVA_LINE_RULES: list[tuple[re.Pattern[str], str, str, str]] = [
    (re.compile(r"Thread\.sleep\(|TimeUnit\.\w+\.sleep\("), "S-HARD-WAIT", FAIL, "Awaitility·CountDownLatch·StepVerifier로 관찰 가능한 완료를 기다린다"),
    (re.compile(r"assert(?:True|That)\(\s*true\s*\)|assertFalse\(\s*false\s*\)|assertEquals\(\s*(\d+|\"[^\"]*\")\s*,\s*\1\s*\)"), "S-TAUTOLOGY", FAIL, "구현 결과를 단언한다 — 상수끼리 비교는 아무것도 증명하지 않는다"),
    (re.compile(r"System\.out\.print"), "S-DEBUG-LOG", WARN, "디버그 출력을 지운다"),
]
_JAVA_DISABLED_RE = re.compile(r"@Disabled(\(\s*\"[^\"]*\"\s*\))?")
_JAVA_TEST_RE = re.compile(r"@(?:Test|ParameterizedTest|RepeatedTest)\b")
_JAVA_METHOD_RE = re.compile(r"\b(?:void|\w+)\s+(\w+)\s*\([^)]*\)\s*(?:throws [\w., ]+)?\s*\{")
_JAVA_ASSERT_RE = re.compile(r"assertThat|assertEquals|assertTrue|assertFalse|assertNull|assertNotNull|assertThrows|assertThatThrownBy|assertAll|andExpect\(|StepVerifier|assertIterableEquals|assertArrayEquals|assertDoesNotThrow|fail\(")
_JAVA_MOCK_ONLY_RE = re.compile(r"\bthen\(|\bverify\(|verifyNoInteractions|verifyNoMoreInteractions")


def _scan_java(path: str, text: str) -> list[dict]:
    smells: list[dict] = []
    lines = text.splitlines()
    for number, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith(("//", "*", "/*")):
            continue
        for pattern, rule, level, fix in _JAVA_LINE_RULES:
            if pattern.search(line):
                smells.append(_smell(path, number, rule, level, line, fix))
        for match in _JAVA_DISABLED_RE.finditer(line):
            if match.group(1):
                smells.append(_smell(path, number, "S-DISABLED", WARN, line, "이슈가 닫히면 @Disabled를 제거한다"))
            else:
                smells.append(_smell(path, number, "S-DISABLED", FAIL, line, '@Disabled("이슈번호 + 사유")로 사유를 남기거나 테스트를 고친다'))
    if "@SpringBootTest" in text and not re.search(r"extends\s+\w*(?:IntegrationTestSupport|PersistenceTestSupport)", text):
        line_no = next((i for i, l in enumerate(lines, 1) if "@SpringBootTest" in l), 1)
        smells.append(_smell(path, line_no, "S-CONTEXT-CACHE", WARN, lines[line_no - 1], "IntegrationTestSupport/PersistenceTestSupport를 상속해 컨텍스트 캐시를 공유한다 — 새 컨텍스트는 suite 시간을 늘린다"))
    for match in _JAVA_TEST_RE.finditer(text):
        window_start = match.end()
        method = _JAVA_METHOD_RE.search(text, window_start)
        if not method:
            continue
        annotations = text[match.start(): method.start()]
        line_no = text.count("\n", 0, method.start()) + 1
        body = text[method.end() - 1: _block_end(text, method.end() - 1)]
        has_assert = bool(_JAVA_ASSERT_RE.search(body))
        has_mock = bool(_JAVA_MOCK_ONLY_RE.search(body))
        if not has_assert and not has_mock:
            smells.append(_smell(path, line_no, "S-NO-ASSERT", FAIL, method.group(0), "assertThat으로 결과를 단언한다"))
        elif not has_assert and has_mock:
            smells.append(_smell(path, line_no, "S-MOCK-ONLY", WARN, method.group(0), "mock 호출 검증만 있는 테스트는 게이트 증거로 인정하지 않는다 — 결과 값을 단언하거나 통합 테스트로 보강한다"))
        if "@DisplayName" not in annotations:
            smells.append(_smell(path, line_no, "S-DISPLAY-NAME", WARN, method.group(0), '@DisplayName("[단위|통합|API] 조건이면 기대 결과다")를 붙인다'))
    return smells


def scan_smells(kind: str, root: Path, test_files: list[str]) -> list[dict]:
    smells: list[dict] = []
    for rel in test_files:
        text = _read(root / rel)
        if not text:
            continue
        if kind == "server":
            if rel.endswith(".java"):
                smells.extend(_scan_java(rel, text))
        elif rel.endswith((".ts", ".tsx", ".js", ".mjs")):
            smells.extend(_scan_ts(kind, rel, text))
    smells.sort(key=lambda s: (s["file"], s["line"], s["rule"]))
    return smells


# ---------------------------------------------------------------------------
# PR 본문 영수증
# ---------------------------------------------------------------------------

_RECEIPT_HEADING_RE = re.compile(r"테스트\s*영수증")
_RECEIPT_SPAN_RE = re.compile(r"`([^`\n]+)`")
_RECEIPT_TOKEN_RE = re.compile(r"(?<![\w/])([\w./()\[\]-]+\.(?:spec\.ts|test\.tsx?|java))\b")
_MUTATION_LINE_RE = re.compile(r"^\s*[-*]\s*뮤테이션[^:：]*[:：]\s*(\S.*)?$", re.M)
_EXEMPT_LINE_RE = re.compile(r"^\s*[-*]\s*면제[^:：]*[:：]\s*(\S.*)?$", re.M)


def check_pr_body(body: str, root: Path) -> list[dict]:
    findings: list[dict] = []
    if not _RECEIPT_HEADING_RE.search(body):
        findings.append({"rule": "PR-RECEIPT-MISSING", "level": FAIL, "message": "PR 본문에 '🧪 테스트 영수증' 섹션이 없다 — assets/pr-test-receipt.md 양식을 채운다"})
        return findings
    seen: set[str] = set()
    for span in _RECEIPT_SPAN_RE.finditer(body):
        for token in _RECEIPT_TOKEN_RE.finditer(span.group(1)):
            rel = token.group(1)
            if "*" in rel or rel in seen:
                continue
            seen.add(rel)
            if not (root / rel).is_file():
                findings.append({"rule": "PR-RECEIPT-PATH", "level": FAIL, "message": f"영수증에 적힌 테스트 파일이 레포에 없다: {rel}"})
    exempt = _EXEMPT_LINE_RE.search(body)
    exempt_reason = (exempt.group(1) or "").strip() if exempt else ""
    mutation = _MUTATION_LINE_RE.search(body)
    mutation_text = (mutation.group(1) or "").strip() if mutation else ""
    if not mutation_text and not (exempt_reason and exempt_reason != "없음"):
        findings.append({"rule": "PR-MUTATION-MISSING", "level": WARN, "message": "뮤테이션 확인 줄이 비어 있다 — 구현 한 곳을 일부러 망가뜨려 어떤 테스트가 떨어졌는지 한 줄 적는다"})
    return findings


# ---------------------------------------------------------------------------
# 종합
# ---------------------------------------------------------------------------


def audit(
    root: Path,
    base: str | None = None,
    head: str = "HEAD",
    changed: list[str] | None = None,
    pr_body: str | None = None,
    exempt: str | None = None,
    kind: str | None = None,
) -> dict:
    root = Path(root).resolve()
    kind = kind or detect_repo_kind(root)
    if changed is None:
        if base is None:
            raise ValueError("base 또는 changed 중 하나는 필요하다")
        changed = changed_files(root, base, head)
    parsed = parse_changed(changed)
    classified: dict[str, list[str]] = {}
    for status, path in parsed:
        classified.setdefault(classify_file(kind, path), []).append(f"{status} {path}")
    test_files = [
        path for _, path in parsed if classify_file(kind, path).startswith("test-") and classify_file(kind, path) != "test-fixture"
    ]
    rules = required_rules(kind, root, parsed)
    smells = scan_smells(kind, root, test_files)
    pr_findings = check_pr_body(pr_body, root) if pr_body is not None else []
    if exempt:
        for rule in rules:
            if not rule["satisfied"] and rule["level"] == FAIL:
                rule["level"] = WARN
                rule["fix"] = f"면제 적용({exempt}) — 후속 PR에서 보강: {rule['fix']}"
    report = {
        "repo_kind": kind,
        "base": base,
        "head": head,
        "changed": classified,
        "rules": rules,
        "smells": smells,
        "pr_body": pr_findings,
        "exempt": exempt or "",
    }
    report["verdict"] = verdict(report)
    return report


def verdict(report: dict) -> str:
    levels: list[str] = []
    levels += [r["level"] for r in report["rules"] if not r["satisfied"]]
    levels += [s["level"] for s in report["smells"]]
    levels += [f["level"] for f in report["pr_body"]]
    if FAIL in levels:
        return FAIL
    if WARN in levels:
        return WARN
    return PASS


def render_markdown(report: dict) -> str:
    out: list[str] = []
    out.append("## 🧪 테스트 점검 영수증 (gardenstep-test-audit)")
    compare = f"{report.get('base')}...{report.get('head')}" if report.get("base") else "제공된 변경 목록"
    out.append(f"- 레포: `{report['repo_kind']}` · 비교: `{compare}` · 판정: **{report['verdict']}**")
    if report.get("exempt"):
        out.append(f"- 면제: {report['exempt']}")
    out.append("")
    out.append("### 변경 분류")
    out.append("| 분류 | 파일 |")
    out.append("|---|---|")
    for category in sorted(report["changed"]):
        files = report["changed"][category]
        out.append(f"| {category} | {'<br>'.join(f'`{f}`' for f in files)} |")
    out.append("")
    out.append("### 필수 테스트 규칙")
    if report["rules"]:
        out.append("| 규칙 | 결과 | 근거 | 고치는 법 |")
        out.append("|---|---|---|---|")
        for rule in report["rules"]:
            mark = "✅" if rule["satisfied"] else ("❌" if rule["level"] == FAIL else "⚠️")
            evidence = ", ".join(f"`{e}`" for e in rule["evidence"][:4])
            out.append(f"| {rule['id']} — {rule['title']} | {mark} | {evidence} | {rule['fix']} |")
    else:
        out.append("- 소스 변경이 없어 필수 테스트 규칙이 적용되지 않는다.")
    out.append("")
    out.append("### 테스트 코드 스멜")
    if report["smells"]:
        out.append("| 위치 | 수준 | 규칙 | 코드 | 고치는 법 |")
        out.append("|---|---|---|---|---|")
        for smell in report["smells"]:
            mark = "❌" if smell["level"] == FAIL else "⚠️"
            snippet = smell["snippet"].replace("|", "\\|")
            out.append(f"| `{smell['file']}:{smell['line']}` | {mark} {smell['level']} | {smell['rule']} | `{snippet}` | {smell['fix']} |")
    else:
        out.append("- 변경된 테스트 파일에서 스멜을 찾지 못했다.")
    if report["pr_body"]:
        out.append("")
        out.append("### PR 본문")
        for finding in report["pr_body"]:
            mark = "❌" if finding["level"] == FAIL else "⚠️"
            out.append(f"- {mark} {finding['rule']}: {finding['message']}")
    out.append("")
    if report["verdict"] == FAIL:
        out.append("**판정 FAIL — ❌ 항목을 고친 뒤 다시 점검한다. 리뷰는 PASS/WARN에서 시작한다.**")
    elif report["verdict"] == WARN:
        out.append("**판정 WARN — ⚠️ 항목은 리뷰어가 사람 눈으로 확인한다. PR 본문에 사유가 있으면 통과.**")
    else:
        out.append("**판정 PASS — 정책 자동 점검 통과. 스크립트가 못 보는 항목은 SKILL.md 4단계로 확인한다.**")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gardenstep 테스트 정책 점검")
    parser.add_argument("--repo", type=Path, default=Path("."), help="레포 루트")
    parser.add_argument("--base", help="비교 기준 ref (예: origin/dev)")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--changed-files", type=Path, help="git 대신 사용할 'STATUS path' 목록 파일")
    parser.add_argument("--pr-body", type=Path, help="PR 본문 파일 — 테스트 영수증 검사")
    parser.add_argument("--exempt", help="면제 사유 — FAIL 규칙을 WARN으로 낮춘다 (test-exempt 라벨)")
    parser.add_argument("--kind", choices=["fe", "admin", "server"], help="레포 종류 강제 지정")
    parser.add_argument("--json", action="store_true", help="JSON 출력")
    parser.add_argument("--no-fail", action="store_true", help="FAIL이어도 종료 코드 0")
    args = parser.parse_args(argv)

    changed = None
    if args.changed_files:
        changed = [line for line in args.changed_files.read_text(encoding="utf-8").splitlines() if line.strip()]
    elif not args.base:
        parser.error("--base 또는 --changed-files 중 하나가 필요하다")
    pr_body = args.pr_body.read_text(encoding="utf-8") if args.pr_body else None
    try:
        report = audit(args.repo, base=args.base, head=args.head, changed=changed, pr_body=pr_body, exempt=args.exempt, kind=args.kind)
    except subprocess.CalledProcessError as error:
        print(f"error: git diff 실패 — {error.stderr.strip()}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report))
    if report["verdict"] == FAIL and not args.no_fail:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
