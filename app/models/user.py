from __future__ import annotations

from typing import Optional

from pydantic import EmailStr
from sqlmodel import Field, SQLModel


class UserBase(SQLModel, table=False):
    username: str = Field(index=True, unique=True)
    email: EmailStr = Field(index=True, unique=True)
    password: str
    role: str = ""


class User(UserBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
