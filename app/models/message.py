from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Column, Text
from sqlmodel import Field, Relationship, SQLModel

from app.models.agent import Agent
from app.models.debate import utcnow

if TYPE_CHECKING:
    from app.models.debate import Debate
    from app.models.debate_participant import DebateParticipant


class MessageStatus(str, Enum):
    STREAMING = "streaming"
    COMPLETE = "complete"


class MessageBase(SQLModel, table=False):
    """Base message - shared attributes."""

    round_number: int = Field(ge=1)


class Message(MessageBase, table=True):
    """An agent's contribution to a debate.

    debate_id duplicates participant.debate_id on purpose: transcripts are always
    loaded per debate, so it keeps that query a single indexed lookup.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    debate_id: int = Field(foreign_key="debate.id", index=True)
    agent_id: int = Field(foreign_key="agent.id", index=True)
    participant_id: int = Field(foreign_key="debateparticipant.id", index=True)
    content: str = Field(default="", sa_column=Column(Text, nullable=False, default=""))
    status: MessageStatus = Field(default=MessageStatus.STREAMING)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    debate: Optional["Debate"] = Relationship(back_populates="messages")
    participant: Optional["DebateParticipant"] = Relationship(back_populates="messages")
    agent: Optional[Agent] = Relationship(sa_relationship_kwargs={"lazy": "joined"})
