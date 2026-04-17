"""Configure SQLModel relationships.

This module configures relationships between models after all models are imported.
This avoids circular import issues.
"""

from sqlalchemy.orm import relationship

from app.models.agent import Agent
from app.models.debate import Debate
from app.models.debate_participant import DebateParticipant
from app.models.message import Message


def configure_relationships() -> None:
    """Configure all SQLModel relationships."""
    # Debate <-> DebateParticipant
    Debate.participants = relationship(
        "DebateParticipant",
        back_populates="debate",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    DebateParticipant.debate = relationship(
        "Debate",
        back_populates="participants",
    )

    # DebateParticipant <-> Message
    DebateParticipant.messages = relationship(
        "Message",
        back_populates="participant",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    Message.participant = relationship(
        "DebateParticipant",
        back_populates="messages",
    )

    # Message <-> Agent
    Message.agent = relationship("Agent")

    # Message <-> Debate
    Message.debate = relationship("Debate")


# Configure relationships when this module is imported
configure_relationships()
