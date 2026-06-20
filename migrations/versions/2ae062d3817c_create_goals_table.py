"""create goals table

Revision ID: 2ae062d3817c
Revises: 16b5eb4c9d06
Create Date: 2026-06-20 22:52:52.687632

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2ae062d3817c"
down_revision: Union[str, None] = "16b5eb4c9d06"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "goals",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["auth.users.id"], name="goals_user_id_fkey", ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_goals_user_id_deleted_at", "goals", ["user_id", "deleted_at"]
    )
    op.execute("ALTER TABLE goals ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY goals_select_own ON goals
        FOR SELECT
        USING (auth.uid() = user_id AND deleted_at IS NULL)
        """
    )
    op.execute(
        """
        CREATE POLICY goals_insert_own ON goals
        FOR INSERT
        WITH CHECK (auth.uid() = user_id)
        """
    )
    op.execute(
        """
        CREATE POLICY goals_update_own ON goals
        FOR UPDATE
        USING (auth.uid() = user_id AND deleted_at IS NULL)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS goals_update_own ON goals")
    op.execute("DROP POLICY IF EXISTS goals_insert_own ON goals")
    op.execute("DROP POLICY IF EXISTS goals_select_own ON goals")
    op.drop_index("ix_goals_user_id_deleted_at", table_name="goals")
    op.drop_table("goals")
