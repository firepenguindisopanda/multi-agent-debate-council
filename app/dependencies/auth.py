from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from jwt.exceptions import InvalidTokenError

from app.config import get_settings
from app.dependencies.session import SessionDep
from app.models.user import User
from app.repositories.user import UserRepository

ACCESS_TOKEN_COOKIE = "access_token"


def _token_from_request(request: Request) -> str | None:
    token = request.cookies.get(ACCESS_TOKEN_COOKIE)
    if token:
        return token
    scheme, _, credentials = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() == "bearer" and credentials:
        return credentials
    return None


async def get_current_user(request: Request, db: SessionDep) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    token = _token_from_request(request)
    if token is None:
        raise credentials_exception
    try:
        payload = jwt.decode(
            token, get_settings().secret_key, algorithms=[get_settings().jwt_algorithm]
        )
        user_id = int(payload.get("sub"))
    except (InvalidTokenError, TypeError, ValueError):
        raise credentials_exception from None

    user = UserRepository(db).get_by_id(user_id)
    if user is None:
        raise credentials_exception
    return user


async def get_optional_user(request: Request, db: SessionDep) -> User | None:
    try:
        return await get_current_user(request, db)
    except HTTPException:
        return None


async def is_logged_in(request: Request, db: SessionDep) -> bool:
    return await get_optional_user(request, db) is not None


IsUserLoggedIn = Annotated[bool, Depends(is_logged_in)]
OptionalUserDep = Annotated[User | None, Depends(get_optional_user)]
AuthDep = Annotated[User, Depends(get_current_user)]


async def is_admin(user: User) -> bool:
    return user.role == "admin"


async def is_admin_dep(user: AuthDep) -> User:
    if not await is_admin(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to view this page.",
        )
    return user


AdminDep = Annotated[User, Depends(is_admin_dep)]
