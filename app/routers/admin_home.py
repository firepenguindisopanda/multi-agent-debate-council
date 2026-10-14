from fastapi import Request
from fastapi.responses import HTMLResponse

from app.dependencies import AdminDep, SessionDep
from app.models import DebateStatus
from app.repositories.debate import DebateRepository
from app.repositories.user import UserRepository

from . import router, templates


@router.get("/admin", response_class=HTMLResponse)
async def admin_home_view(request: Request, user: AdminDep, db: SessionDep):
    debates = DebateRepository(db)
    counts = debates.status_counts(None)
    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={
            "user": user,
            "users": UserRepository(db).get_all_users(),
            "recent": debates.list_for_user(None, limit=10),
            "stats": {
                "total": sum(counts.values()),
                "completed": counts.get(DebateStatus.COMPLETED, 0),
                "failed": counts.get(DebateStatus.FAILED, 0),
            },
        },
    )
