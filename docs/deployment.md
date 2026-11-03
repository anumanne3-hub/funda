# Milestone 1 deployment

Use the existing Supabase, Render and Vercel projects. Live deployment requires their project URLs,
connected accounts and backend secrets. Do not paste credentials into chat or commit `.env` files.

## Supabase

Use a PostgreSQL connection with TLS (`sslmode=require`). Store it only on the API host.
Use a session-mode pooler or direct connection for `MIGRATION_DATABASE_URL`; the migration process
must not use transaction-pooling mode. The API defaults to a small pool with no overflow.
Run `uv run --locked alembic upgrade head` once per release. Migration 0002 adds budget/limit
records and cost columns without changing existing chat data.

## Render

With `APP_ENV=production`, code defaults allow `https://funda-geni.vercel.app` and
`https://funda-phi.vercel.app` and use secure cookies with `SameSite=none`.
Environment variables override these defaults: remove stale `FRONTEND_ORIGINS` or
cookie settings from Render to use the code defaults. Local development defaults to
`http://localhost:5173`, non-secure cookies and `SameSite=lax`; keep
`APP_ENV=development` in the local `.env`. Do not copy the local `.env` to Render.

The repository's `render.yaml` defines the API, locked install, `/ready` health check and one
pre-deploy migration command. The template uses a Starter service for the pre-deploy step.
For an existing Free service, run the migration separately once before deploying; do not
change an existing service's billing plan just to apply this template.

Set `APP_ENV=production`, `SESSION_COOKIE_SECURE=true`, exact `FRONTEND_ORIGINS`, and both database
URLs. For separate `vercel.app` / `onrender.com` domains use `SESSION_COOKIE_SAMESITE=none`.
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
Never run the destructive Alembic downgrade on production chat data. Keep a database backup before
schema changes. Public CI runs, hosted smoke tests and the real provider call must be recorded in
the tracker after they actually run.
