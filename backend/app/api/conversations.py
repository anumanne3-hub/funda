from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.security import (
    find_session,
    hash_token,
    new_session_token,
    require_http_session,
    session_expiry,
)
from app.db.session import get_db
from app.models import AnonymousSession, Conversation
from app.schemas.conversation import (
    AnonymousSessionRead,
    ConversationCreate,
    ConversationList,
    ConversationRead,
)

router = APIRouter()


@router.post("/anonymous-session", response_model=AnonymousSessionRead)
def create_anonymous_session(
    request: Request, response: Response, db: Session = Depends(get_db)
) -> AnonymousSession:
    existing = find_session(db, request.cookies.get(get_settings().session_cookie_name))
    if existing:
        return existing
    token = new_session_token()
    record = AnonymousSession(token_hash=hash_token(token), expires_at=session_expiry())
    db.add(record)
    db.commit()
    db.refresh(record)
    settings = get_settings()
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=settings.session_ttl_days * 86400,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        path="/",
    )
    return record


@router.post("/conversations", response_model=ConversationRead, status_code=status.HTTP_201_CREATED)
def create_conversation(
    payload: ConversationCreate, request: Request, db: Session = Depends(get_db)
) -> Conversation:
    owner = require_http_session(request, db)
    record = Conversation(anonymous_session_id=owner.id, title=payload.title.strip())
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.get("/conversations", response_model=ConversationList)
def list_conversations(
    request: Request, limit: int = 20, cursor: UUID | None = None, db: Session = Depends(get_db)
) -> ConversationList:
    owner = require_http_session(request, db)
    limit = min(max(limit, 1), 50)
    query = (
        select(Conversation)
        .where(Conversation.anonymous_session_id == owner.id)
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
    )
    if cursor:
        cursor_record = db.get(Conversation, cursor)
        if cursor_record is None or cursor_record.anonymous_session_id != owner.id:
            raise HTTPException(status_code=404, detail="Conversation not found")
        query = query.where(
            or_(
                Conversation.updated_at < cursor_record.updated_at,
                and_(
                    Conversation.updated_at == cursor_record.updated_at,
                    Conversation.id < cursor_record.id,
                ),
            )
        )
    items = list(db.scalars(query.limit(limit + 1)))
    next_cursor = items[limit - 1].id if len(items) > limit else None
    return ConversationList(
        items=[ConversationRead.model_validate(item) for item in items[:limit]],
        next_cursor=next_cursor,
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationRead)
def get_conversation(
    conversation_id: UUID, request: Request, db: Session = Depends(get_db)
) -> Conversation:
    owner = require_http_session(request, db)
    record = db.scalar(
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .where(Conversation.id == conversation_id, Conversation.anonymous_session_id == owner.id)
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return record
