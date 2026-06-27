"""create sales.orders, sales.order_items tables, sales.order_status enum

Revision ID: 3b204764ebe6
Revises: da8f950f5e39
Create Date: 2026-06-27 17:55:07.004464

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3b204764ebe6'
down_revision: Union[str, None] = 'da8f950f5e39'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with open(f"alembic/sql/{revision}/up.sql") as file:
        op.execute(file.read())


def downgrade() -> None:
    with open(f"alembic/sql/{revision}/down.sql") as file:
        op.execute(file.read())