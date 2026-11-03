from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.security import (
    find_session,
    hash_token,
    new_session_token,
    owner_identity,
    session_expiry,
)
from app.db.session import get_db
from app.models import AnonymousSession, Conversation, Project
from app.schemas.conversation import (
    AnonymousSessionRead,
    ConversationCreate,
    ConversationList,
    ConversationRead,
    ConversationUpdate,
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
    field, owner_id = owner_identity(request, db, csrf=True)
    if payload.project_id and (
        field != "user_id"
        or db.scalar(
            select(Project).where(Project.id == payload.project_id, Project.user_id == owner_id)
        )
        is None
    ):
        raise HTTPException(status_code=404, detail="Project not found")
    record = Conversation(
        **{field: owner_id}, title=payload.title.strip(), project_id=payload.project_id
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.get("/conversations", response_model=ConversationList)
def list_conversations(
    request: Request,
    limit: int = 20,
    cursor: UUID | None = None,
    project_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> ConversationList:
    field, owner_id = owner_identity(request, db)
    owner_column = getattr(Conversation, field)
    limit = min(max(limit, 1), 50)
    query = (
        select(Conversation)
        .where(owner_column == owner_id)
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
    )
    if project_id:
        if (
            field != "user_id"
            or db.scalar(
                select(Project).where(Project.id == project_id, Project.user_id == owner_id)
            )
            is None
        ):
            raise HTTPException(status_code=404, detail="Project not found")
        query = query.where(Conversation.project_id == project_id)
    if cursor:
        cursor_record = db.get(Conversation, cursor)
        if (
            cursor_record is None
            or getattr(cursor_record, field) != owner_id
            or (project_id is not None and cursor_record.project_id != project_id)
        ):
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
    field, owner_id = owner_identity(request, db)
    record = db.scalar(
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .where(Conversation.id == conversation_id, getattr(Conversation, field) == owner_id)
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return record


@router.patch("/conversations/{conversation_id}", response_model=ConversationRead)
def update_conversation(
    conversation_id: UUID,
    payload: ConversationUpdate,
    request: Request,
    db: Session = Depends(get_db),
) -> Conversation:
    field, owner_id = owner_identity(request, db, csrf=True)
    record = db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id, getattr(Conversation, field) == owner_id
        )
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if "title" in payload.model_fields_set:
        if payload.title is None or not payload.title.strip():
            raise HTTPException(status_code=422, detail="Title required")
        record.title = payload.title.strip()
    if "project_id" in payload.model_fields_set:
        if payload.project_id is not None and (
            field != "user_id"
            or db.scalar(
                select(Project).where(Project.id == payload.project_id, Project.user_id == owner_id)
            )
            is None
        ):
            raise HTTPException(status_code=404, detail="Project not found")
        record.project_id = payload.project_id
    db.commit()
    db.refresh(record)
    return record


@router.delete("/conversations/{conversation_id}", status_code=204)
def delete_conversation(
    conversation_id: UUID, request: Request, db: Session = Depends(get_db)
) -> None:
    field, owner_id = owner_identity(request, db, csrf=True)
    record = db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id, getattr(Conversation, field) == owner_id
        )
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    db.delete(record)
    db.commit()
