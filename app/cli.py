"""Management commands. Run with: python -m app.cli --help"""

import asyncio

import typer
from sqlmodel import select

from app.data import seed_agents as _seed_agents
from app.database import get_cli_session, run_migrations
from app.llm.check import run_check
from app.models import Agent
from app.repositories.user import UserRepository
from app.schemas.user import AdminCreate
from app.utilities.security import encrypt_password

cli = typer.Typer(help="Debate Council management commands", no_args_is_help=True)


@cli.command()
def migrate():
    """Apply database migrations."""
    run_migrations()
    typer.echo("Database is up to date.")


@cli.command("seed-agents")
def seed_agents():
    """Add any missing predefined council agents."""
    with get_cli_session() as db:
        added = _seed_agents(db)
    typer.echo(f"Added {len(added)} agent(s).")


@cli.command("list-agents")
def list_agents():
    """List council agents."""
    with get_cli_session() as db:
        for agent in db.exec(select(Agent).order_by(Agent.id)).all():
            typer.echo(f"{agent.avatar or '•'}  {agent.name} ({agent.role}) - {agent.description}")


@cli.command("nim-check")
def nim_check(
    model: str = typer.Option(None, help="Model to test instead of LLM_MODEL."),
):
    """Make one small live call to NVIDIA NIM and list judge-model candidates."""
    ok = asyncio.run(run_check(model, typer.echo))
    raise typer.Exit(0 if ok else 1)


@cli.command("create-admin")
def create_admin(
    username: str = typer.Option(..., prompt=True),
    email: str = typer.Option(..., prompt=True),
    password: str = typer.Option(..., prompt=True, hide_input=True, confirmation_prompt=True),
):
    """Create an admin user."""
    with get_cli_session() as db:
        UserRepository(db).create(
            AdminCreate(username=username, email=email, password=encrypt_password(password))
        )
    typer.echo(f"Admin '{username}' created.")


if __name__ == "__main__":
    cli()
