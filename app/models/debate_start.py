from datetime import datetime
from typing import Optional

from sqlalchemy import Index
from sqlmodel import Field, SQLModel

from app.models.debate import utcnow


class DebateStart(SQLModel, table=True):
    """Ledger of debates a user has started, used for the daily limit.

    Deliberately not linked to Debate, so deleting a debate doesn't refund it.
    """

    __tablename__ = "debate_start"
    # The limit check is "this user's starts since <time>".
    __table_args__ = (Index("ix_debate_start_user_id_created_at", "user_id", "created_at"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    created_at: datetime = Field(default_factory=utcnow)
