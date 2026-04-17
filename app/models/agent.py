from __future__ import annotations

from sqlmodel import Field, SQLModel
from typing import Optional


class AgentBase(SQLModel, table=False):
    """Base agent template - used for creating agent instances."""

    name: str = Field(index=True, unique=True)
    role: str = Field(max_length=20)
    description: str = ""
    system_prompt: str = ""
    avatar: Optional[str] = None


class Agent(AgentBase, table=True):
    """Predefined specialist agent template."""

    id: Optional[int] = Field(default=None, primary_key=True)
