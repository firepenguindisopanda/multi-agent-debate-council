# Import all models to register them with SQLModel.metadata
from app.models.agent import Agent, AgentBase
from app.models.debate import Debate, DebateBase, DebateStatus
from app.models.debate_participant import DebateParticipant, DebateParticipantBase
from app.models.message import Message, MessageBase, MessageStatus
from app.models.user import User, UserBase

# Configure relationships (must be after all models are imported)
from app.models import relationships  # noqa: F401

__all__ = [
    "Agent",
    "AgentBase",
    "Debate",
    "DebateBase",
    "DebateStatus",
    "DebateParticipant",
    "DebateParticipantBase",
    "Message",
    "MessageBase",
    "MessageStatus",
    "User",
    "UserBase",
]
