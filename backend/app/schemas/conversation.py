from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ConversationCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    title: str = Field(default="New conversation", min_length=1, max_length=200)


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    sequence_number: int
    role: str
    content: str
    status: str
    error_code: str | None
    created_at: datetime


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime
    messages: list[MessageRead] = Field(default_factory=list)


class ConversationList(BaseModel):
    items: list[ConversationRead]
    next_cursor: UUID | None = None


class AnonymousSessionRead(BaseModel):
    id: UUID
    expires_at: datetime
