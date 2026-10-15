"""Runs a single debate: each round, every participant speaks in order, then the
moderator writes the consensus report. Progress is persisted and published as events."""

import asyncio
import logging
from dataclasses import asdict
from typing import AsyncIterator, Callable

from sqlalchemy import inspect
from sqlmodel import Session, select

from app.config import Settings
from app.database import engine as db_engine
from app.llm import CallStats, ChatMessage, LLMClient, LLMError
from app.models import Agent, Debate, DebateStatus, LLMCall, LLMCallKind, Message, MessageStatus
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
                self._record_provenance(debate, council)
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
                    db,
                    debate_id,
                    prompts.build_moderator_turn(
                        topic=debate.topic,
                        council=council,
                        transcript=self._transcript(db, debate_id),
                    ),
                )
                missing = prompts.missing_report_sections(debate.summary)
                if missing:
                    logger.warning("Debate %s report is missing sections: %s", debate_id, missing)
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
        async for delta in self._llm_call(
            db,
            message.debate_id,
            LLMCallKind.TURN,
            turn,
            max_tokens=self.settings.llm_max_tokens,
            message_id=message.id,
        ):
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

    async def _stream_summary(self, db: Session, debate_id: int, turn: list[ChatMessage]) -> str:
        loop = asyncio.get_running_loop()
        last_publish = loop.time()
        text, pending = "", ""
        async for delta in self._llm_call(
            db,
            debate_id,
            LLMCallKind.SUMMARY,
            turn,
            max_tokens=self.settings.llm_summary_max_tokens,
        ):
            text += delta
            pending += delta
            if loop.time() - last_publish >= PUBLISH_INTERVAL:
                self.publish(SummaryDelta(debate_id, pending))
                pending, last_publish = "", loop.time()
        if pending:
            self.publish(SummaryDelta(debate_id, pending))
        return text.strip()

    async def _llm_call(
        self,
        db: Session,
        debate_id: int,
        kind: LLMCallKind,
        turn: list[ChatMessage],
        *,
        max_tokens: int,
        message_id: int | None = None,
    ) -> AsyncIterator[str]:
        """Stream one completion and record an LLMCall row however it ends."""
        stats = CallStats()
        error = None
        try:
            async for delta in self.llm.stream_chat(turn, max_tokens=max_tokens, stats=stats):
                yield delta
        except BaseException as e:  # includes cancellation, which is recorded too
            error = type(e).__name__
            raise
        finally:
            # A failed turn's message may be deleted if it's empty, so don't link to it.
            self._record_call(db, debate_id, kind, stats, message_id if not error else None, error)

    def _record_call(
        self,
        db: Session,
        debate_id: int,
        kind: LLMCallKind,
        stats: CallStats,
        message_id: int | None,
        error: str | None,
    ) -> None:
        logger.info(
            "llm_call debate=%s kind=%s model=%s input_tokens=%s output_tokens=%s finish=%s "
            "ttft_ms=%s duration_ms=%s retries=%s error=%s",
            debate_id,
            kind.value,
            stats.response_model or stats.request_model,
            stats.input_tokens,
            stats.output_tokens,
            stats.finish_reason,
            stats.time_to_first_chunk_ms,
            stats.duration_ms,
            stats.retries,
            error,
        )
        if stats.finish_reason == "length":
            logger.warning("Debate %s %s was cut off by max_tokens", debate_id, kind.value)
        call = LLMCall(
            debate_id=debate_id, message_id=message_id, kind=kind, error=error, **asdict(stats)
        )
        try:
            self._commit(db, call)
        except Exception:
            # Metrics must never take a debate down with them.
            logger.exception("Could not record LLM call for debate %s", debate_id)
            db.rollback()

    def _record_provenance(self, debate: Debate, council: list[Agent]) -> None:
        s = self.settings
        debate.llm_model = getattr(self.llm, "model", s.llm_model)
        debate.llm_temperature = getattr(self.llm, "temperature", s.llm_temperature)
        debate.llm_top_p = getattr(self.llm, "top_p", s.llm_top_p)
        debate.llm_max_tokens = s.llm_max_tokens
        debate.llm_summary_max_tokens = s.llm_summary_max_tokens
        debate.prompt_version = prompts.prompt_version(council)

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
        # No refresh: it would open a new transaction and hold a connection while the
        # model streams. expire_on_commit=False keeps the in-memory state valid.
        db.add(obj)
        db.commit()

    def _close_partial(self, db: Session, message: Message | None) -> None:
        """Reset the session after an interruption and keep whatever was said so far."""
        text = message.content if message is not None else ""
        db.rollback()  # clears a failed transaction; expires (reloads) all objects
        if message is None or not inspect(message).persistent:
            return
        if text.strip():
            message.content = text
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
