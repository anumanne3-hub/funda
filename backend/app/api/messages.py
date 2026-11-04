import asyncio
import math
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import account_identity, hash_token
from app.db.session import get_db
from app.models import (
    ChatRequest,
    Conversation,
    Message,
    MessageCitation,
    MessageFeedback,
    MessageVersion,
    RegenerationRequest,
)
from app.providers import ProviderError
from app.providers.llm import Usage
from app.services.limits import consume

router = APIRouter()


class VersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    message_id: UUID
    version_number: int
    parent_version_id: UUID | None
    content: str


class CitationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    ordinal: int
    document_id: UUID
    document_version_id: UUID
    chunk_id: UUID
    title: str
    source_url: str | None
    page: int | None
    section: str | None
    start_ms: int | None
    end_ms: int | None


class EditInput(BaseModel):
    content: str = Field(min_length=1, max_length=12000)


class FeedbackInput(BaseModel):
    version_id: UUID
    rating: int = Field(ge=-1, le=1)
    note: str | None = Field(default=None, max_length=2000)


class RegenerateInput(BaseModel):
    idempotency_key: UUID


def owned_message(db: Session, user_id: UUID, message_id: UUID, *, lock: bool = False) -> Message:
    query = (
        select(Message)
        .join(Conversation)
        .where(Message.id == message_id, Conversation.user_id == user_id)
    )
    message = db.scalar(query)
    if message is None:
        raise HTTPException(status_code=404, detail="Message not found")
    if lock:
        db.execute(
            update(Conversation)
            .where(Conversation.id == message.conversation_id, Conversation.user_id == user_id)
            .values(updated_at=Conversation.updated_at)
        )
    return message


def versions(db: Session, message: Message) -> list[MessageVersion]:
    rows = list(
        db.scalars(
            select(MessageVersion)
            .where(MessageVersion.message_id == message.id)
            .order_by(MessageVersion.version_number)
        )
    )
    if not rows:
        first = MessageVersion(message_id=message.id, version_number=1, content=message.content)
        db.add(first)
        db.flush()
        rows = [first]
    return rows


@router.get("/messages/{message_id}/versions", response_model=list[VersionRead])
def list_versions(
    message_id: UUID, request: Request, db: Session = Depends(get_db)
) -> list[MessageVersion]:
    user = account_identity(request, db)
    owned_message(db, user.id, message_id)
    return list(
        db.scalars(
            select(MessageVersion)
            .where(MessageVersion.message_id == message_id)
            .order_by(MessageVersion.version_number)
        )
    )


@router.get("/messages/{message_id}/citations", response_model=list[CitationRead])
def list_citations(
    message_id: UUID, request: Request, db: Session = Depends(get_db)
) -> list[MessageCitation]:
    user = account_identity(request, db)
    message = owned_message(db, user.id, message_id)
    if message.role != "assistant" or message.status != "completed":
        return []
    latest = db.scalar(
        select(MessageVersion.id)
        .where(MessageVersion.message_id == message_id)
        .order_by(MessageVersion.version_number.desc())
        .limit(1)
    )
    if latest is None:
        return []
    return list(
        db.scalars(
            select(MessageCitation)
            .where(MessageCitation.message_version_id == latest)
            .order_by(MessageCitation.ordinal)
        )
    )


@router.patch("/messages/{message_id}", response_model=VersionRead)
def edit_message(
    message_id: UUID, payload: EditInput, request: Request, db: Session = Depends(get_db)
) -> MessageVersion:
    user = account_identity(request, db, csrf=True)
    message = owned_message(db, user.id, message_id, lock=True)
    if message.role != "user" or message.status != "completed":
        raise HTTPException(status_code=409, detail="Only completed user messages can be edited")
    prior = versions(db, message)[-1]
    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="Content required")
    row = MessageVersion(
        message_id=message.id,
        version_number=prior.version_number + 1,
        parent_version_id=prior.id,
        content=content,
    )
    db.add(row)
    message.content = content
    db.commit()
    db.refresh(row)
    return row


@router.post("/messages/{message_id}/activate/{version_id}", response_model=VersionRead)
def activate_version(
    message_id: UUID, version_id: UUID, request: Request, db: Session = Depends(get_db)
) -> MessageVersion:
    user = account_identity(request, db, csrf=True)
    message = owned_message(db, user.id, message_id, lock=True)
    if message.role != "user" or message.status != "completed":
        raise HTTPException(status_code=409, detail="Only completed user messages can be activated")
    rows = versions(db, message)
    chosen = next((row for row in rows if row.id == version_id), None)
    if chosen is None:
        raise HTTPException(status_code=404, detail="Version not found")
    row = MessageVersion(
        message_id=message.id,
        version_number=rows[-1].version_number + 1,
        parent_version_id=chosen.id,
        content=chosen.content,
    )
    db.add(row)
    message.content = chosen.content
    db.commit()
    db.refresh(row)
    return row


