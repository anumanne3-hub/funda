import asyncio
import logging
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.schemas.chat import ChatSendEvent, ServerEvent

router = APIRouter()
logger = logging.getLogger(__name__)


async def send_event(websocket: WebSocket, event: ServerEvent) -> None:
    await websocket.send_json(event.model_dump(mode="json", exclude_none=True))


@router.websocket("/ws/chat")
async def chat_socket(websocket: WebSocket) -> None:
    """Stream chat events; persistence and session ownership are added next."""
    await websocket.accept()
    await send_event(websocket, ServerEvent(type="connection.ready"))
    logger.info("websocket connected", extra={"event": "websocket.connected"})

    try:
        while True:
            raw_event = await websocket.receive_json()
            try:
                event = ChatSendEvent.model_validate(raw_event)
            except ValidationError:
                await send_event(
                    websocket,
                    ServerEvent(
                        type="error",
                        code="INVALID_CHAT_EVENT",
                        content="Send a non-empty message using the chat.send event.",
                        retryable=False,
                    ),
                )
                continue

            await stream_mock_answer(websocket, event.request_id, event.content)
    except WebSocketDisconnect:
        logger.info("websocket disconnected", extra={"event": "websocket.disconnected"})


async def stream_mock_answer(websocket: WebSocket, request_id: UUID, content: str) -> None:
    """Deterministic streaming proves the protocol before a paid LLM is connected."""
    await send_event(websocket, ServerEvent(type="message.started", request_id=request_id))
    answer = f"Mock assistant: I received your message: {content}"
    for token in answer.split(" "):
        await send_event(
            websocket,
            ServerEvent(type="message.delta", request_id=request_id, content=f"{token} "),
        )
        await asyncio.sleep(0.025)
    await send_event(websocket, ServerEvent(type="message.completed", request_id=request_id))
    logger.info(
        "mock chat completed",
        extra={"event": "chat.completed", "request_id": str(request_id)},
    )
