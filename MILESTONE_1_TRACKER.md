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
8. [x] Timestamped initial schema and limits/cost SQL migrations; hosted application pending.
9. [x] Opaque anonymous cookies, hashed tokens, ownership-scoped HTTP/WebSocket access and origin checks.
10. [x] Conversation create/list/detail with composite cursor ordering and frontend load-more controls.
11. [x] Transactional message/request states and persisted streamed results.
12. [x] Idempotency keys, payload-conflict checks and concurrent duplicate-request locking.
13. [~] Mock, OpenAI-compatible and native Gemini adapters. Mock transport contract tests pass;
    live Gemini key/model verification still needs the user's free-tier API key.
14. [x] Provider total timeout/output limit, usage/cost metadata, durable IP/session limits,
    daily request caps, conservative paid budget reservations and no automatic duplicate provider calls.
15. [x] Persisted UI history, original-key retry/reconnect, reload reconciliation and stale-request handling.
16. [x] Backend tests for migrations, ownership, invalid input, provider errors, rate/budget limits,
    idempotency and concurrency. Browser tests cover isolation, reload, interrupted streaming and mobile UI.
17. [~] CI and public smoke workflows implemented; local checks pass. Hosted GitHub Actions result
    on the final commit still needs verification.
18. [~] Supabase/Render/Vercel deployment instructions, Render blueprint and Vercel config are ready.
    User has existing projects; their URLs, connected access and deployment secrets are still needed.
19. [~] Local browser and API/database restart checks pass; public hosted smoke and production
    cookie/domain behavior remain unverified.
20. [ ] Tag v0.1.0 only after all hosted acceptance criteria pass.

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

## External release inputs still needed

- Existing Supabase project URL, Render service URL and Vercel frontend URL / connected access.
- PostgreSQL runtime/migration secrets and exact frontend origin on Render.
- Google AI Studio key on a free-tier project. The chosen initial model is gemini-3.1-flash-lite;
  there is no paid fallback. See docs/deployment.md for the exact settings and data-use note.
- Successful hosted CI and public smoke run against the final deployment, then the release tag.

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