@router.post("/messages/{message_id}/feedback", status_code=204)
def submit_feedback(
    message_id: UUID, payload: FeedbackInput, request: Request, db: Session = Depends(get_db)
) -> None:
    user = account_identity(request, db, csrf=True)
    message = owned_message(db, user.id, message_id, lock=True)
    if message.role != "assistant" or message.status != "completed" or payload.rating == 0:
        raise HTTPException(
            status_code=409, detail="Feedback requires a completed assistant message"
        )
    row = next(
        (version for version in versions(db, message) if version.id == payload.version_id), None
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Version not found")
    existing = db.scalar(
        select(MessageFeedback).where(
            MessageFeedback.user_id == user.id, MessageFeedback.version_id == row.id
        )
    )
    if existing is None:
        db.add(
            MessageFeedback(
                user_id=user.id, version_id=row.id, rating=payload.rating, note=payload.note
            )
        )
    else:
        existing.rating = payload.rating
        existing.note = payload.note
    db.commit()


@router.post("/messages/{message_id}/regenerate", response_model=VersionRead)
async def regenerate_message(
    message_id: UUID, payload: RegenerateInput, request: Request, db: Session = Depends(get_db)
) -> MessageVersion:
    user = account_identity(request, db, csrf=True)
    assistant = owned_message(db, user.id, message_id, lock=True)
    if assistant.role != "assistant" or assistant.status != "completed":
        raise HTTPException(
            status_code=409, detail="Only completed assistant messages can be regenerated"
        )
    original = db.scalar(
        select(ChatRequest).where(ChatRequest.assistant_message_id == assistant.id)
    )
    if original is None:
        raise HTTPException(status_code=409, detail="Original chat request not found")
    user_message = db.get(Message, original.user_message_id)
    if user_message is None:
        raise HTTPException(status_code=409, detail="Original user message not found")
    key = str(payload.idempotency_key)
    input_hash = hash_token(user_message.content)
    existing = db.scalar(
        select(RegenerationRequest).where(
            RegenerationRequest.assistant_message_id == assistant.id,
            RegenerationRequest.idempotency_key == key,
        )
    )
    if existing is not None:
        if existing.input_hash != input_hash:
            raise HTTPException(
                status_code=409, detail="Regeneration key belongs to different content"
            )
        if existing.status == "completed" and existing.version_id:
            result = db.get(MessageVersion, existing.version_id)
            if result is not None:
                return result
        raise HTTPException(status_code=409, detail="Regeneration is pending or failed")
    pending = db.scalar(
        select(RegenerationRequest).where(
            RegenerationRequest.assistant_message_id == assistant.id,
            RegenerationRequest.status == "pending",
        )
    )
    if pending is not None:
        created = pending.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        if (datetime.now(UTC) - created).total_seconds() <= get_settings().llm_timeout_seconds + 30:
            raise HTTPException(status_code=409, detail="Regeneration already pending")
        pending.status = "failed"
        pending.error_code = "REQUEST_INTERRUPTED"
    versions(db, assistant)
    settings = get_settings()
    consume(db, f"session:{user.id}", 1, settings.requests_per_minute, 60)
    reservation = 0
    if settings.llm_provider != "mock":
        consume(db, "provider-requests", 1, settings.llm_daily_request_limit, 86400)
        reservation = math.ceil(
            (len(user_message.content.encode("utf-8")) + 256) * settings.llm_input_usd_per_million
            + settings.llm_max_output_tokens * settings.llm_output_usd_per_million
        )
        consume(db, "budget", reservation, int(settings.llm_daily_budget_usd * 1_000_000), 86400)
    operation = RegenerationRequest(
        assistant_message_id=assistant.id,
        idempotency_key=key,
        input_hash=input_hash,
        status="pending",
        reserved_cost_microusd=reservation,
    )
    db.add(operation)
    db.commit()
    try:
        chunks: list[str] = []
        async with asyncio.timeout(settings.llm_timeout_seconds):
            async for chunk in request.app.state.llm_provider.stream(user_message.content):
                if not isinstance(chunk, Usage):
                    chunks.append(chunk)
        if not chunks:
            raise ProviderError("PROVIDER_EMPTY_RESPONSE", False)
        with request.app.state.session_factory() as result_db:
            current = owned_message(result_db, user.id, message_id, lock=True)
            prior = versions(result_db, current)[-1]
            result = MessageVersion(
                message_id=current.id,
                version_number=prior.version_number + 1,
                parent_version_id=prior.id,
                content="".join(chunks),
            )
            result_db.add(result)
            result_db.flush()
            current.content = result.content
            saved = result_db.get(RegenerationRequest, operation.id)
            if saved is None:
                raise RuntimeError("Regeneration record disappeared")
            saved.status = "completed"
            saved.version_id = result.id
            result_db.commit()
            result_db.refresh(result)
            return result
    except (ProviderError, TimeoutError) as exc:
        with request.app.state.session_factory() as result_db:
            saved = result_db.get(RegenerationRequest, operation.id)
            if saved is not None:
                saved.status = "failed"
                saved.error_code = (
                    exc.code if isinstance(exc, ProviderError) else "PROVIDER_TIMEOUT"
                )
                result_db.commit()
        raise HTTPException(status_code=503, detail="Model provider could not regenerate") from None
