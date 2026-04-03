"""Add up_mbps and down_mbps to hosts

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-02

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    cols = [c["name"] for c in inspect(op.get_bind()).get_columns("hosts")]
    if "up_mbps" not in cols:
        op.add_column("hosts", sa.Column("up_mbps", sa.Integer(), nullable=True))
    if "down_mbps" not in cols:
        op.add_column("hosts", sa.Column("down_mbps", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("hosts", "down_mbps")
    op.drop_column("hosts", "up_mbps")
