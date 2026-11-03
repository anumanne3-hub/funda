import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, update
from starlette.websockets import WebSocketDisconnect
from test_milestone_one import create_session_and_conversation, send_chat

from app.core.config import Settings, get_settings
from app.main import app
from app.models import ChatRequest, Conversation, Message
from app.services.chat import prepare_chat
from app.services.limits import RequestRejected, consume


def test_pagination_with_equal_timestamps(client):
    first = create_session_and_conversation(client)
    ids = {first}
    for i in range(4):
        ids.add(client.post("/api/v1/conversations", json={"title": str(i)}).json()["id"])
    with app.state.session_factory() as db:
        db.execute(update(Conversation).values(updated_at=datetime(2026, 1, 1, tzinfo=UTC)))
        db.commit()
    seen = []
    cursor = None
    while True:
        page = client.get(
            "/api/v1/conversations", params={"limit": 2, **({"cursor": cursor} if cursor else {})}
        ).json()
        seen.extend(item["id"] for item in page["items"])
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert len(seen) == len(ids) and set(seen) == ids


def test_websocket_ownership_and_origin(client):
    conversation = create_session_and_conversation(client)
    client.cookies.clear()
    create_session_and_conversation(client)
    assert send_chat(client, conversation, "other-session")[0]["code"] == "CONVERSATION_NOT_FOUND"
    assert client.get("/api/v1/conversations").json()["items"][0]["id"] != conversation
    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect("/api/v1/ws/chat", headers={"origin": "https://evil.invalid"}),
    ):
        pass
    assert (
        client.post(
            "/api/v1/anonymous-session", headers={"origin": "https://evil.invalid"}
        ).status_code
        == 403
    )


def test_invalid_json_does_not_kill_socket(client):
    create_session_and_conversation(client)
    with client.websocket_connect("/api/v1/ws/chat") as ws:
        ws.receive_json()
        for payload in ("{", "{}", '{"type":"unknown"}'):
            ws.send_text(payload)
            assert ws.receive_json()["code"] == "INVALID_CHAT_EVENT"
    assert client.get("/health").status_code == 200
    assert client.post("/api/v1/conversations", json={"title": "  "}).status_code == 422


def test_idempotency_conflict_and_single_provider_call(client):
    conversation = create_session_and_conversation(client)

    class CountingProvider:
        model = "counting"
        calls = 0

        async def stream(self, content):
            self.calls += 1
            yield content

    provider = CountingProvider()
    app.state.llm_provider = provider
    send_chat(client, conversation, "same-key-123")
    send_chat(client, conversation, "same-key-123")
    assert provider.calls == 1
    with client.websocket_connect("/api/v1/ws/chat") as ws:
        ws.receive_json()
        ws.send_json(
            {
                "type": "chat.send",
                "request_id": str(uuid4()),
                "conversation_id": conversation,
                "idempotency_key": "same-key-123",
                "content": "different content",
            }
        )
        assert ws.receive_json()["code"] == "IDEMPOTENCY_CONFLICT"


def test_stale_pending_is_not_called_again(client):
    conversation = UUID(create_session_and_conversation(client))
    with app.state.session_factory() as db:
        owner = db.get(Conversation, conversation).anonymous_session_id
        prepared = prepare_chat(
            db, owner, conversation, "stale-request", "Hello persistence", "mock"
        )
        prepared.request.created_at = datetime.now(UTC) - timedelta(minutes=5)
        db.commit()
    events = send_chat(client, str(conversation), "stale-request")
    assert events[-1]["code"] == "REQUEST_INTERRUPTED"
    assert len(client.get(f"/api/v1/conversations/{conversation}").json()["messages"]) == 2


def test_timeout_is_bounded_and_persisted(client, monkeypatch):
    conversation = create_session_and_conversation(client)
    monkeypatch.setattr(get_settings(), "llm_timeout_seconds", 0.01)

    class SlowProvider:
        model = "slow"

        async def stream(self, content):
            await asyncio.sleep(1)
            yield content

    app.state.llm_provider = SlowProvider()
    assert send_chat(client, conversation, "slow-request")[-1]["code"] == "PROVIDER_TIMEOUT"
    assert (
        client.get(f"/api/v1/conversations/{conversation}").json()["messages"][-1]["status"]
        == "failed"
    )
    assert client.get("/ready").status_code == 200


def test_rate_limit_and_budget_are_durable(client, monkeypatch):
    conversation = create_session_and_conversation(client)
    monkeypatch.setattr(get_settings(), "requests_per_minute", 1)
    send_chat(client, conversation, "first-request")
    assert send_chat(client, conversation, "second-request")[-1]["code"] == "RATE_LIMITED"
    assert send_chat(client, conversation, "first-request")[-1]["type"] == "message.completed"
    with app.state.session_factory() as db:
        consume(db, "budget", 5, 6, 86400)
        db.commit()
    with app.state.session_factory() as db, pytest.raises(RequestRejected, match="BUDGET_EXCEEDED"):
        consume(db, "budget", 2, 6, 86400)


def test_concurrent_duplicate_requests(client):
    factory = app.state.session_factory
    if factory.kw["bind"].dialect.name != "postgresql":
        pytest.skip("Row-lock concurrency requires PostgreSQL")
    conversation = UUID(create_session_and_conversation(client))
    with factory() as db:
        owner = db.get(Conversation, conversation).anonymous_session_id

    def prepare(_):
        with factory() as db:
            return prepare_chat(db, owner, conversation, "concurrent-key", "same", "mock").replay

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(prepare, range(4)))
    assert results.count(False) == 1
    with factory() as db:
        assert len(list(db.scalars(select(ChatRequest)))) == 1
        assert len(list(db.scalars(select(Message)))) == 2


def test_configuration_rejects_unsafe_production():
    with pytest.raises(ValueError):
        Settings(app_env="production", _env_file=None)
    with pytest.raises(ValueError):
        Settings(session_cookie_samesite="none", _env_file=None)


def test_errors_do_not_echo_inputs(client):
    create_session_and_conversation(client)
    response = client.post("/api/v1/conversations", json={"title": {"secret": "private-value"}})
    assert response.status_code == 422
    assert "private-value" not in response.text
    assert response.json()["request_id"] == response.headers["X-Request-ID"]


def test_cors_preflight_and_session_response(client):
    origin = get_settings().frontend_origins[0]
    preflight = client.options(
        "/api/v1/anonymous-session",
        headers={
            "origin": origin,
            "access-control-request-method": "POST",
            "access-control-request-headers": "content-type",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == origin
    response = client.post("/api/v1/anonymous-session", headers={"origin": origin})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert response.headers["access-control-allow-credentials"] == "true"


def test_cors_headers_on_middleware_error(client, monkeypatch):
    def unavailable_db():
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(app.state, "session_factory", unavailable_db)
    origin = get_settings().frontend_origins[0]
    response = client.post("/api/v1/anonymous-session", headers={"origin": origin})
    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"
    assert response.headers["access-control-allow-origin"] == origin
    assert response.headers["access-control-allow-credentials"] == "true"
