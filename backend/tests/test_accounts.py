def test_accounts_projects_and_ownership(client):
    client.post("/api/v1/anonymous-session").raise_for_status()
    anonymous = client.post("/api/v1/conversations", json={"title": "Before signup"})
    anonymous.raise_for_status()
    anonymous_id = anonymous.json()["id"]
    registration = client.post(
        "/api/v1/auth/register",
        json={"email": " Alice@Example.com ", "password": "a-long-test-password"},
    )
    assert registration.status_code == 201
    assert registration.json()["email"] == "alice@example.com"
    csrf = client.get("/api/v1/auth/csrf").json()["csrf_token"]
    headers = {"X-CSRF-Token": csrf}
    assert client.get(f"/api/v1/conversations/{anonymous_id}").status_code == 404
    assert client.post("/api/v1/auth/claim-anonymous").status_code == 403
    assert client.post("/api/v1/auth/claim-anonymous", headers=headers).json() == {"claimed": 1}
    project = client.post("/api/v1/projects", json={"name": "Work"}, headers=headers)
    assert project.status_code == 201
    project_id = project.json()["id"]
    conversation = client.post(
        "/api/v1/conversations",
        json={"title": "Project chat", "project_id": project_id},
        headers=headers,
    )
    assert conversation.status_code == 201
    assert conversation.json()["project_id"] == project_id
    assert [
        item["id"]
        for item in client.get(f"/api/v1/conversations?project_id={project_id}").json()["items"]
    ] == [conversation.json()["id"]]
    assert (
        client.patch(
            f"/api/v1/conversations/{conversation.json()['id']}",
            json={"title": "Renamed"},
            headers=headers,
        ).json()["title"]
        == "Renamed"
    )
    assert (
        client.delete(
            f"/api/v1/conversations/{conversation.json()['id']}", headers=headers
        ).status_code
        == 204
    )
    assert client.get(f"/api/v1/conversations/{conversation.json()['id']}").status_code == 404
    assert client.delete(f"/api/v1/projects/{project_id}", headers=headers).status_code == 204
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 204
    assert client.get("/api/v1/projects").status_code == 401


def test_account_isolation_and_revocation(client):
    from uuid import uuid4

    def register(email):
        client.post(
            "/api/v1/auth/register", json={"email": email, "password": "a-long-test-password"}
        ).raise_for_status()
        csrf = client.get("/api/v1/auth/csrf").json()["csrf_token"]
        return {"X-CSRF-Token": csrf}

    alice_headers = register("alice@example.com")
    project = client.post(
        "/api/v1/projects", json={"name": "Private"}, headers=alice_headers
    ).json()["id"]
    conversation = client.post(
        "/api/v1/conversations", json={"project_id": project}, headers=alice_headers
    ).json()["id"]
    client.post("/api/v1/auth/logout", headers=alice_headers).raise_for_status()
    bob_headers = register("bob@example.com")
    assert client.get(f"/api/v1/conversations/{conversation}").status_code == 404
    assert (
        client.patch(
            f"/api/v1/conversations/{conversation}", json={"title": "Mine"}, headers=bob_headers
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/v1/conversations", json={"project_id": project}, headers=bob_headers
        ).status_code
        == 404
    )
    assert client.get("/api/v1/projects").json() == []
    assert client.get(f"/api/v1/conversations?project_id={project}").status_code == 404
    key = str(uuid4())
    with client.websocket_connect("/api/v1/ws/chat") as websocket:
        assert websocket.receive_json()["type"] == "connection.ready"
        websocket.send_json(
            {
                "type": "chat.send",
                "request_id": key,
                "idempotency_key": key,
                "conversation_id": conversation,
                "content": "Cross-account attempt",
            }
        )
        result = websocket.receive_json()
        assert result["type"] == "error"
        assert result["code"] == "CONVERSATION_NOT_FOUND"


