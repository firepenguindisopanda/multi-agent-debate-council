"""HTML pages for debates, progressively enhanced with htmx."""

from fastapi import Form, Request, status
from fastapi.responses import (
    HTMLResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)

from app.dependencies import AuthDep, DebateServiceDep, RunnerDep
from app.models import DebateStatus
from app.services import prompts
from app.services.debate_service import MAX_ROUNDS
from app.services.errors import ServiceError
from app.utilities.flash import flash
from app.web.stream import debate_event_stream, page_context

from . import router, templates

TOPIC_EXAMPLES = [
    "A mobile app that lets university students book study rooms and see live occupancy.",
    "Add single sign-on (Google + Microsoft) to our internal HR portal within one quarter.",
    "A real-time dashboard for a small logistics company to track 200 delivery vans.",
    "Migrate a monolithic e-commerce site to microservices without downtime.",
]


def _is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


def _parse_status(value: str) -> DebateStatus | None:
    try:
        return DebateStatus(value) if value else None
    except ValueError:
        return None


def _list_context(service, user, q: str, status_filter: str) -> dict:
    debates = service.list_for_user(user, query=q, status=_parse_status(status_filter))
    return {
        "debates": debates,
        "message_counts": service.debates.message_counts([d.id for d in debates]),
        "q": q,
        "status_filter": status_filter,
        "has_active": any(d.status.is_active for d in debates),
    }


@router.get("/debates", response_class=HTMLResponse)
async def debates_view(
    request: Request, user: AuthDep, service: DebateServiceDep, q: str = "", status: str = ""
):
    return templates.TemplateResponse(
        request=request,
        name="debates/index.html",
        context={
            "user": user,
            "stats": service.stats_for_user(user),
            **_list_context(service, user, q, status),
        },
    )


@router.get("/debates/list", response_class=HTMLResponse)
async def debates_list_partial(
    request: Request, user: AuthDep, service: DebateServiceDep, q: str = "", status: str = ""
):
    return templates.TemplateResponse(
        request=request, name="debates/_list.html", context=_list_context(service, user, q, status)
    )


@router.get("/debates/new", response_class=HTMLResponse)
async def new_debate_view(
    request: Request, user: AuthDep, service: DebateServiceDep, runner: RunnerDep
):
    agents = service.list_agents()
    return templates.TemplateResponse(
        request=request,
        name="debates/new.html",
        context={
            "user": user,
            "agents": agents,
            "selected_ids": [a.id for a in agents[:4]],
            "max_rounds": MAX_ROUNDS,
            "rounds": 2,
            "topic": "",
            "examples": TOPIC_EXAMPLES,
            "provider_ready": runner.is_ready,
        },
    )


@router.post("/debates", response_class=HTMLResponse)
async def create_debate_action(
    request: Request,
    user: AuthDep,
    service: DebateServiceDep,
    topic: str = Form(default=""),
    agent_ids: list[int] = Form(default=[]),
    max_rounds: int = Form(default=2),
):
    try:
        debate = service.create_and_start(
            user, topic=topic, agent_ids=agent_ids, max_rounds=max_rounds
        )
    except ServiceError as e:
        if _is_htmx(request):
            return templates.TemplateResponse(
                request=request,
                name="partials/form_error.html",
                context={"message": e.message},
                status_code=422,
            )
        flash(request, e.message, "danger")
        return RedirectResponse(
            request.url_for("new_debate_view"), status_code=status.HTTP_303_SEE_OTHER
        )

    url = str(request.url_for("debate_view", debate_id=debate.id))
    if _is_htmx(request):
        return Response(status_code=204, headers={"HX-Redirect": url})
    return RedirectResponse(url, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/debates/{debate_id}", response_class=HTMLResponse)
async def debate_view(
    request: Request, debate_id: int, user: AuthDep, service: DebateServiceDep, runner: RunnerDep
):
    debate = service.get_for_user(user, debate_id)
    ctx = page_context(request, debate, runner.live_state(debate_id))
    ctx.update(user=user, is_running=runner.is_running(debate_id))
    return templates.TemplateResponse(request=request, name="debates/show.html", context=ctx)


@router.get("/debates/{debate_id}/events")
async def debate_events(
    request: Request, debate_id: int, user: AuthDep, service: DebateServiceDep, runner: RunnerDep
):
    service.get_for_user(user, debate_id)  # authorisation
    return StreamingResponse(
        debate_event_stream(request, debate_id, runner),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/debates/{debate_id}/stop")
async def stop_debate_action(
    request: Request, debate_id: int, user: AuthDep, service: DebateServiceDep
):
    await service.stop(user, debate_id)
    if _is_htmx(request):
        # The live stream re-renders the page regions when the debate stops.
        return Response(status_code=204)
    return RedirectResponse(request.url_for("debate_view", debate_id=debate_id), status_code=303)


@router.delete("/debates/{debate_id}")
@router.post("/debates/{debate_id}/delete")
async def delete_debate_action(
    request: Request, debate_id: int, user: AuthDep, service: DebateServiceDep
):
    await service.delete(user, debate_id)
    url = str(request.url_for("debates_view"))
    if _is_htmx(request):
        if request.headers.get("HX-Target", "").startswith("debate-card-"):
            return HTMLResponse("")  # removes the card from the dashboard list
        return Response(status_code=204, headers={"HX-Redirect": url})
    flash(request, "Debate deleted.")
    return RedirectResponse(url, status_code=303)


@router.get("/debates/{debate_id}/export.md")
async def export_debate(debate_id: int, user: AuthDep, service: DebateServiceDep):
    debate = service.get_for_user(user, debate_id)
    council = ", ".join(f"{p.agent.name} ({p.agent.role})" for p in debate.participants)
    body = (
        f"# Council debate: {debate.topic}\n\n"
        f"- Status: {debate.status.value}\n- Rounds: {debate.max_rounds}\n- Council: {council}\n\n"
        f"## Council report\n\n{debate.summary or '_No report yet._'}\n\n"
        f"## Transcript\n\n{prompts.format_transcript(list(debate.messages))}\n"
    )
    return PlainTextResponse(
        body,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="debate-{debate.id}.md"'},
    )
