from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ChatSendEvent(BaseModel):
    """The only client event accepted by the first WebSocket protocol version."""

    type: Literal["chat.send"]
    request_id: UUID
    conversation_id: UUID
    idempotency_key: str = Field(min_length=8, max_length=100)
    content: str = Field(min_length=1, max_length=12_000)

    @field_validator("content")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Message cannot be blank")
        return value


class ServerEvent(BaseModel):
    type: Literal[
        "connection.ready",
        "message.started",
        "message.delta",
        "message.completed",
        "error",
    ]
    request_id: UUID | None = None
    content: str | None = None
    code: str | None = None
    retryable: bool | None = None
    conversation_id: UUID | None = None
    message_id: UUID | None = None
