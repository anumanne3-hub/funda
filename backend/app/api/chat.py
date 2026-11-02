import asyncio
import json
import logging
import time
from dataclasses import asdict
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.core.config import get_settings
from app.core.security import websocket_session
from app.providers import ProviderError
from app.providers.llm import Usage
from app.schemas.chat import ChatSendEvent, ServerEvent
from app.services.chat import ConversationNotFound, complete_chat, fail_chat, prepare_chat
from app.services.limits import RequestRejected

router = APIRouter()
logger = logging.getLogger(__name__)


async def send_event(websocket: WebSocket, event: ServerEvent) -> None:
    try:
        await websocket.send_json(event.model_dump(mode="json", exclude_none=True))
    except (OSError, RuntimeError) as exc:
        raise WebSocketDisconnect from exc


@router.websocket("/ws/chat")
async def chat_socket(websocket: WebSocket) -> None:
    """Persist chat turns and stream provider deltas over a versioned protocol."""
    origin = websocket.headers.get("origin")
    settings = get_settings()
    if (origin and origin not in settings.frontend_origins) or (
        settings.app_env == "production" and not origin
    ):
        await websocket.close(code=4403)
        return
    await websocket.accept()
    session_factory = websocket.app.state.session_factory
    with session_factory() as db:
        owner = websocket_session(websocket, db)
    if owner is None:
        await send_event(
            websocket,
            ServerEvent(
                type="error",
                code="SESSION_REQUIRED",
                content="Create an anonymous session first.",
                retryable=False,
            ),
        )
        await websocket.close(code=4401)
        return
    await send_event(websocket, ServerEvent(type="connection.ready"))
    logger.info("websocket connected", extra={"event": "websocket.connected"})
    try:
        while True:
            try:
                raw = await websocket.receive_text()
                if len(raw.encode("utf-8")) > 65536:
                    await websocket.close(code=1009)
                    return
                event = ChatSendEvent.model_validate(json.loads(raw))
            except (ValidationError, ValueError):
                await send_event(
                    websocket,
                    ServerEvent(
                        type="error",
                        code="INVALID_CHAT_EVENT",
                        content="Invalid chat event.",
                        retryable=False,
                    ),
                )
                continue
            with session_factory() as db:
                owner = websocket_session(websocket, db)
            if owner is None:
                await websocket.close(code=4401)
                return
            await process_chat(websocket, owner.id, event)
    except WebSocketDisconnect:
        logger.info("websocket disconnected", extra={"event": "websocket.disconnected"})


async def process_chat(websocket: WebSocket, owner_id: UUID, event: ChatSendEvent) -> None:
    started = time.perf_counter()
    provider = websocket.app.state.llm_provider
    session_factory = websocket.app.state.session_factory
    try:
        with session_factory() as db:
            prepared = prepare_chat(
                db,
                owner_id,
                event.conversation_id,
                event.idempotency_key,
                event.content,
                provider.model,
                websocket.client.host if websocket.client else "unknown",
            )
            persisted_request_id = prepared.request.id
            assistant_id = prepared.assistant.id
            previous_status = prepared.request.status
            previous_content = prepared.assistant.content
            previous_error = prepared.assistant.error_code
    except RequestRejected as exc:
        await send_event(
            websocket,
            ServerEvent(
                type="error",
                request_id=event.request_id,
                code=exc.code,
                content="Request rejected. Try later for rate or budget limits.",
                retryable=exc.retryable,
            ),
        )
        return
    except ConversationNotFound:
        await send_event(
            websocket,
            ServerEvent(
                type="error",
                request_id=event.request_id,
                code="CONVERSATION_NOT_FOUND",
                content="Conversation not found.",
                retryable=False,
            ),
        )
        return
    except Exception:
        logger.error("chat preparation failed", extra={"event": "chat.prepare.failed"})
        await send_event(
            websocket,
            ServerEvent(
                type="error",
                request_id=event.request_id,
                code="DATABASE_UNAVAILABLE",
                content="The request could not be saved. Retry with the same request key.",
                retryable=True,
            ),
        )
        return

    await send_event(
        websocket,
        ServerEvent(
            type="message.started",
            request_id=event.request_id,
            conversation_id=event.conversation_id,
            message_id=assistant_id,
        ),
    )
    if prepared.replay:
        if previous_status == "completed":
            await send_event(
                websocket,
                ServerEvent(
                    type="message.delta", request_id=event.request_id, content=previous_content
                ),
            )
            await send_event(
                websocket,
                ServerEvent(
                    type="message.completed",
                    request_id=event.request_id,
                    conversation_id=event.conversation_id,
                    message_id=assistant_id,
                ),
            )
        else:
            await send_event(
                websocket,
                ServerEvent(
                    type="error",
                    request_id=event.request_id,
                    code="REQUEST_PENDING" if previous_status == "pending" else previous_error,
                    content="Request is pending."
                    if previous_status == "pending"
                    else "This request failed. It will not be charged again by a retry.",
                    retryable=previous_status == "pending",
                ),
            )
        return

    chunks: list[str] = []
    usage: dict = {}
    connected = True
    try:
        async with asyncio.timeout(get_settings().llm_timeout_seconds):
            async for chunk in provider.stream(event.content):
                if isinstance(chunk, Usage):
                    usage = asdict(chunk)
                    continue
                chunks.append(chunk)
                if connected:
                    try:
                        await send_event(
                            websocket,
                            ServerEvent(
                                type="message.delta",
                                request_id=event.request_id,
                                content=chunk,
                            ),
                        )
                    except (WebSocketDisconnect, OSError, RuntimeError):
                        connected = False
        if not chunks:
            raise ProviderError("PROVIDER_EMPTY_RESPONSE", False)
        with session_factory() as db:
            complete_chat(db, persisted_request_id, assistant_id, "".join(chunks), started, usage)
        if not connected:
            raise WebSocketDisconnect
        await send_event(
            websocket,
            ServerEvent(
                type="message.completed",
                request_id=event.request_id,
                conversation_id=event.conversation_id,
                message_id=assistant_id,
            ),
        )
        logger.info(
            "chat completed",
            extra={
                "event": "chat.completed",
                "request_id": str(event.request_id),
                "conversation_id": str(event.conversation_id),
            },
        )
    except WebSocketDisconnect:
        raise
    except (ProviderError, TimeoutError) as exc:
        code = exc.code if isinstance(exc, ProviderError) else "PROVIDER_TIMEOUT"
        with session_factory() as db:
            fail_chat(db, persisted_request_id, assistant_id, code, started)
        if not connected:
            raise WebSocketDisconnect from exc
        await send_event(
            websocket,
            ServerEvent(
                type="error",
                request_id=event.request_id,
                code=code,
                content="The model provider could not complete the request.",
                retryable=False,
            ),
        )
    except Exception:
        with session_factory() as db:
            fail_chat(db, persisted_request_id, assistant_id, "INTERNAL_ERROR", started)
        logger.error(
            "chat failed", extra={"event": "chat.failed", "request_id": str(event.request_id)}
        )
        await send_event(
            websocket,
            ServerEvent(
                type="error",
                request_id=event.request_id,
                code="INTERNAL_ERROR",
                content="The request could not be completed.",
                retryable=False,
            ),
        )
