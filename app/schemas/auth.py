import re

from pydantic import EmailStr, field_validator
from sqlmodel import SQLModel

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,30}$")


class SigninRequest(SQLModel):
    username: str
    password: str


class SignupRequest(SQLModel):
    username: str
    email: EmailStr
    password: str

    @field_validator("username")
    @classmethod
    def _username(cls, v: str) -> str:
        v = v.strip()
        if not USERNAME_RE.match(v):
            raise ValueError("Username must be 3-30 letters, numbers, dots, dashes or underscores.")
        return v

    @field_validator("password")
    @classmethod
    def _password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters.")
        return v


class TokenResponse(SQLModel):
    access_token: str
    token_type: str = "bearer"
