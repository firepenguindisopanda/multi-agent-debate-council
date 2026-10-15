"""llm call metrics and debate provenance

Revision ID: fa6a22b11636
Revises: a9a9c1e3cad9
Create Date: 2026-10-15 09:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "fa6a22b11636"
down_revision: Union[str, Sequence[str], None] = "a9a9c1e3cad9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "llm_call",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("debate_id", sa.Integer(), nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.Enum("TURN", "SUMMARY", name="llmcallkind"), nullable=False),
        sa.Column("request_model", sa.String(length=200), nullable=True),
        sa.Column("response_model", sa.String(length=200), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("finish_reason", sa.String(length=40), nullable=True),
        sa.Column("time_to_first_chunk_ms", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("retries", sa.Integer(), nullable=False),
        sa.Column("error", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["debate_id"], ["debate.id"]),
        sa.ForeignKeyConstraint(["message_id"], ["message.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_llm_call_debate_id", "llm_call", ["debate_id"])

    with op.batch_alter_table("debate", schema=None) as batch_op:
        batch_op.add_column(sa.Column("llm_model", sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column("llm_temperature", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("llm_top_p", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("llm_max_tokens", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("llm_summary_max_tokens", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("prompt_version", sa.String(length=40), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("debate", schema=None) as batch_op:
        batch_op.drop_column("prompt_version")
        batch_op.drop_column("llm_summary_max_tokens")
        batch_op.drop_column("llm_max_tokens")
        batch_op.drop_column("llm_top_p")
        batch_op.drop_column("llm_temperature")
        batch_op.drop_column("llm_model")

    op.drop_index("ix_llm_call_debate_id", table_name="llm_call")
    op.drop_table("llm_call")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS llmcallkind")
