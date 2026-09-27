# Gardenstep repository gates

Load only the branches touched by the current diff. Discover the exact commands from each repository before
execution because scripts and CI evolve.

## `gardenstep` user frontend

- Follow `tests/e2e/README.md`: browser specs use stable `data-testid`; unit specs do not use the `page` fixture.
- Inspect `.github/workflows/cicd.yml` for the current feature-flag and local/remote data-mode matrix. A new remote
  regression must be included in the CI remote-mode list as well as runnable locally.
- Shared shell, cart, quote, payment, authentication, event tracking, and flag routing changes justify the full
  Playwright suite plus a production build.
- Capture Chromium console errors, page errors, broken images, and horizontal overflow on affected viewports.

## `gardenstep-server` backend

- Start with the affected JUnit class/package, then run the complete test suite and build for shared domain,
  transaction, pricing, payment, authorization, persistence, or configuration changes.
- Validate Liquibase/schema changes on the relevant profile. Verify rollback/compatibility order before a
  cross-repository deploy.
- Keep LLM/network calls outside DB transactions. For LLM changes, include timeout/failure and latency/usage
  evidence.
- For deterministic layout/quote work, cover repeated-input equality, bounds, rounding, exclusion/overlap,
  label-to-BOM equality, and explicit failure when constraints cannot be satisfied.

## `gardenstep_admin` admin frontend

- Cover authorization and CRUD failure states as well as the happy path.
- Verify the backend role contract; an authenticated guest is not equivalent to an admin.
- Run the repository's lint/type/build gates and affected browser journey.

## Cross-repository and deployment

- Name the producer/consumer versions and deployment order for API changes.
- Use the project server-access procedure for SSH/container checks without printing secrets.
- After merge, inspect the merge SHA and the push-triggered deploy workflow separately from PR CI.
- Verify HTTP status/content headers and a real browser interaction on the target domain. Confirm DEV versus
  production explicitly and preserve `noindex` on internal public prototypes.
