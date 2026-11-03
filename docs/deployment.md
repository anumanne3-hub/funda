# Milestone 1 deployment

Use the existing Supabase, Render and Vercel projects. Live deployment requires their project URLs,
connected accounts and backend secrets. Do not paste credentials into chat or commit `.env` files.

## Supabase

The source of truth is `supabase/migrations/*.sql` at the repository root, alongside
`supabase/config.toml`. These are native PostgreSQL SQL files, not Python migrations.

### GitHub deployment

In the Supabase GitHub integration, select this repository and its production branch.
Set the project working directory to the **repository root** (usually `/`), which contains
`supabase/config.toml`. Do not set it to `backend` or `backend/supabase`.
Enable the integration's production migration deployment option for the intended branch;
merely connecting GitHub is not enough. Preview/automatic branching is optional.
Check the Supabase GitHub deployment logs after pushing the SQL files.
See [GitHub integration](https://supabase.com/docs/guides/deployment/branching/github-integration).

### CLI alternative and local PostgreSQL

From the repository root, use `npx supabase@3.0.0 db push --remote=<POSTGRESQL_URI>`.
For a local Compose database, see the README. For hosted deployment, store the URI privately
and pass it from an environment variable rather than pasting passwords into command history:

```powershell
npx supabase@3.0.0 db push --remote=$env:MIGRATION_DATABASE_URL
```

The Supabase CLI URI must start with `postgresql://`; Render's SQLAlchemy `DATABASE_URL`
starts with `postgresql+psycopg://`. The CLI does not automatically load `backend/.env`.
Use a direct or **session-mode pooler** URI with `sslmode=require`; do not use the transaction
pooler for migrations. On IPv4 networks, choose Session pooler from Supabase's Connect panel.
The API defaults to a small connection pool with no overflow. No database secret belongs in Git.

### Existing databases previously migrated with Alembic

Do not reset a remote database or replay the initial SQL over existing application tables.
Back up the database and inspect its tables and `alembic_version` first. If it is empty,
apply both SQL migrations normally. If Alembic already created tables, compare the existing
schema with both SQL files before baselining history:

- If the initial schema exactly matches, mark only `20261103000000` applied with
  `npx supabase@3.0.0 migration repair 20261103000000 --status applied --remote=<POSTGRESQL_URI>`,
  then push the remaining migration.
- If both old revisions are already applied and match the SQL, first apply the five
  `ENABLE ROW LEVEL SECURITY` statements from the second SQL file (the old migrations did
  not include these), then mark both `20261103000000` and `20261103000100` applied.
- Do not mark a migration applied merely because an old version row exists. If the schema
  differs or is partial, reconcile it before repair. Keep the old history table until verified.

The SQL files intentionally fail on conflicting tables rather than silently skipping schema
checks. Neither conversion nor GitHub connection applies anything to a remote DB by itself.

## Render

With `APP_ENV=production`, code defaults allow `https://funda-geni.vercel.app` and
`https://funda-phi.vercel.app` and use secure cookies with `SameSite=none`.
Environment variables override these defaults: remove stale `FRONTEND_ORIGINS` or
cookie settings from Render to use the code defaults. Local development defaults to
`http://localhost:5173`, non-secure cookies and `SameSite=lax`; keep
`APP_ENV=development` in the local `.env`. Do not copy the local `.env` to Render.

The repository's `render.yaml` builds and starts the API and checks `/ready`.
It no longer runs migrations at API deployment time. Remove an existing Alembic pre-deploy
command in the Render dashboard. Apply Supabase migrations before deploying the API.

Set `APP_ENV=production`, `SESSION_COOKIE_SECURE=true`, exact `FRONTEND_ORIGINS`, and `DATABASE_URL`. Migration credentials are only needed where the Supabase CLI runs. For separate `vercel.app` / `onrender.com` domains use `SESSION_COOKIE_SAMESITE=none`.
Some browsers block third-party cookies; for reliable browser support use same-site custom
domains such as `chat.example.com` and `api.example.com`, with `SameSite=lax`.
Test the intended browser/domain combination before release. WebSockets connect directly to Render.

## Free Gemini model

Use a Google AI Studio project on the **Free Tier**. Do not enable billing or a paid fallback.
Configure these backend secrets/settings:

```dotenv
LLM_PROVIDER=gemini
LLM_MODEL=gemini-3.1-flash-lite
LLM_API_KEY=<set in the secret manager>
LLM_FREE_TIER=true
LLM_INPUT_USD_PER_MILLION=0
LLM_OUTPUT_USD_PER_MILLION=0
LLM_DAILY_REQUEST_LIMIT=100
LLM_MAX_OUTPUT_TOKENS=1000
REQUESTS_PER_MINUTE=5
```

The app cannot verify your Google billing tier: keep that project on the provider's Free Tier.
The daily count is shared across API instances and survives restarts. Provider quota failures
return controlled errors; there is no automatic model switch or paid retry. Adjust the daily
count to the quota shown for your account. The mock remains the default until the key is set.

Google lists free input/output for this model; free-tier content may be used to improve Google's
products. Use non-sensitive demo prompts. See [pricing](https://ai.google.dev/gemini-api/docs/pricing#gemini-3.1-flash-lite)
and [native streaming API](https://ai.google.dev/api/generate-content#method:-models.streamgeneratecontent).
The separate OpenAI-compatible adapter follows the [Chat Completions streaming contract](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create).

## Vercel

Set the project Root Directory to `frontend`; `vercel.json` contains the install/build settings.
Set `VITE_API_BASE_URL=https://YOUR_API_HOST/api/v1`, then build/deploy. Only public configuration
belongs in `VITE_*`. Never expose database credentials, service-role keys, or provider API keys.

## Release verification

1. Run all CI checks on the exact release commit.
2. Deploy migrations/API, check `/health` and `/ready`, then deploy the frontend.
3. Run the `Public smoke test` GitHub workflow with the frontend and API URLs. It creates demo
   conversations and makes a small number of model calls; keep within the free quota.
4. Confirm browser isolation, reload/reconnect recovery, and absence of secrets in assets/logs.
5. Restart the API; confirm existing conversation history remains. Verify database restart
   persistence in an isolated test environment; do not interrupt a shared Supabase project.
6. Tag `v0.1.0` only after all gates pass. An unverified release must remain untagged.

Rollback the API/frontend to the previous known-good commit while retaining additive migrations.
Never reset or drop tables in the production database. Keep a database backup before
schema changes. Public CI runs, hosted smoke tests and the real provider call must be recorded in
the tracker after they actually run.
