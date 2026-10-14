from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Response
from pwdlib import PasswordHash

from app.config import get_settings

password_hash = PasswordHash.recommended()


def encrypt_password(password: str):
    return password_hash.hash(password)


def verify_password(plaintext_password: str, encrypted_password):
    return password_hash.verify(password=plaintext_password, hash=encrypted_password)


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    settings = get_settings()
    expires_delta = expires_delta or timedelta(minutes=settings.jwt_access_token_expires)
    to_encode = {**data, "exp": datetime.now(timezone.utc) + expires_delta}
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.jwt_algorithm)


def set_auth_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.is_production,
        max_age=settings.jwt_access_token_expires * 60,
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(
        key="access_token", httponly=True, samesite="lax", secure=get_settings().is_production
    )


def safe_next_url(value: str | None, default: str = "/debates") -> str:
    """Only allow same-site relative redirects."""
    if value and value.startswith("/") and not value.startswith("//") and "\\" not in value:
        return value
    return default
