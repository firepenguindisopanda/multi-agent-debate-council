from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Column, Text
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.debate_participant import DebateParticipant
    from app.models.message import Message


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DebateStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    STOPPED = "stopped"
    FAILED = "failed"

    @property
    def is_active(self) -> bool:
        return self in (DebateStatus.PENDING, DebateStatus.IN_PROGRESS)


class DebateBase(SQLModel, table=False):
    """Base debate - shared attributes."""

    topic: str = Field(max_length=500)
    max_rounds: int = Field(default=3, ge=1, le=10)
    current_round: int = Field(default=0, ge=0)


class Debate(DebateBase, table=True):
    """A debate session where agents discuss a topic."""

    id: Optional[int] = Field(default=None, primary_key=True)
    status: DebateStatus = Field(default=DebateStatus.PENDING)
    created_by_user_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)
    created_at: datetime = Field(default_factory=utcnow)
    completed_at: Optional[datetime] = None
    # Moderator's consensus report (markdown), written when the debate completes.
    summary: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    error: Optional[str] = Field(default=None, max_length=1000)

    participants: list["DebateParticipant"] = Relationship(
        back_populates="debate",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "order_by": "DebateParticipant.order",
        },
    )
    messages: list["Message"] = Relationship(
        back_populates="debate",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "order_by": "Message.id"},
    )
