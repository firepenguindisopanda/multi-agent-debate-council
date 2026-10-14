from fastapi import Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.dependencies import OptionalUserDep, SessionDep
from app.repositories.debate import AgentRepository

from . import router, templates


@router.get("/", response_class=HTMLResponse)
async def index_view(request: Request, user: OptionalUserDep, db: SessionDep):
    if user:
        return RedirectResponse(
            url=request.url_for("debates_view"), status_code=status.HTTP_303_SEE_OTHER
        )
    return templates.TemplateResponse(
        request=request,
        name="landing.html",
        context={"agents": AgentRepository(db).list_all()},
    )


@router.get("/app", include_in_schema=False)
async def legacy_app_redirect(request: Request):
    return RedirectResponse(
        url=request.url_for("debates_view"), status_code=status.HTTP_301_MOVED_PERMANENTLY
    )
