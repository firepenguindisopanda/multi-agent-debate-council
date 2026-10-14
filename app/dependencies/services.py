from typing import Annotated

from fastapi import Depends, Request

from app.dependencies.session import SessionDep
from app.repositories.debate import AgentRepository, DebateRepository
from app.services.debate_runner import DebateRunner
from app.services.debate_service import DebateService


def get_runner(request: Request) -> DebateRunner:
    return request.app.state.runner


def get_debate_service(request: Request, db: SessionDep) -> DebateService:
    return DebateService(DebateRepository(db), AgentRepository(db), get_runner(request))


RunnerDep = Annotated[DebateRunner, Depends(get_runner)]
DebateServiceDep = Annotated[DebateService, Depends(get_debate_service)]
