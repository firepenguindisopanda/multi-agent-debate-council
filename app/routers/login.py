from typing import Annotated

from fastapi import Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm

from app.dependencies import OptionalUserDep, SessionDep
from app.repositories.user import UserRepository
from app.schemas.auth import TokenResponse
from app.services.auth_service import AuthService
from app.utilities.security import safe_next_url, set_auth_cookie

from . import api_router, router, templates


@router.get("/login", response_class=HTMLResponse)
async def login_view(request: Request, user: OptionalUserDep, next: str | None = None):
    if user:
        return RedirectResponse(safe_next_url(next), status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request=request, name="auth/login.html", context={"next": next or ""}
    )


@router.post("/login", response_class=HTMLResponse)
async def login_action(
    db: SessionDep,
    request: Request,
    username: str = Form(),
    password: str = Form(),
    next: str = Form(default=""),
):
    access_token = AuthService(UserRepository(db)).authenticate_user(username, password)
    if not access_token:
        return templates.TemplateResponse(
            request=request,
            name="auth/login.html",
            context={
                "error": "Incorrect username or password.",
                "username": username,
                "next": next,
            },
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    response = RedirectResponse(url=safe_next_url(next), status_code=status.HTTP_303_SEE_OTHER)
    set_auth_cookie(response, access_token)
    return response


@api_router.post("/auth/token", response_model=TokenResponse)
async def issue_token(db: SessionDep, form: Annotated[OAuth2PasswordRequestForm, Depends()]):
    """Exchange username/password for a bearer token (for API clients)."""
    token = AuthService(UserRepository(db)).authenticate_user(form.username, form.password)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password"
        )
    return TokenResponse(access_token=token)
