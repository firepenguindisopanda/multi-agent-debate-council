"""Runs debates as background asyncio tasks and fans their events out to subscribers.

State is in-process: run the app with a single worker (or swap this for a Redis-backed
broker if you need several)."""

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass

from app.config import get_settings
from app.llm import LLMClient, get_llm_client
from app.services.debate_engine import DebateEngine
from app.services.debate_events import (
    DebateEvent,
    MessageCompleted,
    MessageStarted,
    SummaryDelta,
    SummaryStarted,
    TokenDelta,
)

logger = logging.getLogger(__name__)


@dataclass
class LiveState:
    """What a debate is producing right now that isn't fully persisted yet."""

    message_id: int | None = None
    message_text: str = ""
    summary_text: str | None = None


class DebateRunner:
    def __init__(self, llm: LLMClient | None = None, max_concurrent: int | None = None):
        self._llm = llm
        self._tasks: dict[int, asyncio.Task] = {}
        self._subscribers: dict[int, set[asyncio.Queue]] = defaultdict(set)
        self._live: dict[int, LiveState] = {}
        self._slots = asyncio.Semaphore(max_concurrent or get_settings().max_concurrent_debates)

    @property
    def llm(self) -> LLMClient:
        return self._llm or get_llm_client()

    @property
    def is_ready(self) -> bool:
        """Whether a model provider is configured."""
        return self._llm is not None or get_settings().llm_configured

    def is_running(self, debate_id: int) -> bool:
        return debate_id in self._tasks

    def live_state(self, debate_id: int) -> LiveState | None:
        return self._live.get(debate_id)

    def start(self, debate_id: int) -> None:
        if debate_id in self._tasks:
            return
        self._live[debate_id] = LiveState()
        self._tasks[debate_id] = asyncio.create_task(
            self._run(debate_id), name=f"debate-{debate_id}"
        )

    async def _run(self, debate_id: int) -> None:
        try:
            async with self._slots:
                engine = DebateEngine(llm=self.llm, publish=self.publish, settings=get_settings())
                await engine.run(debate_id)
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Debate task %s crashed", debate_id)
        finally:
            self._tasks.pop(debate_id, None)
            self._live.pop(debate_id, None)
            for queue in self._subscribers.get(debate_id, ()):
                queue.put_nowait(None)  # end-of-stream marker

    async def stop(self, debate_id: int) -> bool:
        task = self._tasks.get(debate_id)
        if task is None:
            return False
        task.cancel()
        await asyncio.wait({task})
        return True

    def subscribe(self, debate_id: int) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers[debate_id].add(queue)
        return queue

    def unsubscribe(self, debate_id: int, queue: asyncio.Queue) -> None:
        subs = self._subscribers.get(debate_id)
        if subs is not None:
            subs.discard(queue)
            if not subs:
                del self._subscribers[debate_id]

    def publish(self, event: DebateEvent) -> None:
        live = self._live.get(event.debate_id)
        if live is not None:
            if isinstance(event, MessageStarted):
                live.message_id, live.message_text = event.message_id, ""
            elif isinstance(event, TokenDelta):
                live.message_text += event.text
            elif isinstance(event, MessageCompleted):
                live.message_id, live.message_text = None, ""
            elif isinstance(event, SummaryStarted):
                live.summary_text = ""
            elif isinstance(event, SummaryDelta):
                live.summary_text = (live.summary_text or "") + event.text
        for queue in self._subscribers.get(event.debate_id, ()):
            queue.put_nowait(event)

    async def shutdown(self) -> None:
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.wait(tasks)