def test_refresh_logout_all_and_account_deletion(client):
    client.post(
        "/api/v1/auth/register",
        json={"email": "user@example.com", "password": "a-long-test-password"},
    ).raise_for_status()
    csrf = client.get("/api/v1/auth/csrf").json()["csrf_token"]
    old_cookie = client.cookies.get("genai_account")
    refreshed = client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": csrf})
    assert refreshed.status_code == 200
    assert client.cookies.get("genai_account") != old_cookie
    csrf = client.get("/api/v1/auth/csrf").json()["csrf_token"]
    assert client.post("/api/v1/auth/logout-all", headers={"X-CSRF-Token": csrf}).status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401
    client.post(
        "/api/v1/auth/login",
        json={"email": "user@example.com", "password": "a-long-test-password"},
    ).raise_for_status()
    csrf = client.get("/api/v1/auth/csrf").json()["csrf_token"]
    assert client.delete("/api/v1/auth/account", headers={"X-CSRF-Token": csrf}).status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401


def test_message_versions_and_feedback(client):
    from uuid import UUID

    from app.main import app
    from app.models import ChatRequest, Message, MessageVersion

    client.post(
        "/api/v1/auth/register",
        json={"email": "editor@example.com", "password": "a-long-test-password"},
    ).raise_for_status()
    csrf = client.get("/api/v1/auth/csrf").json()["csrf_token"]
    headers = {"X-CSRF-Token": csrf}
    conversation = UUID(client.post("/api/v1/conversations", json={}, headers=headers).json()["id"])
    with app.state.session_factory() as db:
        user_message = Message(
            conversation_id=conversation,
            sequence_number=1,
            role="user",
            content="First",
            status="completed",
        )
        assistant = Message(
            conversation_id=conversation,
            sequence_number=2,
            role="assistant",
            content="Answer",
            status="completed",
        )
        db.add_all([user_message, assistant])
        db.flush()
        db.add(
            ChatRequest(
                conversation_id=conversation,
                user_message_id=user_message.id,
                assistant_message_id=assistant.id,
                idempotency_key="initial",
                status="completed",
                model="mock-stream-v1",
            )
        )
        db.add_all(
            [
                MessageVersion(message_id=user_message.id, version_number=1, content="First"),
                MessageVersion(message_id=assistant.id, version_number=1, content="Answer"),
            ]
        )
        db.commit()
        user_id, assistant_id = user_message.id, assistant.id
    first = client.get(f"/api/v1/messages/{user_id}/versions").json()[0]
    edited = client.patch(
        f"/api/v1/messages/{user_id}", json={"content": "Revised"}, headers=headers
    )
    assert edited.status_code == 200
    assert edited.json()["parent_version_id"] == first["id"]
    restored = client.post(f"/api/v1/messages/{user_id}/activate/{first['id']}", headers=headers)
    assert restored.json()["content"] == "First"
    versions = client.get(f"/api/v1/messages/{user_id}/versions").json()
    assert len(versions) == 3
    assert (
        client.get(f"/api/v1/conversations/{conversation}").json()["messages"][0]["content"]
        == "First"
    )
    assistant_version = client.get(f"/api/v1/messages/{assistant_id}/versions").json()[0]
    feedback = client.post(
        f"/api/v1/messages/{assistant_id}/feedback",
        json={"version_id": assistant_version["id"], "rating": 1},
        headers=headers,
    )
    assert feedback.status_code == 204
    from uuid import uuid4

    key = str(uuid4())
    regenerated = client.post(
        f"/api/v1/messages/{assistant_id}/regenerate",
        json={"idempotency_key": key},
        headers=headers,
    )
    assert regenerated.status_code == 200, regenerated.text
    assert regenerated.json()["version_number"] == 2
    replay = client.post(
        f"/api/v1/messages/{assistant_id}/regenerate",
        json={"idempotency_key": key},
        headers=headers,
    )
    assert replay.json()["id"] == regenerated.json()["id"]
    client.patch(
        f"/api/v1/messages/{user_id}",
        json={"content": "Different regeneration input"},
        headers=headers,
    ).raise_for_status()
    assert (
        client.post(
            f"/api/v1/messages/{assistant_id}/regenerate",
            json={"idempotency_key": key},
            headers=headers,
        ).status_code
        == 409
    )
    assert client.delete("/api/v1/auth/account", headers=headers).status_code == 204
