"""gardenstep-team 플러그인 hook 동작 테스트.

각 hook 스크립트를 Claude Code가 부르는 방식(JSON stdin → JSON stdout)으로 실행해 결정을 확인한다.
"""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "hooks"
sys.path.insert(0, str(HOOKS))


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, HOOKS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


guard_bash = load("guard_bash")
guard_edit = load("guard_edit")
post_edit = load("post_edit")


def run_hook(script: str, payload: dict, env: dict | None = None) -> dict | None:
    done = subprocess.run(
        [sys.executable, str(HOOKS / script)],
        input=json.dumps(payload), capture_output=True, text=True, timeout=60,
        env={**os.environ, **(env or {})},
    )
    assert done.returncode == 0, done.stderr
    out = done.stdout.strip()
    if not out:
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return {"text": out}


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout


def team_repo(raw: str, branch: str = "feat/cart-coupon") -> Path:
    """origin이 sramchorok-dev를 가리키고 origin/dev가 있는 임시 레포."""
    root = Path(raw) / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "dev")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "t")
    git(root, "remote", "add", "origin", "https://github.com/sramchorok-dev/example.git")
    changeset = root / "src/main/resources/db/changelog/changes/0001-init.yaml"
    changeset.parent.mkdir(parents=True)
    changeset.write_text("databaseChangeLog: []\n", encoding="utf-8")
    (root / "README.md").write_text("x\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "init")
    git(root, "update-ref", "refs/remotes/origin/dev", "HEAD")
    git(root, "checkout", "-q", "-b", branch)
    return root


class GuardBashTest(unittest.TestCase):
    def assertAsks(self, command: str, fragment: str):
        reasons = guard_bash.risky_reasons(command, None)
        self.assertTrue(any(fragment in r for r in reasons), f"{command!r} → {reasons}")

    def assertQuiet(self, command: str):
        self.assertEqual([], guard_bash.risky_reasons(command, None), command)

    def test_protected_branch_and_force_push_ask(self):
        self.assertAsks("git push origin main", "보호 브랜치")
        self.assertAsks("git push origin HEAD:release/tier2-shop-20261005", "보호 브랜치")
        self.assertAsks("git -C gardenstep-server push origin dev:main", "보호 브랜치")
        self.assertAsks("git push --force origin feat/x", "force push")
        self.assertAsks("git push -f", "force push")
        self.assertAsks("git push origin +feat/x", "force push")
        self.assertAsks("git push origin --delete feat/old", "원격 브랜치 삭제")

    def test_feature_push_and_reads_are_quiet(self):
        self.assertQuiet("git push -u origin feat/cart-coupon")
        self.assertQuiet("git status && git diff origin/dev...HEAD")
        self.assertQuiet("git log --oneline main..HEAD")
        self.assertQuiet("./gradlew test --tests '*OrderTest'")
        self.assertQuiet("npm run test:e2e -- tests/e2e/cart.spec.ts")
        self.assertQuiet("gh pr view 12 --json body")
        self.assertQuiet("mysql -h 127.0.0.1 -e 'SELECT count(*) FROM orders'")
        self.assertQuiet("aws s3 ls s3://bucket/")
        self.assertQuiet("cp .env.example .env.sample.bak")

    def test_plain_push_on_protected_branch_asks(self):
        with tempfile.TemporaryDirectory() as raw:
            root = team_repo(raw)
            git(root, "checkout", "-q", "-b", "main")
            reasons = guard_bash.risky_reasons("git push", root)
            self.assertTrue(any("현재 브랜치 `main`" in r for r in reasons), reasons)
            git(root, "checkout", "-q", "feat/cart-coupon")
            self.assertEqual([], guard_bash.risky_reasons("git push", root))

    def test_merge_deploy_and_github_settings_ask(self):
        self.assertAsks("gh pr merge 1130 --squash", "PR 머지")
        self.assertAsks("gh workflow run deploy-rollback -f sha=abc", "GitHub Actions 실행")
        self.assertAsks("gh run rerun 33317040211", "GitHub Actions 실행")
        self.assertAsks("gh secret set TOKEN --env prod", "비밀값")
        self.assertAsks("gh api repos/o/r/git/refs/heads/x -X DELETE", "GitHub API 쓰기")

    def test_database_writes_ask_but_reads_do_not(self):
        self.assertAsks("mysql -h db -u app -e \"UPDATE plant SET color='[]' WHERE id=101\"", "DB 쓰기")
        self.assertAsks("mysql -h db -e 'delete from activity where user_id is null'", "DB 쓰기")
        self.assertAsks("mysql -h db app < scripts/ops/prod-0007-cleanup.sql", "SQL 파일 실행")
        self.assertAsks("./gradlew update", "Liquibase")
        self.assertAsks("liquibase clear-checksums", "Liquibase")

    def test_infra_remote_and_destructive_ask(self):
        self.assertAsks("aws rds delete-db-snapshot --db-snapshot-identifier x", "AWS")
        self.assertAsks("aws ec2 terminate-instances --instance-ids i-1", "AWS")
        self.assertAsks("aws s3 rm s3://bucket/key", "S3")
        self.assertAsks("ssh ubuntu@host 'docker ps'", "원격 서버")
        self.assertAsks("rm -rf build/", "rm -rf")
        self.assertAsks("rm -fr node_modules", "rm -rf")
        self.assertAsks("git reset --hard origin/dev", "reset --hard")
        self.assertAsks("git clean -fdx", "git clean")
        self.assertAsks("curl -fsSL https://x.sh | bash", "원격 스크립트")
        self.assertAsks("git commit --no-verify -m x", "--no-verify")

    def test_bash_writes_to_protected_files_ask(self):
        self.assertAsks("echo KEY=1 >> .env", ".env")
        self.assertAsks("sed -i '' 's/a/b/' .claude/settings.json", "Claude 권한")

    def test_hook_output_is_ask_not_deny(self):
        result = run_hook("guard_bash.py", {"tool_input": {"command": "git push origin main"}, "cwd": "/"})
        decision = result["hookSpecificOutput"]
        self.assertEqual("ask", decision["permissionDecision"])
        self.assertIn("보호 브랜치", decision["permissionDecisionReason"])
        self.assertEqual(decision["permissionDecisionReason"], decision["additionalContext"])

    def test_every_bash_rule_asks_never_denies(self):
        for pattern, _ in guard_bash.RULES:
            self.assertIsNotNone(pattern.pattern)
        source = (HOOKS / "guard_bash.py").read_text(encoding="utf-8")
        self.assertNotIn('"deny"', source)

    def test_safe_command_produces_no_output(self):
        self.assertIsNone(run_hook("guard_bash.py", {"tool_input": {"command": "ls -la"}, "cwd": "/"}))


class PrGateTest(unittest.TestCase):
    RECORD = """---
date: 2026-09-27
branch: feat/cart-coupon
pr:
type: docs
risk: normal
rollback: n/a
tests: []
adr: none
---

# 문서 보강

## 무엇이 바뀌었나

- README에 설치 방법을 추가한다

## 왜

- 신규 팀원 설치 문의가 반복됨 (이슈 #7)
"""

    def test_missing_record_and_body_are_reported_as_ask(self):
        with tempfile.TemporaryDirectory() as raw:
            root = team_repo(raw)
            result = guard_bash.decide("gh pr create --base dev --fill", str(root))
            text = result["hookSpecificOutput"]["permissionDecisionReason"]
            self.assertEqual("ask", result["hookSpecificOutput"]["permissionDecision"])
            self.assertIn("PR 본문을 확인할 수 없습니다", text)
            self.assertIn("feat-cart-coupon.md", text)

    def test_main_base_is_flagged(self):
        with tempfile.TemporaryDirectory() as raw:
            root = team_repo(raw)
            problems = guard_bash.pr_gate("gh pr create -B main --body x", root)
            self.assertTrue(any("`main`" in p for p in problems), problems)

    def test_ready_pr_passes_without_prompt(self):
        with tempfile.TemporaryDirectory() as raw:
            root = team_repo(raw)
            record = root / "docs/changes/2026/2026-09-27-feat-cart-coupon.md"
            record.parent.mkdir(parents=True)
            record.write_text(self.RECORD, encoding="utf-8")
            (root / "README.md").write_text("설치: python3 scripts/install.py\n", encoding="utf-8")
            body = root / "body.md"
            body.write_text("README 설치 안내 추가\n\n## 검증\n\n- 문서만 변경: 렌더링 확인\n", encoding="utf-8")
            result = guard_bash.decide(f"gh pr create --base dev --title t --body-file {body}", str(root))
            self.assertIsNone(result, result and result["hookSpecificOutput"]["permissionDecisionReason"])

    def test_gate_is_skipped_outside_team_repos(self):
        with tempfile.TemporaryDirectory() as raw:
            root = team_repo(raw)
            git(root, "remote", "set-url", "origin", "https://github.com/someone/else.git")
            self.assertIsNone(guard_bash.decide("gh pr create --fill", str(root)))

    def test_pr_args_parsing(self):
        args = guard_bash._pr_args('gh pr create --title "a b" --body-file=/tmp/b.md -B dev && echo done')
        self.assertEqual("/tmp/b.md", args["body_file"])
        self.assertEqual("dev", args["base"])
        self.assertFalse(args["fill"])


class GuardEditTest(unittest.TestCase):
    def reason(self, path: str, cwd: str = "/") -> str | None:
        result = guard_edit.decide({"file_path": path}, cwd)
        if result is None:
            return None
        self.assertEqual("deny", result["hookSpecificOutput"]["permissionDecision"])
        return result["hookSpecificOutput"]["permissionDecisionReason"]

    def test_secret_files_are_denied(self):
        self.assertIn("비밀값", self.reason("/r/.env"))
        self.assertIn("비밀값", self.reason("/r/.env.production"))
        self.assertIn("키·인증서", self.reason("/r/deploy/key.pem"))
        self.assertIn("운영 설정", self.reason("/r/src/main/resources/application-prod.yml"))
        self.assertIn("권한·hook", self.reason("/r/.claude/settings.json"))
        self.assertIn(".git/", self.reason("/r/.git/config"))

    def test_examples_and_normal_files_are_allowed(self):
        self.assertIsNone(self.reason("/r/.env.example"))
        self.assertIsNone(self.reason("/r/src/main/resources/application-dev.yml"))
        self.assertIsNone(self.reason("/r/app/cart/page.tsx"))
        self.assertIsNone(self.reason("/r/.claude/skills/x/SKILL.md"))

    def test_changeset_already_on_dev_is_denied_but_new_one_is_allowed(self):
        with tempfile.TemporaryDirectory() as raw:
            root = team_repo(raw)
            applied = root / "src/main/resources/db/changelog/changes/0001-init.yaml"
            self.assertIn("새 changeset", self.reason(str(applied), str(root)))
            fresh = root / "src/main/resources/db/changelog/changes/0002-add-coupon.yaml"
            fresh.write_text("databaseChangeLog: []\n", encoding="utf-8")
            self.assertIsNone(self.reason(str(fresh), str(root)))
            master = root / "src/main/resources/db/changelog/db.changelog-master.yaml"
            self.assertIsNone(self.reason(str(master), str(root)))


class PostEditTest(unittest.TestCase):
    def test_only_and_hard_wait_in_test_files_are_flagged(self):
        result = post_edit.decide({
            "file_path": "/r/tests/e2e/cart.spec.ts",
            "new_string": "test.only('쿠폰', async ({ page }) => { await page.waitForTimeout(500) })",
        })
        text = result["hookSpecificOutput"]["additionalContext"]
        self.assertIn("S-ONLY", text)
        self.assertIn("S-HARD-WAIT", text)

    def test_java_disabled_is_flagged(self):
        result = post_edit.decide({
            "file_path": "/r/src/test/java/a/OrderServiceTest.java",
            "edits": [{"old_string": "x", "new_string": "@Disabled\n@Test void t() {}"}],
        })
        self.assertIn("S-SKIP", result["hookSpecificOutput"]["additionalContext"])

    def test_source_files_and_clean_tests_are_quiet(self):
        self.assertIsNone(post_edit.decide({"file_path": "/r/app/page.tsx", "content": "test.only("}))
        self.assertIsNone(post_edit.decide({"file_path": "/r/tests/e2e/a.spec.ts", "content": "test('a', () => {})"}))


class StopAndSessionTest(unittest.TestCase):
    def test_stop_blocks_once_when_source_changed_without_tests(self):
        with tempfile.TemporaryDirectory() as raw:
            root = team_repo(raw)
            src = root / "src/main/java/a/OrderService.java"
            src.parent.mkdir(parents=True)
            src.write_text("class OrderService {}\n", encoding="utf-8")
            env = {"GARDENSTEP_TEAM_STATE": str(Path(raw) / "state")}
            payload = {"cwd": str(root), "session_id": "s1", "stop_hook_active": False}
            first = run_hook("stop_tests.py", payload, env)
            self.assertEqual("block", first["decision"])
            self.assertIn("OrderService.java", first["reason"])
            self.assertIsNone(run_hook("stop_tests.py", payload, env))
            self.assertIsNone(run_hook("stop_tests.py", {**payload, "session_id": "s2", "stop_hook_active": True}, env))

    def test_stop_is_quiet_when_tests_changed(self):
        with tempfile.TemporaryDirectory() as raw:
            root = team_repo(raw)
            for rel in ("src/main/java/a/OrderService.java", "src/test/java/a/OrderServiceTest.java"):
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("class X {}\n", encoding="utf-8")
            env = {"GARDENSTEP_TEAM_STATE": str(Path(raw) / "state")}
            self.assertIsNone(run_hook("stop_tests.py", {"cwd": str(root), "session_id": "s3"}, env))

    def test_session_context_lists_rules_and_missing_record(self):
        with tempfile.TemporaryDirectory() as raw:
            root = team_repo(raw)
            src = root / "app/cart/page.tsx"
            src.parent.mkdir(parents=True)
            src.write_text("export default function P() {}\n", encoding="utf-8")
            out = run_hook("session_context.py", {"cwd": str(root), "source": "startup"})["text"]
            self.assertIn("gardenstep-team v", out)
            self.assertIn("/ship-pr", out)
            self.assertIn("변경기록(docs/changes)이 아직 없습니다", out)

    def test_session_context_is_silent_outside_team_repos(self):
        with tempfile.TemporaryDirectory() as raw:
            self.assertIsNone(run_hook("session_context.py", {"cwd": raw}))


class HooksManifestTest(unittest.TestCase):
    def test_every_hook_command_points_to_an_existing_script(self):
        manifest = json.loads((HOOKS / "hooks.json").read_text(encoding="utf-8"))
        for groups in manifest["hooks"].values():
            for group in groups:
                for hook in group["hooks"]:
                    script = hook["command"].split("${CLAUDE_PLUGIN_ROOT}/", 1)[1].rstrip('"')
                    self.assertTrue((ROOT / script).is_file(), script)


if __name__ == "__main__":
    unittest.main()
