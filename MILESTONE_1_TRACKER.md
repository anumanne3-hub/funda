# Milestone 1 tracker — v0.1.0

Updated 2026-11-03. `[x]` implemented and locally verified; `[~]` implemented with external
verification pending; `[ ]` not completed. Do not equate a deployment template with a live deployment.

1. [x] Execution order and acceptance gates.
2. [x] Frontend/backend structure, environment examples and ignore rules.
3. [x] FastAPI settings, structured logs, request IDs, safe errors, health and database readiness.
4. [x] Versioned WebSocket protocol and deterministic mock streaming.
5. [x] Responsive chat, conversation navigation, empty/loading/error/disabled/retry states.
6. [x] Python uv.lock, npm package-lock.json, formatting, lint, type checks, production build and audits.
7. [x] PostgreSQL Compose configuration, SQLAlchemy sessions and Supabase-native SQL migrations; portable PostgreSQL tested locally.
8. [x] Timestamped initial schema and limits/cost SQL migrations; user confirmed hosted migrations applied.
9. [x] Opaque anonymous cookies, hashed tokens, ownership-scoped HTTP/WebSocket access and origin checks.
10. [x] Conversation create/list/detail with composite cursor ordering and frontend load-more controls.
11. [x] Transactional message/request states and persisted streamed results.
12. [x] Idempotency keys, payload-conflict checks and concurrent duplicate-request locking.
13. [x] Mock, OpenAI-compatible and native Gemini adapters. Transport contract tests pass;
    user reports Gemini configured and strict live smoke now passes with non-mock output.
14. [x] Provider total timeout/output limit, usage/cost metadata, durable IP/session limits,
    daily request caps, conservative paid budget reservations and no automatic duplicate provider calls.
15. [x] Persisted UI history, original-key retry/reconnect, reload reconciliation and stale-request handling.
16. [x] Backend tests for migrations, ownership, invalid input, provider errors, rate/budget limits,
    idempotency and concurrency. Browser tests cover isolation, reload, interrupted streaming and mobile UI.
17. [x] Hosted CI and dedicated GitHub Actions public smoke passed on release commit
    cf5f0651817cede8e929d4cec9bd028909149b2f, including real-provider and live browser checks.
18. [x] Supabase/Render/Vercel deployment is live. Public API health/readiness and browser
    session creation work; Render database connection and CORS issues were resolved.
19. [x] Local API/database restart checks and public API/browser smoke pass, including production
    cookies, isolation, reload and stream recovery. User confirmed conversations and messages
    remain unchanged after a Render service restart.
20. [x] Published v0.1.0 on cf5f0651817cede8e929d4cec9bd028909149b2f after CI and public smoke passed.

## Recorded local verification

- PostgreSQL 18: 23 backend tests passed, including concurrent duplicate requests.
- SQLite suite: 21 passed and the PostgreSQL concurrency case skipped before adding the Gemini
  adapter test; the final full check is recorded below when rerun.
- Previous Alembic roundtrip passed before conversion. SQL migration verification is recorded below.
- API and workspace PostgreSQL restart: committed history and duplicate-free retry preserved.
- Frontend: production build, TypeScript and ESLint passed.
- Chromium: 3 browser tests passed; the first Windows sandbox run needed helper-process cleanup.
- Python/npm dependency audits: no known vulnerabilities reported.
- Source and built-asset secret-pattern scans passed. This is a targeted pattern scan, not a proof
  that arbitrary secrets cannot exist; hosted environment and log checks remain part of release.

## Release status

Milestone 1 is complete. Tag `v0.1.0` points to the verified release commit
`cf5f0651817cede8e929d4cec9bd028909149b2f`.

