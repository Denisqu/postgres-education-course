"""task5

Revision ID: f0820ceba6af
Revises: 9a279c4fd0c6
Create Date: 2026-06-28 15:11:38.631022

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f0820ceba6af'
down_revision: Union[str, None] = '9a279c4fd0c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with open(f"alembic/sql/{revision}/up.sql", 'r', encoding='utf-8') as file:
        op.execute(file.read())


def downgrade() -> None:
    with open(f"alembic/sql/{revision}/down.sql") as file:
        op.execute(file.read())