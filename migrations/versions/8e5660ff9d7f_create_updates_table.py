"""create updates table

Revision ID: 8e5660ff9d7f
Revises: 2ae062d3817c
Create Date: 2026-06-21 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8e5660ff9d7f"
down_revision: Union[str, None] = "2ae062d3817c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "updates",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("goal_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.Column(
            "source",
            sa.Text(),
            nullable=False,
            server_default="coaching_update",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["auth.users.id"], name="updates_user_id_fkey", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["goal_id"], ["goals.id"], name="updates_goal_id_fkey", ondelete="CASCADE"
        ),
        sa.CheckConstraint(
            "source IN ('coaching_update', 'checkin')", name="updates_source_check"
        ),
    )
    op.create_index("ix_updates_goal_id_created_at", "updates", ["goal_id", "created_at"])
    op.execute("ALTER TABLE updates ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY updates_select_own ON updates
        FOR SELECT
        USING (auth.uid() = user_id)
        """
    )
    op.execute(
        """
        CREATE POLICY updates_insert_own ON updates
        FOR INSERT
        WITH CHECK (
            auth.uid() = user_id
            AND EXISTS (
                SELECT 1 FROM goals g
                WHERE g.id = goal_id
                AND g.user_id = auth.uid()
                AND g.deleted_at IS NULL
            )
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS updates_insert_own ON updates")
    op.execute("DROP POLICY IF EXISTS updates_select_own ON updates")
    op.drop_index("ix_updates_goal_id_created_at", table_name="updates")
    op.drop_table("updates")
