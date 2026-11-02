from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ChatSendEvent(BaseModel):
    """The only client event accepted by the first WebSocket protocol version."""

    type: Literal["chat.send"]
    request_id: UUID
    content: str = Field(min_length=1, max_length=12_000)


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
