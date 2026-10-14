from app.models import Agent, Debate, DebateStatus, User
from app.models.debate import utcnow
from app.repositories.debate import AgentRepository, DebateRepository
from app.services.debate_runner import DebateRunner
from app.services.errors import (
    ConflictError,
    InvalidInputError,
    NotFoundError,
    ProviderNotConfiguredError,
)

MIN_TOPIC_LENGTH = 10
MAX_TOPIC_LENGTH = 500
MIN_AGENTS = 2
MAX_ROUNDS = 5


class DebateService:
    def __init__(self, debates: DebateRepository, agents: AgentRepository, runner: DebateRunner):
        self.debates = debates
        self.agents = agents
        self.runner = runner

    def list_agents(self) -> list[Agent]:
        return self.agents.list_all()

    def create_and_start(
        self, user: User, *, topic: str, agent_ids: list[int], max_rounds: int
    ) -> Debate:
        topic = " ".join(topic.split())
        if not MIN_TOPIC_LENGTH <= len(topic) <= MAX_TOPIC_LENGTH:
            raise InvalidInputError(
                f"Describe the topic in {MIN_TOPIC_LENGTH}-{MAX_TOPIC_LENGTH} characters."
            )
        if not 1 <= max_rounds <= MAX_ROUNDS:
            raise InvalidInputError(f"Rounds must be between 1 and {MAX_ROUNDS}.")
        agents = self.agents.get_many(list(dict.fromkeys(agent_ids)))
        if len(agents) < MIN_AGENTS:
            raise InvalidInputError(f"Pick at least {MIN_AGENTS} council members.")
        if not self.runner.is_ready:
            raise ProviderNotConfiguredError(
                "No model provider is configured. Set NVIDIA_API_KEY in .env and restart."
            )
        debate = self.debates.create(
            topic=topic, max_rounds=max_rounds, user_id=user.id, agents=agents
        )
        self.runner.start(debate.id)
        return debate

    def get_for_user(self, user: User, debate_id: int) -> Debate:
        debate = self.debates.get(debate_id)
        if debate is None or (debate.created_by_user_id != user.id and user.role != "admin"):
            raise NotFoundError("Debate not found.")
        return debate

    def list_for_user(
        self, user: User, *, query: str = "", status: DebateStatus | None = None
    ) -> list[Debate]:
        return self.debates.list_for_user(user.id, query=query.strip(), status=status)

    def stats_for_user(self, user: User) -> dict[str, int]:
        counts = self.debates.status_counts(user.id)
        return {
            "total": sum(counts.values()),
            "completed": counts.get(DebateStatus.COMPLETED, 0),
            "active": counts.get(DebateStatus.IN_PROGRESS, 0) + counts.get(DebateStatus.PENDING, 0),
            "stopped": counts.get(DebateStatus.STOPPED, 0) + counts.get(DebateStatus.FAILED, 0),
        }

    async def stop(self, user: User, debate_id: int) -> Debate:
        debate = self.get_for_user(user, debate_id)
        if not debate.status.is_active:
            raise ConflictError("This debate has already finished.")
        await self.runner.stop(debate_id)
        self.debates.db.refresh(debate)
        if debate.status.is_active:
            # The engine never started (still queued, or lost in a restart): close it here.
            debate.status = DebateStatus.STOPPED
            debate.completed_at = utcnow()
            self.debates.save(debate)
        return debate

    async def delete(self, user: User, debate_id: int) -> None:
        debate = self.get_for_user(user, debate_id)
        await self.runner.stop(debate_id)
        self.debates.db.refresh(debate)
        self.debates.delete(debate)
