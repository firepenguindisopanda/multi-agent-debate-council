"""Runs a single debate: each round, every participant speaks in order, then the
moderator writes the consensus report. Progress is persisted and published as events."""

import asyncio
import logging
from typing import Callable

from sqlmodel import Session, select

from app.config import Settings
from app.database import engine as db_engine
from app.llm import ChatMessage, LLMClient, LLMError
from app.models import Debate, DebateStatus, Message, MessageStatus
from app.models.debate import utcnow
from app.services import prompts
from app.services.debate_events import (
    DebateEvent,
    DebateFinished,
    MessageCompleted,
    MessageStarted,
    StatusChanged,
    SummaryDelta,
    SummaryStarted,
    TokenDelta,
)

logger = logging.getLogger(__name__)

# Coalesce token deltas so the browser gets ~15 updates/s instead of one per token.
PUBLISH_INTERVAL = 0.06
# How often partial message content is written to the database while streaming.
PERSIST_INTERVAL = 1.0


class DebateEngine:
    def __init__(
        self,
        *,
        llm: LLMClient,
        publish: Callable[[DebateEvent], None],
        settings: Settings,
        session_factory: Callable[[], Session] | None = None,
    ):
        self.llm = llm
        self.publish = publish
        self.settings = settings
        self.session_factory = session_factory or (
            lambda: Session(db_engine, expire_on_commit=False)
        )

    async def run(self, debate_id: int) -> None:
        with self.session_factory() as db:
            debate = db.get(Debate, debate_id)
            if debate is None or debate.status != DebateStatus.PENDING:
                return
            participants = [p for p in debate.participants if p.is_active]
            council = [p.agent for p in participants]
            current: Message | None = None
            try:
                debate.status = DebateStatus.IN_PROGRESS
                for round_number in range(1, debate.max_rounds + 1):
                    debate.current_round = round_number
                    self._commit(db, debate)
                    self.publish(StatusChanged(debate_id, debate.status, round_number))
                    for participant in participants:
                        transcript = self._transcript(db, debate_id)
                        current = Message(
                            debate_id=debate_id,
                            agent_id=participant.agent_id,
                            participant_id=participant.id,
                            round_number=round_number,
                        )
                        self._commit(db, current)
                        self.publish(MessageStarted(debate_id, current.id, participant.agent_id))
                        turn = prompts.build_agent_turn(
                            agent=participant.agent,
                            topic=debate.topic,
                            council=council,
                            transcript=transcript,
                            round_number=round_number,
                            max_rounds=debate.max_rounds,
                        )
                        await self._stream_message(db, current, turn)
                        current.status = MessageStatus.COMPLETE
                        current.updated_at = utcnow()
                        self._commit(db, current)
                        self.publish(MessageCompleted(debate_id, current.id))
                        current = None

                self.publish(SummaryStarted(debate_id))
                debate.summary = await self._stream_summary(
                    debate_id,
                    prompts.build_moderator_turn(
                        topic=debate.topic,
                        council=council,
                        transcript=self._transcript(db, debate_id),
                    ),
                )
                self._finish(db, debate, DebateStatus.COMPLETED)
            except asyncio.CancelledError:
                self._close_partial(db, current)
                self._finish(db, debate, DebateStatus.STOPPED)
                raise
            except LLMError as e:
                logger.warning("Debate %s failed: %s", debate_id, e)
                self._close_partial(db, current)
                self._finish(db, debate, DebateStatus.FAILED, error=str(e))
            except Exception:
                logger.exception("Debate %s crashed", debate_id)
                self._close_partial(db, current)
                self._finish(db, debate, DebateStatus.FAILED, error="Unexpected server error.")

    async def _stream_message(self, db: Session, message: Message, turn: list[ChatMessage]) -> None:
        loop = asyncio.get_running_loop()
        last_publish = last_persist = loop.time()
        pending = ""
        async for delta in self.llm.stream_chat(turn, max_tokens=self.settings.llm_max_tokens):
            message.content += delta
            pending += delta
            now = loop.time()
            if now - last_publish >= PUBLISH_INTERVAL:
                self.publish(TokenDelta(message.debate_id, message.id, pending))
                pending, last_publish = "", now
            if now - last_persist >= PERSIST_INTERVAL:
                self._commit(db, message)
                last_persist = now
        if pending:
            self.publish(TokenDelta(message.debate_id, message.id, pending))
        if not message.content.strip():
            message.content = "_(No response.)_"

    async def _stream_summary(self, debate_id: int, turn: list[ChatMessage]) -> str:
        loop = asyncio.get_running_loop()
        last_publish = loop.time()
        text, pending = "", ""
        async for delta in self.llm.stream_chat(
            turn, max_tokens=self.settings.llm_summary_max_tokens
        ):
            text += delta
            pending += delta
            if loop.time() - last_publish >= PUBLISH_INTERVAL:
                self.publish(SummaryDelta(debate_id, pending))
                pending, last_publish = "", loop.time()
        if pending:
            self.publish(SummaryDelta(debate_id, pending))
        return text.strip()

    @staticmethod
    def _transcript(db: Session, debate_id: int) -> list[Message]:
        return list(
            db.exec(
                select(Message)
                .where(Message.debate_id == debate_id, Message.status == MessageStatus.COMPLETE)
                .order_by(Message.id)
            ).all()
        )

    @staticmethod
    def _commit(db: Session, obj) -> None:
        db.add(obj)
        db.commit()
        db.refresh(obj)

    def _close_partial(self, db: Session, message: Message | None) -> None:
        if message is None:
            return
        if message.content.strip():
            message.status = MessageStatus.COMPLETE
            message.updated_at = utcnow()
            db.add(message)
        else:
            db.delete(message)
        db.commit()

    def _finish(self, db: Session, debate: Debate, status: DebateStatus, error: str | None = None):
        debate.status = status
        debate.error = error
        debate.completed_at = utcnow()
        self._commit(db, debate)
        self.publish(DebateFinished(debate.id, status))
