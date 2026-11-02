# Milestone 1 tracker — v0.1.0

Status values: `[x]` done, `[~]` in progress, `[ ]` pending, `[!]` blocked.

1. [x] Define the Milestone 1 execution order and acceptance gates.
2. [x] Add frontend and backend project structure, environment templates, and ignore rules.
3. [x] Add FastAPI application configuration, structured logging, request IDs, `/health`, and `/ready`.
4. [x] Define a versioned WebSocket chat protocol and mock token streaming.
5. [x] Build a simple responsive React chat UI with empty, connecting, streaming, error, and retry states.
6. [~] Install and lock current dependencies; run lint, type checks, tests, and production builds.
   - Backend dependencies are installed; Ruff passes and both health/WebSocket tests pass.
   - A reproducible Python lockfile is still pending.
   - Frontend source is pinned to React 19.3 and Vite 8.3.5; Node.js/npm are not installed locally.
7. [ ] Add local PostgreSQL, SQLAlchemy session management, and Alembic.
8. [ ] Create migration `0001_initial_chat` with anonymous sessions, conversations, messages, and chat requests.
9. [ ] Implement opaque anonymous-session cookies and ownership-scoped conversation queries.
10. [ ] Implement HTTP conversation create/list/detail endpoints with cursor pagination.
11. [ ] Persist user messages and pending/completed/failed assistant requests transactionally.
12. [ ] Enforce `Idempotency-Key` so retries do not duplicate turns or provider calls.
13. [ ] Replace mock-only generation with a provider adapter plus one real LLM provider.
14. [ ] Add provider timeout, rate-limit, token-limit, usage/cost metadata, and controlled retry behavior.
15. [ ] Connect the UI to persisted conversations and reconcile WebSocket reconnect/retry behavior.
16. [ ] Add database, ownership, validation, timeout, idempotency, WebSocket, and UI tests.
17. [ ] Add CI for formatting, linting, type checks, tests, builds, dependency audit, and secret scanning.
18. [ ] Create Supabase, Render, and Vercel environments; configure secrets, cookies, CORS, and migration command.
19. [ ] Run public smoke tests for isolation, chat, reload persistence, restart persistence, and secret exposure.
20. [ ] Tag `v0.1.0` only after every acceptance criterion passes.

## Current local blockers

- Install Node.js supported by Vite 8, then generate `package-lock.json` and verify the frontend.
- Install Docker Desktop or provide another local PostgreSQL instance for database work.
- Install backend dependencies before running pytest and the API.

## Milestone acceptance gate

- Public frontend, `/health`, and `/ready` are reachable.
- Two browser sessions cannot see each other's data.
- A visitor can send a message, receive streamed output, reload, and recover history.
- Retrying a request does not duplicate a message or LLM charge.
- Data survives API and database client restarts.
- Provider failures are controlled and the API stays healthy.
- No secret appears in source control, browser assets, API errors, or logs.
