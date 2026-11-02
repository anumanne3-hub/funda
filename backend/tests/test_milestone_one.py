from collections.abc import AsyncIterator
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.providers import ProviderError


def create_session_and_conversation(client: TestClient) -> str:
    session_response = client.post("/api/v1/anonymous-session")
    assert session_response.status_code == 200
    conversation_response = client.post("/api/v1/conversations", json={"title": "Test chat"})
    assert conversation_response.status_code == 201
    return conversation_response.json()["id"]


def send_chat(client: TestClient, conversation_id: str, idempotency_key: str) -> list[dict]:
    events: list[dict] = []
    with client.websocket_connect("/api/v1/ws/chat") as socket:
        assert socket.receive_json()["type"] == "connection.ready"
        socket.send_json(
            {
                "type": "chat.send",
                "request_id": str(uuid4()),
                "conversation_id": conversation_id,
                "idempotency_key": idempotency_key,
                "content": "Hello persistence",
            }
        )
        while True:
            event = socket.receive_json()
            events.append(event)
            if event["type"] in {"message.completed", "error"}:
                break
    return events


def test_health_and_readiness(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok"}


def test_session_required_for_private_routes(client: TestClient) -> None:
    assert client.get("/api/v1/conversations").status_code == 401


def test_conversation_isolated_between_sessions(client: TestClient) -> None:
    conversation_id = create_session_and_conversation(client)
    first_cookie = client.cookies.get("genai_session")
    client.cookies.clear()
    create_session_and_conversation(client)
    assert client.get(f"/api/v1/conversations/{conversation_id}").status_code == 404
    client.cookies.set("genai_session", first_cookie)
    assert client.get(f"/api/v1/conversations/{conversation_id}").status_code == 200


def test_websocket_persists_and_replays_idempotently(client: TestClient) -> None:
    conversation_id = create_session_and_conversation(client)
    first = send_chat(client, conversation_id, "idem-key-0001")
    second = send_chat(client, conversation_id, "idem-key-0001")
    assert any(event["type"] == "message.delta" for event in first)
    assert any(event["type"] == "message.completed" for event in second)

    detail = client.get(f"/api/v1/conversations/{conversation_id}")
    assert detail.status_code == 200
    messages = detail.json()["messages"]
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"
    assert messages[1]["status"] == "completed"
    assert "Hello persistence" in messages[1]["content"]


class FailingProvider:
    model = "failing-test"

    async def stream(self, content: str) -> AsyncIterator[str]:
        if False:
            yield content
        raise ProviderError("PROVIDER_TIMEOUT", True)


def test_provider_failure_is_persisted(client: TestClient) -> None:
    conversation_id = create_session_and_conversation(client)
    app.state.llm_provider = FailingProvider()
    events = send_chat(client, conversation_id, "idem-key-failure")
    assert events[-1]["type"] == "error"
    assert events[-1]["code"] == "PROVIDER_TIMEOUT"
    assert events[-1]["retryable"] is False
    messages = client.get(f"/api/v1/conversations/{conversation_id}").json()["messages"]
    assert messages[-1]["status"] == "failed"
    assert messages[-1]["error_code"] == "PROVIDER_TIMEOUT"
