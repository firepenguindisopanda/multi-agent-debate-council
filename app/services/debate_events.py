"""Events published while a debate runs. Consumers (SSE streams) render them for the UI."""

from dataclasses import dataclass

from app.models import DebateStatus


@dataclass(frozen=True)
class DebateEvent:
    debate_id: int


@dataclass(frozen=True)
class StatusChanged(DebateEvent):
    status: DebateStatus
    current_round: int


@dataclass(frozen=True)
class MessageStarted(DebateEvent):
    message_id: int
    agent_id: int


@dataclass(frozen=True)
class TokenDelta(DebateEvent):
    message_id: int
    text: str


@dataclass(frozen=True)
class MessageCompleted(DebateEvent):
    message_id: int


@dataclass(frozen=True)
class SummaryStarted(DebateEvent):
    pass


@dataclass(frozen=True)
class SummaryDelta(DebateEvent):
    text: str


@dataclass(frozen=True)
class DebateFinished(DebateEvent):
    status: DebateStatus
