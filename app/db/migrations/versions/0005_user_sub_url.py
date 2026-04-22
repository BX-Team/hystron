"""Add sub_url to users

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-22

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    cols = [c["name"] for c in inspect(op.get_bind()).get_columns("users")]
    if "sub_url" not in cols:
        op.add_column("users", sa.Column("sub_url", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("users", "sub_url")
