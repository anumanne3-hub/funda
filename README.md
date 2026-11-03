# GenAI Chatbot

Milestone 1 implements anonymous, isolated, persistent streaming chat with React, FastAPI,
PostgreSQL and a mock / Gemini / OpenAI-compatible provider. See [status](MILESTONE_1_TRACKER.md),
[architecture and API](docs/architecture.md), and [deployment](docs/deployment.md).

## Local setup

Prerequisites: Python 3.13, Node.js 26, npm, and PostgreSQL 18 (or Docker Compose).
The commands below use Supabase CLI 3.0.0 via `npx`.
The development SQLite fallback is useful for a quick demo; production requires PostgreSQL.

From the repository root:

```powershell
docker compose up -d
cd backend
python -m pip install uv==0.13.6
uv sync --locked --extra dev
if (!(Test-Path .env)) { Copy-Item .env.example .env }
cd ..
npx supabase@3.0.0 db push --remote="postgresql://genai:genai@localhost:5432/genai_chatbot?sslmode=disable"
cd backend
uv run --locked uvicorn app.main:app --reload --ws-max-size 65536
```

In another terminal, from the repository root:

```powershell
cd frontend
# If Node is not on PATH, use the existing workspace installation:
# $env:Path = "D:\My\1a_funda\funda\.tools\node-v26.13.0-win-x64;$env:Path"
npm.cmd ci
npm.cmd run dev
```

Open http://localhost:5173. The default mock costs nothing. For a free hosted Gemini model,
follow [the backend-only settings](docs/deployment.md#free-gemini-model). Do not enable provider
billing or add secrets to frontend settings. `LLM_PROVIDER=gemini` requires a real API key;
it is not enabled automatically by the test setup.

For a SQLite-only demo, set `DATABASE_URL=sqlite:///./genai_chatbot.db` in `backend/.env`,
run `uv run --locked python -m app.db.init_local` from `backend`, then start the API.
SQLite is a demo initialized from ORM metadata, not a SQL migration test. Never use it for deployment.

## Verification

```powershell
cd backend
uv run --locked ruff format --check app tests
uv run --locked ruff check app tests
uv run --locked mypy app
uv run --locked pytest -q
uv run --locked pip-audit --local --skip-editable
cd ../frontend
npm run format:check
npm run lint
npm run build
npx playwright install chromium
npm test
npm audit
cd ..
python scripts/scan_secrets.py
python scripts/scan_secrets.py --assets frontend/dist
```

Browser tests start their own isolated mock API and Vite server on ports 8000/5173; stop
local development servers first. On Windows, allow the test runner to close its helper
processes. In a restricted workspace use a fresh `--basetemp ../.tools/pytest-UNIQUE` directory.

For PostgreSQL integration tests create an **empty disposable** database whose name begins
`funda_test_`, set `TEST_DATABASE_URL`, and run pytest. These tests create/drop their test tables;
never point them at a development or production database. The concurrency test runs only on PostgreSQL.
CI runs both SQLite and PostgreSQL suites, applies the SQL migrations to a disposable database,
and checks schema compatibility and data preservation.

For process restart verification, use a separate disposable `funda_test_*` database and run:

```powershell
cd backend
$env:TEST_DATABASE_URL = 'postgresql+psycopg://USER:PASSWORD@HOST:PORT/funda_test_restart'
uv run --locked python ../scripts/verify_restart.py
```

That script starts a mock API on port 18080, persists a chat, restarts the API and verifies
history and idempotent replay. `RESTART_WORKSPACE_POSTGRES=1` additionally restarts only the
portable database at `.tools/pgdata`; it is for this Windows workspace, not a shared hosted DB.

## Supabase production migrations

PostgreSQL schema changes are versioned SQL files in `supabase/migrations/`.
The Supabase project configuration is `supabase/config.toml`; Alembic is no longer used.

In the Supabase GitHub integration, select the repository and production branch and set
the project working directory to the **repository root**, containing `supabase/`.
Enable production migration deployment and inspect the deployment logs after pushing.
Do not point the integration at `backend` or the old `backend/supabase` folder.

If application tables already exist remotely, follow the existing-database instructions
in [the deployment guide](docs/deployment.md#existing-databases-previously-migrated-with-alembic)
before applying these initial SQL migrations. Do not reset the production database.

For a manual deployment from the repository root, Supabase CLI 3 uses:

```powershell
npx supabase@3.0.0 db push --remote=$env:MIGRATION_DATABASE_URL
```

Set that shell variable privately to the Supabase session-pooler URI, beginning with
`postgresql://` and using `sslmode=require`. The CLI does not automatically load
`backend/.env`. Never commit the password or put it in frontend configuration.

## Render commands

Root Directory: `backend`

Build and start commands are unchanged. Supabase now deploys migrations separately;
remove any old Alembic command from the existing Render service's Pre-Deploy field.

- Build: `pip install uv==0.13.6 && uv sync --locked`
- Start: `uv run --locked uvicorn app.main:app --host 0.0.0.0 --port $PORT --ws-max-size 65536`
- Pre-deploy: leave blank; Supabase deploys SQL migrations separately before the API rollout.
- Health check: `/ready`

Configure these values in Render's Environment settings:

| Key | Value |
| --- | --- |
| `APP_ENV` | `production` |
| `DATABASE_URL` | Supabase session-pooler URI with `postgresql+psycopg://` and `sslmode=require` |
| `FRONTEND_ORIGINS` | `https://funda-geni.vercel.app` |
| `SESSION_COOKIE_SECURE` | `true` |
| `SESSION_COOKIE_SAMESITE` | `none` |
| `LLM_PROVIDER` | `mock` until real-provider settings are configured |

The API only needs `DATABASE_URL`; `MIGRATION_DATABASE_URL` is for the shell running the
Supabase CLI. Local `backend/.env` settings do not configure Render.

Apply database migrations before rolling out the API. Check `/health` for process liveness
and `/ready` for database/schema readiness. Both should return HTTP 200.

## Vercel configuration

Use Root Directory `frontend` and set this public build-time variable, then redeploy:

```dotenv
VITE_API_BASE_URL=https://funda-g0wg.onrender.com/api/v1
```

The current frontend origin is `https://funda-geni.vercel.app`. If it changes, update
Render's `FRONTEND_ORIGINS` to the exact new origin without a trailing slash.

See the deployment guide for Supabase GitHub migration setup, database connections, production
cookies/CORS, Vercel configuration and the automated public smoke workflow. Release `v0.1.0`
remains gated on real-provider, hosted CI and public deployment verification.
