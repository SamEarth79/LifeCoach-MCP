"""add goals progress_percent

Revision ID: 66f94137137d
Revises: 8e5660ff9d7f
Create Date: 2026-06-21 09:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "66f94137137d"
down_revision: Union[str, None] = "8e5660ff9d7f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("goals", sa.Column("progress_percent", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "goals_progress_percent_check",
        "goals",
        "progress_percent IS NULL OR (progress_percent BETWEEN 0 AND 100)",
    )


def downgrade() -> None:
    op.drop_constraint("goals_progress_percent_check", "goals", type_="check")
    op.drop_column("goals", "progress_percent")
