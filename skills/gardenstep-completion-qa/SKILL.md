---
name: gardenstep-completion-qa
description: Run the Gardenstep completion gate after any code, schema, configuration, CI, or deployment change in gardenstep, gardenstep_admin, gardenstep-server, gardenstep-ai, or a cross-repo flow. Invoke before claiming a feature or fix is complete, opening or merging its PR, handing it to a teammate, or finishing a deployment. Map every changed behavior to TC, integration/build, Playwright E2E, and live-smoke evidence; keep skipped or unverified gates explicit.
---

# Gardenstep completion QA

Use this as a **completion gate**, not as a generic request to run every command. The diff and risk decide the
coverage; the final evidence decides whether the word “complete” is accurate.

## 1. Establish the test contract

1. Resolve each affected repository. Run every command inside that repository's own checkout.
2. Read its `AGENTS.md`/`CONTEXT.md`, test documentation, package/build scripts, and CI workflow before choosing
   commands. Treat those files as the current command source of truth.
3. State the public seams under test before adding tests: API boundary, domain service, rendered screen, persisted
   state, generated artifact, or deployed URL. If the contract itself is ambiguous, confirm it with the user.
4. Build a compact coverage matrix with one row per changed behavior and columns for TC, integration/build, E2E,
   and post-deploy verification. Mark genuinely irrelevant gates `N/A` with a reason.

Completion criterion: every behavior in the diff has an observable seam and a planned gate or a written `N/A`
reason.

Read [references/repo-gates.md](references/repo-gates.md) for repository-specific branches and deployment
gotchas.

## 2. Lock the behavior with TC

For a bug, first add the smallest public-boundary regression TC and record the expected failure. Then make it
green. Add the boundary, error, authorization, retry/idempotency, deterministic-seed, and serialization cases that
the changed behavior can actually reach.

Prefer behavior assertions over internal calls. Expected values come from the specification or an independently
worked example. A check that repeats the implementation formula, asserts a hard-coded “success” flag, or only
proves that a mock was called is not evidence.

Completion criterion: the reported bug is red before the fix and green after it; newly reachable failure paths
and important bounds have executable cases.

## 3. Run repository gates

Run narrow feedback first, then the full relevant gate:

- changed-file lint/type/static analysis;
- targeted TC and integration tests for the affected module;
- the repository's complete test suite when shared code, contracts, persistence, security, pricing, or CI changes;
- production build/package generation;
- migration/schema validation when persistence changes;
- cross-repository contract tests on both producer and consumer when a payload or release order changes.

Treat warnings separately from failures. Record a warning only after deciding whether it blocks this change.

Completion criterion: every applicable command exits successfully and its exact scope/count is captured.

## 4. Run user-journey E2E

Exercise each changed happy path and its highest-risk failure path through the real public screen or endpoint.
For browser work, verify stable `data-testid` contracts, desktop and affected mobile layouts, console/page errors,
network failures, loading/retry state, and feature/data-mode branches. Avoid fixed sleeps; wait on observable state.

When the workflow spans repositories, run the journey against the same contract/version combination intended for
deployment. A component-only green run does not close a cross-repository journey.

Completion criterion: each affected journey has a named E2E result, and browser/API errors are zero or explicitly
explained.

## 5. Verify release and live state

When deployment is in scope, inspect the PR and CI until required checks finish, confirm unresolved review threads
are zero, then verify the deployed commit, container/health state, HTTP contract, and one real browser journey.
Keep DEV and production evidence separate. A DEV success never implies production deployment.

Completion criterion: the target environment serves the intended revision and the live smoke reproduces the
critical local assertion.

## 6. Audit and report

Re-read the final diff, run whitespace/status checks, and ensure unrelated user changes remain untouched. Report
using this compact receipt:

```markdown
QA completion receipt
- Scope: <repositories, behavior, environment>
- TC: <command, passed/failed count, key boundaries>
- Integration/build: <command and result>
- E2E: <named journeys, viewport/mode, result>
- Live smoke: <URL/endpoint, revision, result or N/A reason>
- Review: <PR checks, unresolved threads, clean/dirty worktrees>
- Warnings: <non-blocking findings>
- Unverified/blockers: <none, or exact remaining gate>
- Verdict: COMPLETE | NOT COMPLETE
```

Use `COMPLETE` only when every applicable row is green. A skipped, flaky, timed-out, or unavailable required gate
keeps the verdict `NOT COMPLETE` and names the next action.
