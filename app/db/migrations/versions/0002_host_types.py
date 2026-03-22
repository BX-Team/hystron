"""Add host_type and hystron_node fields to hosts

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-23

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    cols = [c["name"] for c in inspect(op.get_bind()).get_columns("hosts")]

    if "host_type" not in cols:
        op.add_column("hosts", sa.Column("host_type", sa.Text(), nullable=False, server_default="hysteria2"))
    if "inbound_tag" not in cols:
        op.add_column("hosts", sa.Column("inbound_tag", sa.Text(), nullable=True))
    if "inbound_port" not in cols:
        op.add_column("hosts", sa.Column("inbound_port", sa.Integer(), nullable=True))
    if "grpc_address" not in cols:
        op.add_column("hosts", sa.Column("grpc_address", sa.Text(), nullable=True))
    if "api_key" not in cols:
        op.add_column("hosts", sa.Column("api_key", sa.Text(), nullable=True))
    if "sub_params" not in cols:
        op.add_column("hosts", sa.Column("sub_params", sa.Text(), nullable=True))
    if "protocol" not in cols:
        op.add_column("hosts", sa.Column("protocol", sa.Text(), nullable=True))
    if "flow" not in cols:
        op.add_column("hosts", sa.Column("flow", sa.Text(), nullable=True))


def downgrade() -> None:
    for col in ("flow", "protocol", "sub_params", "api_key", "grpc_address", "inbound_port", "inbound_tag", "host_type"):
        op.drop_column("hosts", col)
