"""Run an isolated migrated mock API for browser tests."""

import os
from pathlib import Path
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
(root / ".tools").mkdir(exist_ok=True)
sys.path.insert(0, str(root / "backend"))
os.chdir(root / "backend")

with tempfile.TemporaryDirectory(prefix="e2e-", dir=root / ".tools") as directory:
    os.environ.update({
        "DATABASE_URL": f"sqlite:///{Path(directory).as_posix()}/chat.db",
        "MIGRATION_DATABASE_URL": "", "LLM_PROVIDER": "mock", "APP_ENV": "development",
        "SESSION_COOKIE_SECURE": "false", "SESSION_COOKIE_SAMESITE": "lax",
        "FRONTEND_ORIGINS": "http://localhost:5173", "SESSIONS_PER_MINUTE": "1000",
    })
    from alembic import command
    from alembic.config import Config
    import uvicorn

    command.upgrade(Config("alembic.ini"), "head")
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, ws_max_size=65536)
