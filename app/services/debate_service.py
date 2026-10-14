from dataclasses import dataclass
from datetime import datetime, timedelta

from app.models import Agent, Debate, DebateStatus, User
from app.models.debate import utcnow
from app.repositories.debate import AgentRepository, DebateRepository
from app.services.debate_runner import DebateRunner
from app.services.errors import (
    ConflictError,
    InvalidInputError,
    LimitExceededError,
    NotFoundError,
    ProviderNotConfiguredError,
)
from app.utilities.timefmt import format_duration

MIN_TOPIC_LENGTH = 10
MAX_TOPIC_LENGTH = 500
MIN_AGENTS = 2
MAX_ROUNDS = 5
LIMIT_WINDOW = timedelta(hours=24)


@dataclass(frozen=True)
class Usage:
    """A user's debate starts within the rolling limit window."""

    limit: int
    used: int
    next_available_at: datetime | None  # set only when the limit is reached

    @property
    def remaining(self) -> int:
        return max(self.limit - self.used, 0)


class DebateService:
    def __init__(
        self,
        debates: DebateRepository,
        agents: AgentRepository,
        runner: DebateRunner,
        daily_limit: int = 0,
    ):
        self.debates = debates
        self.agents = agents
        self.runner = runner
        self.daily_limit = daily_limit

    def usage_for(self, user: User) -> Usage | None:
        """None when the user has no limit (admins, or a limit of 0)."""
        if self.daily_limit <= 0 or user.role == "admin":
            return None
        starts = self.debates.starts_since(user.id, utcnow() - LIMIT_WINDOW)
        next_at = None
        if len(starts) >= self.daily_limit:
            # The next slot frees up when the oldest start that keeps us at the limit ages out.
            next_at = starts[len(starts) - self.daily_limit] + LIMIT_WINDOW
        return Usage(limit=self.daily_limit, used=len(starts), next_available_at=next_at)

    def _check_limit(self, user: User) -> None:
        usage = self.usage_for(user)
        if usage is None or usage.next_available_at is None:
            return
        wait = usage.next_available_at - utcnow()
        raise LimitExceededError(
            f"You've started {usage.limit} debate{'s' if usage.limit != 1 else ''} "
            "in the last 24 hours, the daily limit. "
            f"You can start another in {format_duration(wait)}.",
            retry_after_seconds=max(int(wait.total_seconds()), 1),
        )

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
        self._check_limit(user)
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
