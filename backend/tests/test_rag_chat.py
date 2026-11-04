from uuid import uuid4

from app.core.config import get_settings
from app.main import app
from app.rag.contracts import RetrievedEvidence, SourceLocation


class FakeRetrieval:
    def __init__(self, evidence):
        self.evidence = evidence

    async def search(self, _scope, _query, *, limit):
        assert limit == 5
        return self.evidence


class CitingProvider:
    model = "fake-citing"

    async def stream(self, prompt):
        assert "untrusted data" in prompt
        yield "The mission launched [1]."


def test_rag_chat_persists_citations_and_handles_missing_evidence(client, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "rag_chat_enabled", True)
    monkeypatch.setattr(settings, "rag_embedding_api_key", "test-key")
    client.post(
        "/api/v1/auth/register",
        json={"email": "rag-chat@example.com", "password": "a-long-test-password"},
    ).raise_for_status()
    csrf = client.get("/api/v1/auth/csrf").json()["csrf_token"]
    conversation_id = client.post(
        "/api/v1/conversations", json={}, headers={"X-CSRF-Token": csrf}
    ).json()["id"]
    evidence = RetrievedEvidence(
        document_id=uuid4(),
        document_version_id=uuid4(),
        chunk_id=uuid4(),
        title="Report",
        text="The mission launched.",
        location=SourceLocation(page=2),
    )
    app.state.rag_retrieval = FakeRetrieval([evidence])
    app.state.llm_provider = CitingProvider()
    try:
        with client.websocket_connect("/api/v1/ws/chat") as websocket:
            assert websocket.receive_json()["type"] == "connection.ready"
            websocket.send_json(
                {
                    "type": "chat.send",
                    "request_id": str(uuid4()),
                    "idempotency_key": str(uuid4()),
                    "conversation_id": conversation_id,
                    "content": "What happened?",
                }
            )
            started = websocket.receive_json()
            delta = websocket.receive_json()
            completed = websocket.receive_json()
            assert started["type"] == "message.started"
            assert delta["content"] == "The mission launched [1]."
            assert completed["type"] == "message.completed"
            message_id = completed["message_id"]
        citations = client.get(f"/api/v1/messages/{message_id}/citations").json()
        assert len(citations) == 1
        assert citations[0]["document_version_id"] == str(evidence.document_version_id)

        app.state.rag_retrieval = FakeRetrieval([])
        with client.websocket_connect("/api/v1/ws/chat") as websocket:
            websocket.receive_json()
            websocket.send_json(
                {
                    "type": "chat.send",
                    "request_id": str(uuid4()),
                    "idempotency_key": str(uuid4()),
                    "conversation_id": conversation_id,
                    "content": "Unknown question?",
                }
            )
            websocket.receive_json()
            assert "enough indexed evidence" in websocket.receive_json()["content"]
            completed = websocket.receive_json()
            assert client.get(f"/api/v1/messages/{completed['message_id']}/citations").json() == []
    finally:
        del app.state.rag_retrieval
