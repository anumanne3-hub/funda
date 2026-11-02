from fastapi.testclient import TestClient

from app.main import app


def test_health() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_websocket_streams_mock_answer() -> None:
    with TestClient(app) as client, client.websocket_connect("/api/v1/ws/chat") as socket:
        assert socket.receive_json()["type"] == "connection.ready"
        socket.send_json(
            {
                "type": "chat.send",
                "request_id": "6f833db2-ae65-4f1f-b9ad-b204fdc037c5",
                "content": "Hello",
            }
        )
        assert socket.receive_json()["type"] == "message.started"
        event_types = []
        while "message.completed" not in event_types:
            event_types.append(socket.receive_json()["type"])
        assert "message.delta" in event_types
