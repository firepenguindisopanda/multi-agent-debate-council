from fastapi import Request, status
from fastapi.responses import RedirectResponse

from app.utilities.security import clear_auth_cookie

from . import router


@router.api_route("/logout", methods=["GET", "POST"])
async def logout(request: Request):
    response = RedirectResponse(
        url=request.url_for("login_view"), status_code=status.HTTP_303_SEE_OTHER
    )
    clear_auth_cookie(response)
    return response
