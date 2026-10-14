from datetime import datetime
from typing import Optional

from pydantic import Field
from sqlmodel import SQLModel

from app.models import DebateStatus, MessageStatus


class AgentRead(SQLModel):
    id: int
    name: str
    role: str
    description: str
    avatar: Optional[str] = None


class DebateCreate(SQLModel):
    topic: str = Field(min_length=10, max_length=500)
    agent_ids: list[int] = Field(min_length=2)
    max_rounds: int = Field(default=2, ge=1, le=5)


class ParticipantRead(SQLModel):
    id: int
    order: int
    agent: AgentRead


class MessageRead(SQLModel):
    id: int
    round_number: int
    agent_id: int
    content: str
    status: MessageStatus
    created_at: datetime


class DebateListItem(SQLModel):
    id: int
    topic: str
    status: DebateStatus
    max_rounds: int
    current_round: int
    created_at: datetime
    completed_at: Optional[datetime] = None


class DebateDetail(DebateListItem):
    summary: Optional[str] = None
    error: Optional[str] = None
    participants: list[ParticipantRead]
    messages: list[MessageRead]
