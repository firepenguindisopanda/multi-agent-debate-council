from fastapi import Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError

from app.dependencies import SessionDep
from app.repositories.user import UserRepository
from app.schemas.auth import SignupRequest
from app.services.auth_service import AuthService
from app.services.errors import ConflictError
from app.utilities.flash import flash

from . import router, templates


@router.get("/register", response_class=HTMLResponse)
async def register_view(request: Request):
    return templates.TemplateResponse(request=request, name="auth/register.html")


@router.post("/register", response_class=HTMLResponse)
def signup_user(
    request: Request,
    db: SessionDep,
    username: str = Form(),
    email: str = Form(),
    password: str = Form(),
):
    try:
        signup = SignupRequest.model_validate(
            {"username": username, "email": email, "password": password}
        )
        AuthService(UserRepository(db)).register_user(signup)
    except ValidationError as e:
        error = e.errors()[0]["msg"].removeprefix("Value error, ")
    except ConflictError as e:
        error = e.message
    else:
        flash(request, "Account created. Sign in to convene your first council.")
        return RedirectResponse(
            url=request.url_for("login_view"), status_code=status.HTTP_303_SEE_OTHER
        )
    return templates.TemplateResponse(
        request=request,
        name="auth/register.html",
        context={"error": error, "username": username, "email": email},
        status_code=422,
    )
