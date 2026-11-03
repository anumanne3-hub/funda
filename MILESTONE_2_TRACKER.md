# Milestone 2 tracker — v0.2.0

Updated 2026-11-03. Local implementation is in progress; v0.2.0 is not released or deployed.

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

- Run hosted CI and public smoke on the final commit.
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