- [Hosted CI passed](https://github.com/anumanne3-hub/funda/actions/runs/41619743266).
- [Dedicated public smoke passed](https://github.com/anumanne3-hub/funda/actions/runs/41622856935).
- [Release tag](https://github.com/anumanne3-hub/funda/releases/tag/v0.1.0).
- Hosted restart persistence was confirmed by the user; earlier pending-status notes
  below are historical and superseded by these results.

## Acceptance gate

- Public frontend, health and readiness are reachable.
- Two browser sessions cannot see each other's data.
- A visitor can send a message, receive streamed output, reload and recover history.
- Replaying a request does not duplicate a message or provider operation.
- API/database restarts preserve data.
- Provider errors are controlled and leave the API healthy.
- Secrets are absent from source, frontend assets, error responses and logs.

## Supabase SQL migration conversion

- Native SQL migrations now live at repository-root `supabase/migrations`.
- Removed both Python migration trees and Render Alembic pre-deploy command.
- Existing hosted schemas require inspection/baselining; no remote database was changed.


## Hosted verification ? 2026-11-03

Tested deployment at commit `7a35c4c911602691909d422749907aa9bf2edec0`:

- Frontend: https://funda-geni.vercel.app
- API: https://funda-g0wg.onrender.com
- Public API smoke passed: health, write readiness, anonymous session, conversation creation,
  WebSocket streaming, replay with no duplicate messages, persisted history and cross-session isolation.
- Chromium against the live frontend: all 3 tests passed, covering history after reload,
  separate browser sessions, reload during streaming and mobile composer layout.
- Hosted startup takes more than five seconds across sequential API calls. External Playwright
  assertions now allow 30 seconds; local assertions retain five seconds.
- Provider probe completed successfully but returned the deterministic `Mock assistant:` prefix.
  This is evidence of mock operation, not a verified Gemini call. The release smoke workflow now
  sets `SMOKE_REQUIRE_REAL_PROVIDER=true` and fails if it receives mock output.
- GitHub reports `Vercel ? funda-geni` success for the tested commit. The separate `Vercel ? funda`
  project reports failure; it is not the frontend URL tested above.
- Hosted CI passed for this commit: [Milestone 1 checks run 41617492526](https://github.com/anumanne3-hub/funda/actions/runs/41617492526).
  The initial connector lookup only returned PR-triggered runs; the direct push-run lookup
  confirmed this successful result.
- Backend local SQLite: 31 passed, 3 PostgreSQL-only tests skipped. Latest PostgreSQL verification
  earlier in this session: 34 passed, including SQL migrations and concurrent duplicate handling.
- Backend lint/type checks and frontend formatting/lint/type/build checks passed.
- Refreshed Python and npm dependency audits both report no known vulnerabilities.
- Source secret-pattern scan: 71 files passed; built assets: 4 files passed. This is a pattern scan,
  not proof that every possible secret is absent. Production logs/settings need separate review.
- No hosted restart, database reset, remote release tag, or real-provider success is claimed.

These results verify the deployed commit above. Changes to verification workflows and this tracker
still require hosted CI on their final commit before tagging `v0.1.0`.


## Verification branch follow-up

- Hosted push and pull-request CI passed for verification commit
  `1695136fb8b459f4b33e9658e898c0e0bbf00839`:
  [push run](https://github.com/anumanne3-hub/funda/actions/runs/41618987140),
  [PR run](https://github.com/anumanne3-hub/funda/actions/runs/41619016987).
- Strict live smoke rejected the deployed mock response as intended.
- Gemini startup configuration now defaults the model when omitted, identifies missing keys
  separately from stale mock-model overrides, and hides validation input values.
  The Render startup failure still requires a successful deployment/provider call before closure.


## Real-provider live verification ? 2026-11-03

- Strict public API smoke passed with `SMOKE_REQUIRE_REAL_PROVIDER=true` against the production
  frontend/API origins: health, write readiness, real streamed reply, replay without duplicate
  messages, persisted history and isolation of a second session.
- This supersedes the earlier mock-provider result. The user reports Gemini is configured;
  the live check confirms a successful non-mock reply without inspecting or exposing secrets.
- Hosted push and PR CI also passed for settings-fix commit
  `37e819195c217992850cbecd0f5caaf7adfcfbe5` (runs 41619432101 and 41619437735).
- Hosted restart remains pending: the Render integration is not installed/connected.
  No production restart, schema change, reset or release tag was performed.


## Hosted restart confirmation - 2026-11-03

- User restarted the Render service and confirmed existing conversations and messages
  remained unchanged. This closes the hosted API restart persistence check.
- This is user-reported verification; the assistant did not perform the restart or compare
  its private checkpoint after the restart. No database restart or reset is claimed.
- Earlier pending-restart and provider-setup notes above describe historical status and
  are superseded by the real-provider smoke result and this confirmation.


## Final release verification - 2026-11-03

- Ran the dedicated GitHub Actions public-smoke workflow on release commit `cf5f065`.
  Strict real-provider API checks and all live browser tests passed (run 41622856935).
- Confirmed hosted CI passed on the same commit (run 41619743266).
- Created and read back remote tag `v0.1.0`, pointing to the verified commit.
- No service restart, application deployment, schema change or database reset was performed
  during this final release step. The workflow created isolated test sessions/conversations.
