"""allow queued collection runs

Revision ID: 18378751c907
Revises: c4850987e2f2
Create Date: 2026-11-13 10:22:35.724189

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '18378751c907'
down_revision: Union[str, Sequence[str], None] = 'c4850987e2f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_collection_runs_status",
        "collection_runs",
        type_="check",
    )

    op.create_check_constraint(
        "ck_collection_runs_status",
        "collection_runs",
        "status IN "
        "('queued', 'running', 'completed', 'failed', 'interrupted')",
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE collection_runs
        SET status = 'interrupted'
        WHERE status = 'queued'
        """
    )

    op.drop_constraint(
        "ck_collection_runs_status",
        "collection_runs",
        type_="check",
    )

    op.create_check_constraint(
        "ck_collection_runs_status",
        "collection_runs",
        "status IN "
        "('running', 'completed', 'failed', 'interrupted')",
    )
