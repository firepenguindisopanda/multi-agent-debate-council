"""timezone-aware timestamps

Revision ID: 5b1d0c3e9a21
Revises: fe07e7502366
Create Date: 2026-10-14 13:00:00.000000

The models store aware UTC datetimes (SQLModel's UTCDateTime, i.e. TIMESTAMP WITH
TIME ZONE), but earlier migrations created plain TIMESTAMP columns. On Postgres that
shifts values whenever the server's TimeZone isn't UTC. SQLite has no timezone type,
so this is a no-op there.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "5b1d0c3e9a21"
down_revision: Union[str, Sequence[str], None] = "fe07e7502366"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLUMNS = [
    ("debate", "created_at", False),
    ("debate", "completed_at", True),
    ("message", "created_at", False),
    ("message", "updated_at", False),
]


def upgrade() -> None:
    """Upgrade schema."""
    if op.get_bind().dialect.name != "postgresql":
        return
    for table, column, nullable in COLUMNS:
        # Existing naive values were written as UTC.
        op.alter_column(
            table,
            column,
            type_=sa.DateTime(timezone=True),
            existing_type=sa.DateTime(),
            existing_nullable=nullable,
            postgresql_using=f"{column} AT TIME ZONE 'UTC'",
        )


def downgrade() -> None:
    """Downgrade schema."""
    if op.get_bind().dialect.name != "postgresql":
        return
    for table, column, nullable in COLUMNS:
        op.alter_column(
            table,
            column,
            type_=sa.DateTime(),
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=nullable,
            postgresql_using=f"{column} AT TIME ZONE 'UTC'",
        )
