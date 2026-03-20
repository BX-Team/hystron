"""xray host fields

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-20

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
    cols = {c["name"] for c in inspect(op.get_bind()).get_columns("hosts")}
    for col_name, col_type, default in [
        ("grpc_address", sa.Text, ""),
        ("protocol", sa.Text, "vless_reality"),
        ("inbound_tag", sa.Text, ""),
        ("sni", sa.Text, ""),
        ("reality_public_key", sa.Text, ""),
        ("reality_short_id", sa.Text, ""),
    ]:
        if col_name not in cols:
            op.add_column("hosts", sa.Column(col_name, col_type, nullable=False, server_default=default))


def downgrade() -> None:
    for col_name in ("reality_short_id", "reality_public_key", "sni", "inbound_tag", "protocol", "grpc_address"):
        op.drop_column("hosts", col_name)
