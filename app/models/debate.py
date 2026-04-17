from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, SQLModel

if TYPE_CHECKING:
    pass


class DebateStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    STOPPED = "stopped"


class DebateBase(SQLModel, table=False):
    """Base debate - shared attributes."""

    topic: str = Field(max_length=500)
    max_rounds: int = Field(default=3, ge=1, le=10)
    current_round: int = Field(default=0, ge=0)


class Debate(DebateBase, table=True):
    """A debate session where agents discuss a topic."""

    id: Optional[int] = Field(default=None, primary_key=True)
    status: DebateStatus = Field(default=DebateStatus.PENDING)
    created_by_user_id: Optional[int] = Field(default=None, foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None

    # Note: Relationships are configured in a separate function to avoid circular imports
