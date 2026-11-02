"""Durable rate limits, budget reservations, and measured costs."""

import sqlalchemy as sa
from alembic import op

revision = "0002_limits_and_cost"
down_revision = "0001_initial_chat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chat_requests",
        sa.Column("reserved_cost_microusd", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("chat_requests", sa.Column("cost_microusd", sa.Integer()))
    op.create_table(
        "limit_buckets",
        sa.Column("key", sa.String(200), primary_key=True),
        sa.Column("value", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("limit_buckets")
    op.drop_column("chat_requests", "cost_microusd")
    op.drop_column("chat_requests", "reserved_cost_microusd")
