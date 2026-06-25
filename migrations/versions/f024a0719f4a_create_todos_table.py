"""create todos table

Revision ID: f024a0719f4a
Revises: 66f94137137d
Create Date: 2026-06-25 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f024a0719f4a"
down_revision: Union[str, None] = "66f94137137d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "todos",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("goal_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "done",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("sort_order", sa.Integer(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["user_id"], ["auth.users.id"], name="todos_user_id_fkey", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["goal_id"], ["goals.id"], name="todos_goal_id_fkey", ondelete="CASCADE"
        ),
    )
    op.create_index("ix_todos_goal_id_sort_order", "todos", ["goal_id", "sort_order"])
    op.execute("ALTER TABLE todos ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY todos_select_own ON todos
        FOR SELECT
        USING (
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
    op.execute(
        """
        CREATE POLICY todos_insert_own ON todos
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
    op.execute(
        """
        CREATE POLICY todos_update_own ON todos
        FOR UPDATE
        USING (
            auth.uid() = user_id
            AND EXISTS (
                SELECT 1 FROM goals g
                WHERE g.id = goal_id
                AND g.user_id = auth.uid()
                AND g.deleted_at IS NULL
            )
        )
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
    op.execute(
        """
        CREATE POLICY todos_delete_own ON todos
        FOR DELETE
        USING (
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
    op.execute("DROP POLICY IF EXISTS todos_delete_own ON todos")
    op.execute("DROP POLICY IF EXISTS todos_update_own ON todos")
    op.execute("DROP POLICY IF EXISTS todos_insert_own ON todos")
    op.execute("DROP POLICY IF EXISTS todos_select_own ON todos")
    op.drop_index("ix_todos_goal_id_sort_order", table_name="todos")
    op.drop_table("todos")
