import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from sqlalchemy.types import Uuid

from app.db.base import Base


class AnonymousSession(Base):
    __tablename__ = "anonymous_sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="anonymous_session", cascade="all, delete-orphan"
    )


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        Index("ix_conversations_owner_updated", "anonymous_session_id", "updated_at"),
        Index("ix_conversations_user_updated", "user_id", "updated_at"),
        CheckConstraint(
            "(anonymous_session_id IS NULL) <> (user_id IS NULL)", name="ck_conversation_owner"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    anonymous_session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("anonymous_sessions.id", ondelete="CASCADE"), nullable=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(String(200), default="New conversation", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    anonymous_session: Mapped[AnonymousSession | None] = relationship(
        back_populates="conversations"
    )
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.sequence_number",
    )
    requests: Mapped[list["ChatRequest"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("role IN ('user','assistant','system')", name="ck_messages_role"),
        CheckConstraint("status IN ('pending','completed','failed')", name="ck_messages_status"),
        UniqueConstraint("conversation_id", "sequence_number", name="uq_message_sequence"),
        Index("ix_messages_conversation_created", "conversation_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    provider_request_id: Mapped[str | None] = mapped_column(String(200))
    error_code: Mapped[str | None] = mapped_column(String(100))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class ChatRequest(Base):
    __tablename__ = "chat_requests"
    __table_args__ = (
        CheckConstraint("status IN ('pending','completed','failed')", name="ck_requests_status"),
        UniqueConstraint("conversation_id", "idempotency_key", name="uq_request_idempotency"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    user_message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("messages.id"), nullable=False)
    assistant_message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("messages.id"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), default="v1", nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    reserved_cost_microusd: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_microusd: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    conversation: Mapped[Conversation] = relationship(back_populates="requests")


class LimitBucket(Base):
    __tablename__ = "limit_buckets"

    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    value: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
