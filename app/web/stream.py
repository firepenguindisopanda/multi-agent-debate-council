"""Turns debate events into HTML fragments for the htmx SSE extension.

Every `update` event carries out-of-band swaps (hx-swap-oob) that patch specific
regions of the debate page; the final `done` event tells htmx to close the stream."""

import asyncio
from typing import AsyncIterator

from fastapi import Request
from markupsafe import escape
from sqlmodel import Session

from app.database import engine
from app.models import Debate, Message
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
from app.services.debate_runner import DebateRunner, LiveState
from app.web.templating import render

HEARTBEAT_SECONDS = 15


def sse(event: str, data: str = "") -> str:
    lines = data.splitlines() or [""]
    return f"event: {event}\n" + "".join(f"data: {line}\n" for line in lines) + "\n"


def _oob(fragment: str, how: str = "true") -> str:
    """Mark the root element of a rendered fragment as an out-of-band swap."""
    tag_end = fragment.index(">")
    return f'{fragment[:tag_end]} hx-swap-oob="{how}"{fragment[tag_end:]}'


def _append_text(target: str, text: str) -> str:
    return f'<span hx-swap-oob="beforeend:{target}">{escape(text)}</span>'


def page_context(request: Request, debate: Debate, live: LiveState | None) -> dict:
    """Template context for the live regions of the debate page."""
    messages = list(debate.messages)
    speaking_id = None
    if live and live.message_id is not None:
        speaking_id = next((m.agent_id for m in messages if m.id == live.message_id), None)
    rounds: dict[int, list[Message]] = {}
    for m in messages:
        rounds.setdefault(m.round_number, []).append(m)
    if debate.current_round and debate.status.is_active:
        rounds.setdefault(debate.current_round, [])
    spoke = {}
    for m in messages:
        spoke[m.agent_id] = spoke.get(m.agent_id, 0) + 1
    return {
        "request": request,
        "debate": debate,
        "rounds": rounds,
        "live": live,
        "speaking_id": speaking_id,
        "spoke": spoke,
    }


def render_regions(ctx: dict) -> str:
    return "".join(
        _oob(render(name, **ctx))
        for name in (
            "debates/_header.html",
            "debates/_council.html",
            "debates/_transcript.html",
            "debates/_summary.html",
        )
    )


def _render_event(event: DebateEvent, request: Request, db: Session, runner: DebateRunner) -> str:
    if isinstance(event, TokenDelta):
        return _append_text(f"#msg-{event.message_id}-body", event.text)
    if isinstance(event, SummaryDelta):
        return _append_text("#summary-stream", event.text)

    db.expire_all()
    debate = db.get(Debate, event.debate_id)
    live = runner.live_state(event.debate_id)
    ctx = page_context(request, debate, live)
    header = _oob(render("debates/_header.html", **ctx))
    council = _oob(render("debates/_council.html", **ctx))
    if isinstance(event, StatusChanged):
        section = render(
            "debates/_round.html", **ctx, round_number=event.current_round, messages=[]
        )
        return header + council + f'<div hx-swap-oob="beforeend:#transcript">{section}</div>'
    if isinstance(event, MessageStarted):
        message = db.get(Message, event.message_id)
        card = render("debates/_message.html", **ctx, message=message, streaming=True)
        return (
            council
            + f'<div hx-swap-oob="beforeend:#round-{message.round_number}-messages">{card}</div>'
        )
    if isinstance(event, MessageCompleted):
        message = db.get(Message, event.message_id)
        return council + _oob(
            render("debates/_message.html", **ctx, message=message, streaming=False)
        )
    if isinstance(event, (SummaryStarted, DebateFinished)):
        return header + council + _oob(render("debates/_summary.html", **ctx))
    return ""


async def debate_event_stream(
    request: Request, debate_id: int, runner: DebateRunner
) -> AsyncIterator[str]:
    # Subscribe and snapshot without awaiting in between, so no event can slip through.
    queue = runner.subscribe(debate_id)
    try:
        with Session(engine, expire_on_commit=False) as db:
            debate = db.get(Debate, debate_id)
            if debate is None:
                yield sse("done")
                return
            yield sse(
                "update",
                render_regions(page_context(request, debate, runner.live_state(debate_id))),
            )
            if not runner.is_running(debate_id):
                yield sse("done")
                return
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), HEARTBEAT_SECONDS)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                if event is None:
                    break
                yield sse("update", _render_event(event, request, db, runner))
            db.expire_all()
            debate = db.get(Debate, debate_id)
            yield sse("update", render_regions(page_context(request, debate, None)))
            yield sse("done")
    finally:
        runner.unsubscribe(debate_id, queue)
