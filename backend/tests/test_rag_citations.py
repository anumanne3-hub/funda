import time
from uuid import UUID, uuid4

from app.main import app
from app.rag.contracts import RetrievedEvidence, SourceLocation
from app.services.chat import complete_chat, prepare_chat


def test_citations_persist_with_assistant_version_and_are_owner_scoped(client):
    client.post(
        "/api/v1/auth/register",
        json={"email": "citation@example.com", "password": "a-long-test-password"},
    ).raise_for_status()
    owner_id = UUID(client.get("/api/v1/auth/me").json()["id"])
    headers = {"X-CSRF-Token": client.get("/api/v1/auth/csrf").json()["csrf_token"]}
    conversation_id = UUID(
        client.post("/api/v1/conversations", json={}, headers=headers).json()["id"]
    )
    with app.state.session_factory() as db:
        prepared = prepare_chat(
            db,
            owner_id,
            conversation_id,
            str(uuid4()),
            "What happened?",
            "mock-stream-v1",
            owner_field="user_id",
        )
        assistant_id = prepared.assistant.id
        evidence = RetrievedEvidence(
            document_id=uuid4(),
            document_version_id=uuid4(),
            chunk_id=uuid4(),
            title="Report",
            text="The mission launched.",
            location=SourceLocation(page=2, section="Launch"),
            source_url="https://example.com/report",
        )
        uncited = RetrievedEvidence(
            document_id=uuid4(),
            document_version_id=uuid4(),
            chunk_id=uuid4(),
            title="Uncited report",
            text="Unrelated details.",
            location=SourceLocation(page=1),
        )
        complete_chat(
            db,
            prepared.request.id,
            assistant_id,
            "The mission launched [2].",
            time.perf_counter(),
            evidence=[uncited, evidence],
            cited_ordinals=[2],
        )
    citations = client.get(f"/api/v1/messages/{assistant_id}/citations")
    assert citations.status_code == 200
    assert citations.json()[0]["document_version_id"] == str(evidence.document_version_id)
    assert len(citations.json()) == 1
    assert citations.json()[0]["ordinal"] == 2
    assert citations.json()[0]["page"] == 2
    assert citations.json()[0]["section"] == "Launch"
    assert client.get(f"/api/v1/messages/{assistant_id}/citations").json() == citations.json()

    client.post("/api/v1/auth/logout", headers=headers).raise_for_status()
    client.post(
        "/api/v1/auth/register",
        json={"email": "other-citation@example.com", "password": "a-long-test-password"},
    ).raise_for_status()
    assert client.get(f"/api/v1/messages/{assistant_id}/citations").status_code == 404
