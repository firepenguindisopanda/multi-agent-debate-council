from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, SQLModel

if TYPE_CHECKING:
    pass


class MessageStatus(str, Enum):
    STREAMING = "streaming"
    COMPLETE = "complete"


class MessageBase(SQLModel, table=False):
    """Base message - shared attributes."""

    round_number: int = Field(ge=1)
    content: str = ""


class Message(MessageBase, table=True):
    """An agent's contribution to a debate."""

    id: Optional[int] = Field(default=None, primary_key=True)
    debate_id: int = Field(foreign_key="debate.id", index=True)
    agent_id: int = Field(foreign_key="agent.id", index=True)
    participant_id: int = Field(foreign_key="debateparticipant.id", index=True)
    content: str = Field(default="")
    status: MessageStatus = Field(default=MessageStatus.STREAMING)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
