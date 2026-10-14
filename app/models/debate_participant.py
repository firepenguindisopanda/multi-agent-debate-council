from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship, SQLModel

from app.models.agent import Agent

if TYPE_CHECKING:
    from app.models.debate import Debate
    from app.models.message import Message


class DebateParticipantBase(SQLModel, table=False):
    """Base debate participant - shared attributes."""

    order: int = Field(default=0, ge=0)
    is_active: bool = Field(default=True)


class DebateParticipant(DebateParticipantBase, table=True):
    """Links an agent to a debate."""

    id: Optional[int] = Field(default=None, primary_key=True)
    debate_id: int = Field(foreign_key="debate.id", index=True)
    agent_id: int = Field(foreign_key="agent.id", index=True)

    debate: Optional["Debate"] = Relationship(back_populates="participants")
    agent: Optional[Agent] = Relationship(sa_relationship_kwargs={"lazy": "joined"})
    messages: list["Message"] = Relationship(back_populates="participant")
