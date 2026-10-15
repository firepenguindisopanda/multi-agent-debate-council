"""JSON API for debates. The HTML pages use the same DebateService."""

from dataclasses import asdict

from fastapi import Response, status

from app.dependencies import AuthDep, DebateServiceDep
from app.models import Debate, DebateStatus
from app.schemas.debate import (
    AgentRead,
    DebateCreate,
    DebateDetail,
    DebateListItem,
    RunStatsRead,
)
from app.services.run_stats import summarize

from . import api_router


def _detail(debate: Debate) -> DebateDetail:
    detail = DebateDetail.model_validate(debate, from_attributes=True)
    run = summarize(debate)
    return detail.model_copy(update={"run": RunStatsRead(**asdict(run)) if run else None})


@api_router.get("/agents", response_model=list[AgentRead])
async def api_list_agents(user: AuthDep, service: DebateServiceDep):
    return service.list_agents()


@api_router.get("/debates", response_model=list[DebateListItem])
async def api_list_debates(
    user: AuthDep, service: DebateServiceDep, q: str = "", status: DebateStatus | None = None
):
    return service.list_for_user(user, query=q, status=status)


@api_router.post("/debates", response_model=DebateDetail, status_code=status.HTTP_201_CREATED)
async def api_create_debate(payload: DebateCreate, user: AuthDep, service: DebateServiceDep):
    return _detail(
        service.create_and_start(
            user, topic=payload.topic, agent_ids=payload.agent_ids, max_rounds=payload.max_rounds
        )
    )


@api_router.get("/debates/{debate_id}", response_model=DebateDetail)
async def api_get_debate(debate_id: int, user: AuthDep, service: DebateServiceDep):
    return _detail(service.get_for_user(user, debate_id))


@api_router.post("/debates/{debate_id}/stop", response_model=DebateDetail)
async def api_stop_debate(debate_id: int, user: AuthDep, service: DebateServiceDep):
    return _detail(await service.stop(user, debate_id))


@api_router.delete("/debates/{debate_id}", status_code=status.HTTP_204_NO_CONTENT)
async def api_delete_debate(debate_id: int, user: AuthDep, service: DebateServiceDep):
    await service.delete(user, debate_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
