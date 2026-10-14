import logging
from contextlib import contextmanager

from sqlmodel import Session, SQLModel, create_engine

from app.config import get_settings

logger = logging.getLogger(__name__)


def _build_engine():
    settings = get_settings()
    kwargs = {"echo": False}
    if settings.database_uri.startswith("sqlite"):
        # Background debate tasks use their own sessions on the same thread pool.
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        kwargs.update(
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_additional_overflow,
            pool_timeout=settings.db_pool_timeout,
            pool_recycle=settings.db_pool_recycle,
            pool_pre_ping=True,
        )
    return create_engine(settings.database_uri, **kwargs)


engine = _build_engine()


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


def drop_all():
    SQLModel.metadata.drop_all(bind=engine)


def run_migrations():
    """Apply Alembic migrations up to head."""
    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")


def _session_generator():
    with Session(engine) as session:
        yield session


def get_session():
    yield from _session_generator()


@contextmanager
def get_cli_session():
    yield from _session_generator()
