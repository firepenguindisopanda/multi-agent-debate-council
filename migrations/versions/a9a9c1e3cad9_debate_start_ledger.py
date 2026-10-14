"""debate start ledger for the daily debate limit

Revision ID: a9a9c1e3cad9
Revises: 5b1d0c3e9a21
Create Date: 2026-10-14 14:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a9a9c1e3cad9"
down_revision: Union[str, Sequence[str], None] = "5b1d0c3e9a21"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "debate_start",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_debate_start_user_id_created_at", "debate_start", ["user_id", "created_at"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_debate_start_user_id_created_at", table_name="debate_start")
    op.drop_table("debate_start")
