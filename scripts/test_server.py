"""Start a migrated, isolated mock backend for Playwright. Never reads a developer .env."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
python = root / "backend/.venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
if not python.exists():
    python = Path(sys.executable)

with tempfile.TemporaryDirectory(prefix="funda-e2e-") as directory:
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{Path(directory).as_posix()}/chat.db",
           "MIGRATION_DATABASE_URL": "", "LLM_PROVIDER": "mock", "APP_ENV": "development",
           "SESSION_COOKIE_SECURE": "false", "SESSION_COOKIE_SAMESITE": "lax",
           "FRONTEND_ORIGINS": "http://localhost:5173", "SESSIONS_PER_MINUTE": "1000"}
    subprocess.run([str(python), "-m", "alembic", "-c", str(root / "backend/alembic.ini"),
                    "upgrade", "head"], cwd=root / "backend", env=env, check=True)
    subprocess.run([str(python), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
                    "--port", "8000", "--ws-max-size", "65536"],
                   cwd=root / "backend", env=env, check=True)
