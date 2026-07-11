"""roles access migration

Revision ID: 9a279c4fd0c6
Revises: 3b204764ebe6
Create Date: 2026-06-27 23:51:51.446974

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9a279c4fd0c6'
down_revision: Union[str, None] = '3b204764ebe6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with open(f"alembic/sql/{revision}/up.sql") as file:
        op.execute(file.read())


def downgrade() -> None:
    with open(f"alembic/sql/{revision}/down.sql") as file:
        op.execute(file.read())