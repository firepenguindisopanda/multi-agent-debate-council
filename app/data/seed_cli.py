"""CLI command to seed the database with agent templates."""

import click
from sqlmodel import Session, select

from app.database import engine
from app.models.agent import Agent
from app.data.seed_agents import AGENTS_DATA, get_seed_agents


@click.command()
def seed_agents():
    """Seed the database with predefined debate council agents."""
    click.echo("Seeding agents...")

    with Session(engine) as session:
        # Check if agents already exist
        existing = session.exec(select(Agent)).all()

        if existing:
            click.echo(f"Found {len(existing)} existing agents. Skipping seed.")
            click.echo("To re-seed, delete existing agents first.")
            return

        # Create new agents
        agents = get_seed_agents()
        for agent_data in AGENTS_DATA:
            agent = Agent(**agent_data)
            session.add(agent)
            click.echo(f"  Added: {agent.name} ({agent.role})")

        session.commit()
        click.echo(f"\nSuccessfully seeded {len(agents)} agents!")


@click.command()
def list_agents():
    """List all agents in the database."""
    with Session(engine) as session:
        agents = session.exec(select(Agent)).all()

        if not agents:
            click.echo("No agents found. Run 'seed-agents' first.")
            return

        click.echo(f"\nFound {len(agents)} agents:\n")
        for agent in agents:
            click.echo(f"  {agent.avatar or '•'} {agent.name} ({agent.role})")
            click.echo(f"     {agent.description}")
            click.echo()


@click.command()
def reset_agents():
    """Delete all agents and re-seed."""
    with Session(engine) as session:
        agents = session.exec(select(Agent)).all()
        for agent in agents:
            session.delete(agent)
        session.commit()

    click.echo(f"Deleted {len(agents)} agents. Re-seeding...")

    with Session(engine) as session:
        for agent_data in AGENTS_DATA:
            agent = Agent(**agent_data)
            session.add(agent)
            click.echo(f"  Added: {agent.name} ({agent.role})")
        session.commit()
        click.echo("\nSuccessfully reset agents!")


if __name__ == "__main__":
    seed_agents()
