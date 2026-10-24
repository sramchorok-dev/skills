# Browser-agent catalog workflow

This mode adds versioned catalogs to the existing sheet-TC workflow. It does not replace `tc_cards.py`, `qa_record.py`, or the separately reviewed API matrix/copy tools. The browser-agent suite is never added to CI, a scheduler, or a deployment gate. Deterministic code tests remain required.

## Inputs and source freshness

Read the current sheet's `00 먼저읽기` rules, the private project's source map and catalog README. The public skill contains no internal QA rows or account data. Project cards live in the private service repository; environments, account secrets and run evidence remain outside git.

Before a run, fetch metadata and the relevant bounded tab ranges using the connected Sheets tools. Preserve the fetched time and values in the private snapshot. Compare current values with the catalog source payloads. Do not call a saved snapshot “latest.” Update affected source fingerprints and increment card versions when the acceptance criteria change. Original row numbers, historical verdicts and repeated display IDs remain separate from permanent source/card IDs. A row move alone is reconciled by tab, display ID and content fingerprint; duplicate display IDs require content review, never “first match.”

```bash
python3 <skill>/scripts/browser_agent.py validate --catalog <private-catalog.json>
python3 <skill>/scripts/browser_agent.py diff --before <old-catalog.json> --after <new-catalog.json>
python3 <skill>/scripts/browser_agent.py list --catalog <catalog.json> --profile critical
```

`full` selects all catalog cards. Other profiles are explicit card memberships. `--ids`, `--journey`, `--viewports` narrow the selection and do not count as a full critical run. `retest --run <old>` returns failed/blocked journeys; initialize a **new** run with those IDs. Every source needs a card or an approved exclusion. Mapping coverage and executable definition coverage are different: unresolved expectations remain visible.

## Environment and fixture contract

Copy the private project's environment template to the untracked run parent. Supply actual HTTPS origins, observed revisions for every service used by selected cards, observation time, verification evidence, responsible person and actual tool/model. Missing revisions block initialization. Never turn a guessed revision into evidence. Fixtures are availability aliases, not passwords. Only mark a fixture `available` after its account role, ownership, current state and independent price/expected data have been checked. Authentication via browser must not be replaced by token or localStorage injection in a login journey.

Read the installed browser tool guide first. Use the user-authorized task space/context; record the actual tool. A new tab or Ego TaskSpace is **not** a new incognito session. Prove isolation (empty stores/cart, correct role, new guest alias) without clearing the human's cookies or data. If Ego cannot supply an isolated context, a supported connected browser tool can create and close a dedicated context. Observe the rendered page/DOM after each bounded action group, choose the next action from that observation, and save screenshots. Do not substitute a canned Playwright runner for agent browser use. Record any fallback truthfully.

```bash
python3 <skill>/scripts/browser_agent.py init --catalog <catalog.json> \
  --environment <private-env.json> --run <private-runs/QA-YYYYMMDD-NN> \
  --run-id QA-YYYYMMDD-NN --profile critical
python3 <skill>/scripts/browser_agent.py template --run <run> --cell <card>@<viewport> --out <result.json>
```

`manifest.json` freezes catalog, selection and revisions. `catalog.json` is an immutable run snapshot. `init` creates zero passing results. On resume, re-observe the deployed revisions and source versions:

```bash
python3 <skill>/scripts/browser_agent.py resume --run <run> --catalog <current-catalog.json> --environment <fresh-env.json>
```

Changed source/card/revision/origin means a new run. Never combine prior PASS with the new version. The resume receipt is stored separately.

## Fixture readiness before execution

Run the read-only readiness check after preparing fixtures through existing documented tools/UI:

```bash
python3 <skill>/scripts/browser_agent.py fixture-check --catalog <catalog.json> --environment <private-env.json> --profile critical
```

It performs no network calls, seeding, login, payment or deletion. It lists runnable and blocked cells separately;
exit 2 means unresolved fixtures/specifications remain. `fixture_receipts[alias]` must include owner, source_contract,
checked_at and actual evidence file paths under the environment file directory's `evidence/` or `screenshots/`.
An `available` label without this proof is rejected at init. Unverified aliases may initialize a run for honest BLOCKED
receipts. Init freezes/hashes fixture proof files into the run. New fixture state requires a new run rather than silently
changing the original readiness snapshot. This check verifies documentation and artifacts, not the service state itself;
the browser agent remains responsible for observing current ownership/role/state.

