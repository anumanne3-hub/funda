"""Verify committed chat survives API restart and optionally the workspace test DB restart."""

import json
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

import httpx
from websockets.sync.client import connect

root = Path(__file__).resolve().parents[1]
url = os.environ["TEST_DATABASE_URL"]
if "funda_test_" not in url.rsplit("/", 1)[-1]:
    raise SystemExit("Use a dedicated funda_test_* database")
env = {**os.environ, "DATABASE_URL": url, "MIGRATION_DATABASE_URL": url,
       "LLM_PROVIDER": "mock", "APP_ENV": "development", "SESSION_COOKIE_SECURE": "false",
       "SESSION_COOKIE_SAMESITE": "lax"}
subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
               cwd=root / "backend", env=env, check=True)
log = (root / ".tools/restart-api.log").open("w", encoding="utf-8")


def start():
    process = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", "18080"],
        cwd=root / "backend", env=env, stdout=log, stderr=log,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    for _ in range(100):
        if process.poll() is not None:
            raise RuntimeError("API failed to start; inspect .tools/restart-api.log")
        try:
            if httpx.get("http://127.0.0.1:18080/ready").status_code == 200:
                return process
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    process.terminate()
    process.wait(timeout=10)
    raise RuntimeError("API startup timeout")


process = start()
try:
    with httpx.Client(base_url="http://127.0.0.1:18080") as client:
        client.post("/api/v1/anonymous-session").raise_for_status()
        response = client.post("/api/v1/conversations", json={"title": "Restart verification"})
        response.raise_for_status()
        conversation = response.json()["id"]
        key = str(uuid4())
        event = {"type": "chat.send", "request_id": key, "idempotency_key": key,
                 "conversation_id": conversation, "content": "Persist through restart"}
        cookie = "; ".join(f"{k}={v}" for k, v in client.cookies.items())
        def send():
            with connect("ws://127.0.0.1:18080/api/v1/ws/chat",
                         additional_headers={"Cookie": cookie}) as ws:
                ws.recv(timeout=30)
                ws.send(json.dumps(event))
                while True:
                    result = json.loads(ws.recv(timeout=30))
                    if result["type"] in {"message.completed", "error"}:
                        assert result["type"] == "message.completed"
                        break
        send()
        path = f"/api/v1/conversations/{conversation}"
        before = client.get(path).json()["messages"]
        process.terminate()
        process.wait(timeout=15)
        if os.environ.get("RESTART_WORKSPACE_POSTGRES") == "1":
            data = (root / ".tools/pgdata").resolve()
            assert data.is_relative_to(root.resolve())
            subprocess.run([str(root / ".tools/pgsql/bin/pg_ctl.exe"), "-D", str(data),
                            "-l", str(root / ".tools/postgres.log"), "-w", "restart"],
                           cwd=root, check=True)
        process = start()
        assert client.get(path).json()["messages"] == before
        send()
        assert client.get(path).json()["messages"] == before
        assert len(before) == 2
        print("API/database restart preserves chat; retry creates no duplicate turn.")
finally:
    process.terminate()
    process.wait(timeout=15)
    log.close()
