"""Jinja environment, filters and helpers shared by HTML routes and the SSE stream."""

from datetime import datetime, timezone

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markdown_it import MarkdownIt
from markupsafe import Markup

from app.config import get_settings
from app.models import DebateStatus
from app.utilities.flash import get_flashed_messages
from app.utilities.timefmt import format_duration

_md = MarkdownIt("commonmark", {"html": False, "breaks": True}).enable("table")

STATUS_META = {
    DebateStatus.PENDING: ("Queued", "queued"),
    DebateStatus.IN_PROGRESS: ("Live", "live"),
    DebateStatus.COMPLETED: ("Completed", "done"),
    DebateStatus.STOPPED: ("Stopped", "stopped"),
    DebateStatus.FAILED: ("Failed", "failed"),
}


def markdown(text: str | None) -> Markup:
    return Markup(_md.render(text or ""))


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def timeago(value: datetime | None) -> str:
    if value is None:
        return ""
    seconds = int((datetime.now(timezone.utc) - _aware(value)).total_seconds())
    if seconds < 45:
        return "just now"
    for unit, size in (("day", 86400), ("hour", 3600), ("minute", 60)):
        if seconds >= size:
            n = seconds // size
            return f"{n} {unit}{'s' if n != 1 else ''} ago"
    return "just now"


def timeuntil(value: datetime | None) -> str:
    if value is None:
        return ""
    return format_duration(_aware(value) - datetime.now(timezone.utc))


def isodate(value: datetime | None) -> str:
    return _aware(value).isoformat() if value else ""


def role_slug(role: str) -> str:
    return "".join(ch for ch in role.lower() if ch.isalnum()) or "agent"


def status_label(status: DebateStatus) -> str:
    return STATUS_META[status][0]


def status_class(status: DebateStatus) -> str:
    return STATUS_META[status][1]


env = Environment(
    loader=FileSystemLoader("app/templates"),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)
env.globals.update(
    get_flashed_messages=get_flashed_messages,
    settings=get_settings(),
    DebateStatus=DebateStatus,
)
env.filters.update(
    markdown=markdown,
    timeago=timeago,
    timeuntil=timeuntil,
    isodate=isodate,
    role_slug=role_slug,
    status_label=status_label,
    status_class=status_class,
)


def render(name: str, **context) -> str:
    return env.get_template(name).render(**context)
