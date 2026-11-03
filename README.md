# GenAI Chatbot

Milestone 1 implements anonymous, isolated, persistent streaming chat with React, FastAPI,
PostgreSQL and a mock / Gemini / OpenAI-compatible provider. See [status](MILESTONE_1_TRACKER.md),
[architecture and API](docs/architecture.md), and [deployment](docs/deployment.md).

## Local setup

Prerequisites: Python 3.13, Node.js 26, npm, and PostgreSQL 18 (or Docker Compose).
The development SQLite fallback is useful for a quick demo; production requires PostgreSQL.

From the repository root:

```powershell
docker compose up -d
cd backend
python -m pip install uv==0.13.6
uv sync --locked --extra dev
Copy-Item .env.example .env
uv run --locked alembic upgrade head
uv run --locked uvicorn app.main:app --reload --ws-max-size 65536
```

In another terminal:

```powershell
cd frontend
npm ci
npm run dev
```

Open http://localhost:5173. The default mock costs nothing. For a free hosted Gemini model,
follow [the backend-only settings](docs/deployment.md#free-gemini-model). Do not enable provider
billing or add secrets to frontend settings. `LLM_PROVIDER=gemini` requires a real API key;
it is not enabled automatically by the test setup.

For a SQLite-only demo, set `DATABASE_URL=sqlite:///./genai_chatbot.db` in `backend/.env`,
then run the same migrations and API commands. Never use this fallback for deployment.

## Verification

```powershell
cd backend
uv run --locked ruff format --check app tests migrations
uv run --locked ruff check app tests migrations
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
CI runs both SQLite and PostgreSQL suites and a clean migration upgrade/downgrade/upgrade cycle.

For process restart verification, use a separate disposable `funda_test_*` database and run:

```powershell
cd backend
$env:TEST_DATABASE_URL = 'postgresql+psycopg://USER:PASSWORD@HOST:PORT/funda_test_restart'
uv run --locked python ../scripts/verify_restart.py
```

That script starts a mock API on port 18080, persists a chat, restarts the API and verifies
history and idempotent replay. `RESTART_WORKSPACE_POSTGRES=1` additionally restarts only the
portable database at `.tools/pgdata`; it is for this Windows workspace, not a shared hosted DB.

## Render commands

Root Directory: `backend`

- Build: `pip install uv==0.13.6 && uv sync --locked`
- Start: `uv run --locked uvicorn app.main:app --host 0.0.0.0 --port $PORT --ws-max-size 65536`
- Pre-deploy: `uv run --locked alembic upgrade head`
- Health check: `/ready`

See the deployment guide for free-plan migration handling, Supabase connections, production
cookies/CORS, Vercel configuration and the automated public smoke workflow. Release `v0.1.0`
remains gated on real-provider, hosted CI and public deployment verification.
