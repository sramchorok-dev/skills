# Repeatable manual QA

Keep this workflow manual. Neither browser execution nor the fixture client belongs in CI.
Use the browser tool the user specified. If the user requires Ego Lite, do not fall back to another browser.
A new task space is not session isolation. If the tool cannot prove independent state, record BLOCKED for
isolation-dependent acceptance. Shared-profile public readback may be reported separately as an observation.

## Prepare only the prerequisite, test the named journey

For a review→PDF card, an API-prepared paid order is allowed as setup, but says nothing about signup,
checkout, real PG approval or notification delivery. Keep those steps in their own browser journeys.
Do not silently remove steps from an existing purchase card; create a source-backed subjourney version.

`qa_fixtures.py` supports the existing **loopback-only test-classpath lease API**. It does not start a server
or make this API available on public DEV. Check its source contract in the project's test support first.
Public DEV/prod origins, redirects and proxies are rejected. Unsupported environments stay BLOCKED.
Do not expose this endpoint, weaken its server guards, or insert paid orders with ad-hoc SQL to make a test pass.

```sh
# E2E_FIXTURE_TOKEN comes from the existing private secret store; never echo it.
python3 <skill>/scripts/qa_fixtures.py prepare --origin http://127.0.0.1:18080 \
  --run-id QA-YYYYMMDD-NN --lease-file <private-dir>/lease.json
python3 <skill>/scripts/qa_fixtures.py paid-order --lease-file <private-dir>/lease.json
python3 <skill>/scripts/qa_fixtures.py remaining --lease-file <private-dir>/lease.json
python3 <skill>/scripts/qa_fixtures.py cleanup --lease-file <private-dir>/lease.json
```

The client persists a random run-owned key before creation and uses a mode-0600 file for returned credentials.
Never commit this file. Mutations have no automatic retries. An unknown response keeps an intent record;
reconcile the same key using remaining/cleanup, never create another lease to hide it. A lease operation lock
prevents concurrent modifications. Cleanup succeeds only after DELETE and a separate remaining=0 readback;
then credentials are removed. The server verifies reference ownership; the client is not a substitute for it.
TTL is a fallback, not cleanup evidence. Attach the sanitized cleanup output as run evidence and register the
lease alias in browser_agent's resource ledger. Setup alone does not mark a fixture available: observe its
role/state/ownership and supply the regular fixture receipt. Browser context cleanup remains separate.

## Independent checks

Add an optional `grader` to a criterion in the **catalog**, increment its card version, and link the independent
source already required by `oracle`. Use only explicit expectations; do not derive them from today's screen.

```json
{"id":"C1","expected":"Total is 13500","oracle":"source-price-example",
 "grader":{"operator":"decimal-equals","value":"13500"}}
```

`equals` compares JSON values with the same type; `decimal-equals` compares finite numeric values exactly.
Capture a numeric amount without currency decoration as `observed_value`, keeping original visible text in
`observed` and evidence files. The recorder rejects a declared MATCH/MISMATCH that disagrees with the rule.
UNKNOWN remains possible when observation is unavailable. Unresolved sources remain UNKNOWN.
For visual/semantic checks retain explicit review: this deterministic guard neither proves image contents
nor catches a fabricated observation. No LLM score can override a price/permission mismatch.

## Select and order

```sh
python3 <skill>/scripts/qa_reliability.py plan --catalog <catalog.json> \
  --journeys J01,J02 --failed-ids CASE-01
```

The plan selects the union of **all P0 + critical + changed journeys + previous failures**. Gaps remain selected.
Use its `selected_ids` with `browser_agent init --profile full --ids ...`; validate freshness before execution.
Unselected cards stay visible in the full catalog. This is prioritization, not proof that other tests are redundant.
Do not replace a mandatory exhaustive matrix with pairwise cases until its independent inputs/constraints and
coverage policy are approved. Keep original P0 and matrix denominators.

## Repeat and distinguish failures

Plan at least 3 trials for a pilot (not a statistical reliability claim). Run each in a fresh proven session with new
owned fixtures, same catalog, revisions, viewport, model and browser. Record `environment.runtime`:
`browser_version`, `model`, `skill_revision`. Each trial gets a new run ID. Finish all planned trials or leave
missing trials explicit. Do not rerun until green and discard failures.

```sh
python3 <skill>/scripts/qa_reliability.py benchmark --expected-trials 3 --runs <run1> <run2> <run3>
python3 <skill>/scripts/qa_reliability.py defects --run <run1>
```

The benchmark revalidates evidence, rejects mixed scope/revision/runtime and duplicate runs, and retains missing
trials in its denominator. It reports first-pass coverage, eventual complete-trial rate, historical failures and
pending cleanup. Duration is observed attempt time, not wall time or cost. Unmeasured tokens/cost stay unknown.
Different skill versions require separate cohorts; compare results descriptively without merging them.
Classify failures in the narrative as product/agent/environment/oracle/unknown using evidence, not guessing from
FAIL alone. Defect drafts retain failures even after recovery; review evidence before creating a regression card.
No automatic issue posting. A fixed regression must reproduce the old defect and pass after the fix.

## CI measurement without changing coverage

Save REST run metadata and **all pages** of `/runs/ID/attempts/N/jobs` for the same attempt, then run:

```sh
python3 <skill>/scripts/ci_metrics.py --run-json <run.json> --jobs-json <jobs.json>
```

Missing jobs/times yield unknown aggregate duration; mixed attempts are rejected. Job seconds are resource time,
not billed cost. Test totals and reuse are unknown unless verified with their separate artifacts. Compare several
equivalent runs before changing partitioning or removing duplication. Preserve money/permissions/stock/idempotency/
schema checks and the aggregate required-check gate. Build artifacts and environment-specific values must stay
identical before consolidating duplicated image builds.

References: [agent evals](https://www.anthropic.com/research/demystifying-evals-for-ai-agents),
[test isolation](https://playwright.dev/docs/best-practices),
[GitHub workflow jobs API](https://docs.github.com/en/rest/actions/workflow-jobs).
