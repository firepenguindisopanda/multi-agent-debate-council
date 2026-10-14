from datetime import datetime

from sqlalchemy import func
from sqlmodel import Session, col, select

from app.models import (
    Agent,
    Debate,
    DebateParticipant,
    DebateStart,
    DebateStatus,
    Message,
    MessageStatus,
)
from app.models.debate import utcnow


class AgentRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_all(self) -> list[Agent]:
        return list(self.db.exec(select(Agent).order_by(Agent.id)).all())

    def get_many(self, ids: list[int]) -> list[Agent]:
        agents = {a.id: a for a in self.db.exec(select(Agent).where(col(Agent.id).in_(ids))).all()}
        return [agents[i] for i in ids if i in agents]


class DebateRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, *, topic: str, max_rounds: int, user_id: int, agents: list[Agent]) -> Debate:
        debate = Debate(topic=topic, max_rounds=max_rounds, created_by_user_id=user_id)
        debate.participants = [
            DebateParticipant(agent_id=agent.id, order=i) for i, agent in enumerate(agents)
        ]
        self.db.add(debate)
        self.db.add(DebateStart(user_id=user_id))  # same transaction as the debate
        self.db.commit()
        self.db.refresh(debate)
        return debate

    def starts_since(self, user_id: int, since: datetime) -> list[datetime]:
        """When the user started debates since `since`, oldest first."""
        stmt = (
            select(DebateStart.created_at)
            .where(DebateStart.user_id == user_id, DebateStart.created_at >= since)
            .order_by(col(DebateStart.created_at))
        )
        return list(self.db.exec(stmt).all())

    def get(self, debate_id: int) -> Debate | None:
        return self.db.get(Debate, debate_id)

    def list_for_user(
        self,
        user_id: int | None,
        *,
        query: str = "",
        status: DebateStatus | None = None,
        limit: int = 50,
    ) -> list[Debate]:
        stmt = select(Debate).order_by(col(Debate.created_at).desc()).limit(limit)
        if user_id is not None:
            stmt = stmt.where(Debate.created_by_user_id == user_id)
        if query:
            stmt = stmt.where(col(Debate.topic).ilike(f"%{query}%"))
        if status is not None:
            stmt = stmt.where(Debate.status == status)
        return list(self.db.exec(stmt).all())

    def status_counts(self, user_id: int | None) -> dict[DebateStatus, int]:
        stmt = select(Debate.status, func.count()).group_by(Debate.status)
        if user_id is not None:
            stmt = stmt.where(Debate.created_by_user_id == user_id)
        return {status: count for status, count in self.db.exec(stmt).all()}

    def message_counts(self, debate_ids: list[int]) -> dict[int, int]:
        if not debate_ids:
            return {}
        stmt = (
            select(Message.debate_id, func.count())
            .where(col(Message.debate_id).in_(debate_ids))
            .group_by(Message.debate_id)
        )
        return dict(self.db.exec(stmt).all())

    def save(self, debate: Debate) -> Debate:
        self.db.add(debate)
        self.db.commit()
        self.db.refresh(debate)
        return debate

    def delete(self, debate: Debate) -> None:
        self.db.delete(debate)
        self.db.commit()

    def fail_interrupted(self) -> int:
        """Mark debates left running by a previous process as failed."""
        debates = self.db.exec(
            select(Debate).where(
                col(Debate.status).in_([DebateStatus.PENDING, DebateStatus.IN_PROGRESS])
            )
        ).all()
        for debate in debates:
            debate.status = DebateStatus.FAILED
            debate.error = "Interrupted by a server restart."
            debate.completed_at = utcnow()
            for message in debate.messages:
                if message.status == MessageStatus.STREAMING:
                    message.status = MessageStatus.COMPLETE
            self.db.add(debate)
        self.db.commit()
        return len(debates)
