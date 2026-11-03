"""Public health, ownership, streaming and retry smoke test. Uses a fresh anonymous session."""

import json
import os
from uuid import uuid4

import httpx
from websockets.sync.client import connect

base = os.environ["SMOKE_API_URL"].rstrip("/")
origin = os.environ["SMOKE_BASE_URL"].rstrip("/")
require_real_provider = os.environ.get("SMOKE_REQUIRE_REAL_PROVIDER", "false").lower() == "true"
headers = {"Origin": origin}
with httpx.Client(base_url=base, headers=headers, timeout=60) as client:
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/ready").json()["status"] == "ready"
    session = client.post("/api/v1/anonymous-session")
    session.raise_for_status()
    response = client.post("/api/v1/conversations", json={"title": "Release smoke test"})
    response.raise_for_status()
    conversation = response.json()["id"]
    key = str(uuid4())
    event = {"type": "chat.send", "request_id": key, "idempotency_key": key,
             "conversation_id": conversation, "content": "Reply with a short greeting."}
    cookie = "; ".join(f"{name}={value}" for name, value in client.cookies.items())
    for _ in range(2):
        with connect(base.replace("https://", "wss://").replace("http://", "ws://")
                     + "/api/v1/ws/chat", origin=origin, additional_headers={"Cookie": cookie}) as ws:
            assert json.loads(ws.recv(timeout=60))["type"] == "connection.ready"
            ws.send(json.dumps(event))
            while True:
                result = json.loads(ws.recv(timeout=60))
                if result["type"] in {"message.completed", "error"}:
                    assert result["type"] == "message.completed", result.get("code")
                    break
    messages = client.get(f"/api/v1/conversations/{conversation}").json()["messages"]
    assert len(messages) == 2
    if require_real_provider:
        assert not messages[-1]["content"].startswith("Mock assistant:"), (
            "Release verification requires a real provider; the deployment still uses mock"
        )
    with httpx.Client(base_url=base, headers=headers) as other:
        other.post("/api/v1/anonymous-session").raise_for_status()
        assert other.get(f"/api/v1/conversations/{conversation}").status_code == 404
        assert not other.get("/api/v1/conversations").json()["items"]
print("Public health, streaming, retry and isolation smoke checks passed.")
