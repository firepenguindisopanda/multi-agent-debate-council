"""debate summary, error and failed status

Revision ID: fe07e7502366
Revises: 46ec214b784e
Create Date: 2026-10-14 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "fe07e7502366"
down_revision: Union[str, Sequence[str], None] = "46ec214b784e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # SQLite stores enums as plain VARCHAR; Postgres needs the new label added.
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TYPE debatestatus ADD VALUE IF NOT EXISTS 'FAILED'")

    with op.batch_alter_table("debate", schema=None) as batch_op:
        batch_op.add_column(sa.Column("summary", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("error", sa.String(length=1000), nullable=True))
        batch_op.create_index(
            batch_op.f("ix_debate_created_by_user_id"), ["created_by_user_id"], unique=False
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("debate", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_debate_created_by_user_id"))
        batch_op.drop_column("error")
        batch_op.drop_column("summary")
