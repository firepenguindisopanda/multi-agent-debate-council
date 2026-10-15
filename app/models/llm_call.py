from datetime import datetime
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel

from app.models.debate import utcnow


class LLMCallKind(str, Enum):
    TURN = "turn"
    SUMMARY = "summary"


class LLMCall(SQLModel, table=True):
    """One chat completion made while running a debate: its cost and how it ended.

    Mirrors an OpenTelemetry GenAI `chat` span, so it can feed tracing later.
    """

    __tablename__ = "llm_call"

    id: Optional[int] = Field(default=None, primary_key=True)
    debate_id: int = Field(foreign_key="debate.id", index=True)
    # Set for agent turns; empty for the moderator's summary.
    message_id: Optional[int] = Field(default=None, foreign_key="message.id")
    kind: LLMCallKind
    request_model: Optional[str] = Field(default=None, max_length=200)
    response_model: Optional[str] = Field(default=None, max_length=200)
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    # "stop" = finished naturally, "length" = cut off by the max_tokens cap.
    finish_reason: Optional[str] = Field(default=None, max_length=40)
    time_to_first_chunk_ms: Optional[int] = None
    duration_ms: Optional[int] = None
    retries: int = 0
    # Exception class name when the call failed or was cancelled.
    error: Optional[str] = Field(default=None, max_length=100)
    created_at: datetime = Field(default_factory=utcnow)
