import math
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import ChatRequest, Conversation, Message
from app.services.limits import RequestRejected, consume


class ConversationNotFound(Exception):
    pass


@dataclass
class PreparedChat:
    request: ChatRequest
    assistant: Message
    replay: bool


def prepare_chat(
    db: Session,
    owner_id: UUID,
    conversation_id: UUID,
    idempotency_key: str,
    content: str,
    model: str,
    ip: str = "local",
) -> PreparedChat:
    # Acquire the conversation write lock before checking keys or allocating sequence numbers.
    locked = db.execute(
        update(Conversation)
        .where(Conversation.id == conversation_id, Conversation.anonymous_session_id == owner_id)
        .values(updated_at=Conversation.updated_at)
        .returning(Conversation.id)
    ).first()
    if locked is None:
        raise ConversationNotFound
    conversation = db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id, Conversation.anonymous_session_id == owner_id
        )
    )
    if conversation is None:
        raise ConversationNotFound
    existing = db.scalar(
        select(ChatRequest).where(
            ChatRequest.conversation_id == conversation_id,
            ChatRequest.idempotency_key == idempotency_key,
        )
    )
    if existing:
        user = db.get(Message, existing.user_message_id)
        if user is None or user.content != content:
            raise RequestRejected("IDEMPOTENCY_CONFLICT")
        assistant = db.get(Message, existing.assistant_message_id)
        if assistant is None:
            raise RuntimeError("Persisted assistant message disappeared")
        created = existing.created_at.replace(tzinfo=UTC)
        if (
            existing.status == "pending"
            and (datetime.now(UTC) - created).total_seconds()
            > get_settings().llm_timeout_seconds + 30
        ):
            existing.status = assistant.status = "failed"
            assistant.error_code = "REQUEST_INTERRUPTED"
        db.commit()
        return PreparedChat(existing, assistant, True)

    settings = get_settings()
    consume(db, f"session:{owner_id}", 1, settings.requests_per_minute, 60)
    consume(db, f"ip:{ip}", 1, settings.requests_per_minute * 3, 60)
    reservation = 0
    if settings.llm_provider != "mock":
        # UTF-8 bytes bound content tokens; allow extra tokens for the message envelope.
        reservation = math.ceil(
            (len(content.encode("utf-8")) + 256) * settings.llm_input_usd_per_million
            + settings.llm_max_output_tokens * settings.llm_output_usd_per_million
        )
        consume(db, "budget", reservation, int(settings.llm_daily_budget_usd * 1_000_000), 86400)

    last_sequence = (
        db.scalar(
            select(func.max(Message.sequence_number)).where(
                Message.conversation_id == conversation_id
            )
        )
        or 0
    )
    user_message = Message(
        conversation_id=conversation_id,
        sequence_number=last_sequence + 1,
        role="user",
        content=content,
        status="completed",
    )
    assistant = Message(
        conversation_id=conversation_id,
        sequence_number=last_sequence + 2,
        role="assistant",
        content="",
        status="pending",
    )
    db.add_all([user_message, assistant])
    db.flush()
    request = ChatRequest(
        conversation_id=conversation_id,
        user_message_id=user_message.id,
        assistant_message_id=assistant.id,
        idempotency_key=idempotency_key,
        status="pending",
        model=model,
        prompt_version="v1",
        reserved_cost_microusd=reservation,
    )
    if conversation.title == "New conversation":
        conversation.title = content[:197] + ("..." if len(content) > 197 else "")
    db.add(request)
    conversation.updated_at = datetime.now(UTC)
    db.commit()
    return PreparedChat(request, assistant, False)


def complete_chat(
    db: Session,
    request_id: UUID,
    assistant_id: UUID,
    content: str,
    started: float,
    usage: dict | None = None,
) -> None:
    request = db.get(ChatRequest, request_id)
    assistant = db.get(Message, assistant_id)
    if request is None or assistant is None:
        raise RuntimeError("Persisted chat request disappeared")
    assistant.content = content
    assistant.status = "completed"
    request.status = "completed"
    request.duration_ms = int((time.perf_counter() - started) * 1000)
    if usage:
        assistant.input_tokens = usage.get("input_tokens")
        assistant.output_tokens = usage.get("output_tokens")
        assistant.provider_request_id = usage.get("provider_request_id")
        if assistant.input_tokens is not None and assistant.output_tokens is not None:
            settings = get_settings()
            request.cost_microusd = math.ceil(
                assistant.input_tokens * settings.llm_input_usd_per_million
                + assistant.output_tokens * settings.llm_output_usd_per_million
            )
    db.commit()


def fail_chat(db: Session, request_id: UUID, assistant_id: UUID, code: str, started: float) -> None:
    request = db.get(ChatRequest, request_id)
    assistant = db.get(Message, assistant_id)
    if request is None or assistant is None:
        return
    assistant.status = "failed"
    assistant.error_code = code
    request.status = "failed"
    request.duration_ms = int((time.perf_counter() - started) * 1000)
    db.commit()