`participant_role` groups list all fixture roles participating in a cell. A multi-role cell appears in more than one group;
do not sum these groups as unique execution totals or claim separate full-role coverage.

## Observe and record one cell

The result template contains every check ID, card/catalog fingerprints and revisions. Fill it from observations, never from the desired verdict:

- `preconditions_met`: boolean. If false, name the missing fixture/source/tool in `blocked_reason`, leave checks UNKNOWN. No claimed behavior observation can be hidden under precondition BLOCKED.
- `session`: real context ID, role alias, `isolation_verified: true`, and concrete proof. Never save secrets.
- `mode`: `live-browser` or explicitly supported `fault-injection`. API substitution is rejected. A fault injection does not demonstrate the normal external integration.
- `steps_completed`: observed step IDs. An early mismatch can be FAIL with later checks UNKNOWN. Unexecuted steps can never produce PASS.
- `checks`: all criterion IDs exactly once, status MATCH/MISMATCH/UNKNOWN, actual text/value and relative evidence paths. Generic “OK” is rejected. Unresolved criterion oracles stay UNKNOWN. Explicit known mismatches remain FAIL even if unrelated criteria are blocked.
- `started_at`, `finished_at`: real ISO timestamps. Save an image/time/usage receipt for costly AI generation and preserve the first failed attempt.

Evidence must be nonempty files under that run's `screenshots/` or `evidence/`. The recorder hashes them. A path string without a real file, missing criterion, wrong revision or modified snapshot cannot pass. Do not overwrite evidence between attempts. No tool can prove that a human/agent's observation is honest; review screenshots against the expected value.

```bash
python3 <skill>/scripts/browser_agent.py record --run <run> <result.json>
python3 <skill>/scripts/browser_agent.py resource --run <run> <resource-entry.json>
python3 <skill>/scripts/browser_agent.py summary --run <run>
```

The result is append-only by attempt. Summary revalidates all receipts and evidence. It writes `execution.tsv`, `coverage.json` and `report.md`; these are local artifacts, not spreadsheet updates or messages. Retests preserve historical failures.

## Side effects and cleanup

Only mutate run-owned QA resources on DEV. Shared prices/stock/catalog settings are not fixture preparation shortcuts. A paid fixture may be used for the review/PDF subjourney, but payment is then unexecuted. Real payment/refund, outbound email/notification and physical-device tests need their named fixture and current authorization; an unavailable external system is BLOCKED.

Use `created-resources.json` for resource alias/ID, run owner, creating cell, cleanup action and status (`created`, `cleanup-blocked`, `cleaned`, `retained-approved`). For `cleaned`, provide a real run-local evidence file; its hash is revalidated by summary. For `retained-approved`, also provide `retention_decision` with `decided_by`, `decision`, `scope` naming the exact alias, and `decided_at`. A label or nonexistent path cannot close cleanup. Never store contact details, order tokens or credentials. Account-secret mappings stay in the existing private credential store. Do not delete a resource unless run ownership is proved. Summary lists all pending cleanup; no pending cleanup is a prerequisite to selected-scope completion.

Production exists only as an explicitly selected `prod-readonly` catalog profile: all selected cards must be read-only with no side effects. This is not authorization to run production. Existing sheet mode stays DEV-only. No order, login mutation, PG, admin write or resource cleanup in production.

## Reporting

Report PASS/FAIL/BLOCKED/NOT_RUN/N/A counts with selected scope and revision. Execution coverage is `(PASS+FAIL)/(selected−approved N/A)`; pass coverage is `PASS/(selected−approved N/A)`. BLOCKED and NOT_RUN stay in the denominator. A narrower smoke profile cannot become “all P0 passed.” State unresolved sources, incomplete external integration, browser-tool failures, first failures and cleanup debt explicitly. Frame/focus/real-iOS emulation differences require separate evidence. Prepare defect drafts; send or write to shared systems only on explicit user instruction.
