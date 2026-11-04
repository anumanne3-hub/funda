# Milestone 2 tracker — v0.2.0

Updated 2026-11-04. The application URL is https://funda-geni.vercel.app/.
The user has manually tested the deployed site and reports that it appears to
work. The exact flows covered by that check are not recorded, so the specific
Milestone 2 release gates below remain open.

## 2026-11-04 completion attempt

- Re-ran the local backend suite: 38 passed, 3 PostgreSQL-only tests skipped.
  Ruff check, Ruff format check, and mypy passed.
- The current GitHub commit is `d4014ef4d8677161f30b5d43557b4bfd709cd79c`.
  Its Vercel `funda-geni` status is successful; a separate Vercel `funda`
  status is failing. The available GitHub workflow lookup returned no PR runs
  for this commit, so final CI could not be confirmed.
- Hosted frontend/API requests from this workspace could not connect. Hosted
  account chat, regeneration, feedback, deletion, provider behavior, and
  cross-account isolation therefore remain unverified for the current build.
- Current local Help UI changes are uncommitted. With the repository's bundled
  Node v26.13.0 added to PATH, the frontend TypeScript and Vite production build
  passed on 2026-11-04.
- Frontend formatting and lint passed after the UI test updates. The local
  Chromium flows passed when run with installed Chrome; Playwright's Windows
  helper hangs during server cleanup, so a clean full-suite exit remains
  unconfirmed.
- Milestone 2 remains **acceptance pending**. Do not tag v0.2.0 until hosted
  verification, final CI, and the retention/deletion checks below pass.

## Implemented locally

- Argon2id password hashes, registration, login, current user, rotating account sessions,
  logout, logout-all, and revoked-token reuse detection on refresh.
- Secure HttpOnly account cookies and a separate CSRF token checked on account writes.
  The frontend obtains the CSRF token through an authenticated API call.
- User-owned projects and conversations, project assignment, rename and delete, and
  ownership checks on HTTP and WebSocket chat access.
- Explicit claim or discard of this browser's anonymous conversations. Registration
  does not silently move anonymous data into an account.
- Immutable message versions for edits and restored branches, feedback tied to an
  assistant version, and idempotent regeneration with a persisted pending state.
- Account deletion cascades through account sessions, projects, conversations, messages,
  versions, feedback, and regeneration records. Anonymous sessions not claimed by the
  account remain separate and expire under the existing anonymous-session policy.
- Repository-root Supabase SQL migrations add the account and version tables. The API
  readiness check includes the new tables and columns.

## Verification so far

- The deployed frontend returned HTTP 200 with the Funda title. The configured API
  returned `ready` with `database: ok`. Public smoke passed health, streaming,
  idempotent retry, and anonymous-session isolation against the hosted API.
- Hosted account, project, message-version, regeneration, and deletion flows have
  not yet been run end to end against disposable production accounts.
- Hosted disposable-account checks verified registration, CSRF, anonymous claim,
  project create/rename, conversation create/rename, and cross-account ownership.
  Account chat then returned `PROVIDER_UNAVAILABLE`; a second attempt lost its
  WebSocket connection before `connection.ready`. The first pair of test accounts
  was deleted. Cleanup of the second pair failed during a connection reset, so
  two accounts with the `funda-release-check-` email prefix may remain in the
  hosted database and need an administrator cleanup. Message versions, feedback,
  and regeneration remain unverified on the hosted service.

- Backend: 38 SQLite tests passed (three PostgreSQL-only tests skipped).
- Backend: 41 PostgreSQL tests passed on an empty disposable `funda_test_m2` database,
  including SQL migration/model compatibility, ownership and regeneration replay.
- Ruff, mypy, frontend formatting/lint/type/build checks passed.
- Python and npm dependency audits reported no known vulnerabilities. Source and built
  asset secret-pattern scans passed (79 source files and four built assets).
- Chromium: all five local browser tests passed with a clean exit, covering anonymous
  isolation/reload, mobile layout, account/project flow, message editing/restore,
  regeneration and feedback. The runner used manually started local servers to avoid
  a Windows helper-process cleanup hang when Playwright owns the servers.

## Remaining release gates

- Run hosted CI on the final commit and repeat public smoke after any deployment change.
- Apply the SQL migrations to a staging/production database before rolling out API code;
  verify hosted account and project isolation with two real accounts. No remote schema or
  deployment has been changed by this work.
- Review the account and message-version UI with the deployed provider, including
  regeneration failures, session expiry, and account deletion.
- Email verification and password reset are explicitly deferred. Until implemented,
  an account with a forgotten password cannot be recovered through the app.
- Confirm retention and deletion behavior against the hosted database and logs, then
  tag v0.2.0 only after the Milestone 2 acceptance gate passes.

## Data and retention decisions

- Emails and Argon2id password hashes live in Supabase PostgreSQL. Raw passwords never
  enter storage or logs. Account and CSRF tokens are stored only as SHA-256 hashes.
- The account cookie expires after the configured session TTL (30 days by default).
  Logout and logout-all revoke server-side sessions immediately.
- Deleting a project leaves its conversations unassigned. Deleting a conversation removes
  its messages, versions, feedback, and regeneration records. Deleting an account removes
  account-owned data through foreign-key cascades. Anonymous data is only moved by an
  explicit claim or removed by an explicit discard.
- Failed and interrupted regeneration keys never invoke the provider again. A new key is
  a new user-requested operation and consumes the applicable rate and budget limits.
