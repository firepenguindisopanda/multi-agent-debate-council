from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, SQLModel

if TYPE_CHECKING:
    pass


class DebateParticipantBase(SQLModel, table=False):
    """Base debate participant - shared attributes."""

    order: int = Field(default=0, ge=0)
    is_active: bool = Field(default=True)


class DebateParticipant(DebateParticipantBase, table=True):
    """Links an agent to a debate."""

    id: Optional[int] = Field(default=None, primary_key=True)
    debate_id: int = Field(foreign_key="debate.id", index=True)
    agent_id: int = Field(foreign_key="agent.id", index=True)
