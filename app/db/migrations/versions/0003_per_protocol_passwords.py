"""Per-protocol user credentials

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-21

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    cols = {c["name"] for c in inspect(op.get_bind()).get_columns("users")}
    for col_name in ("vless_uuid", "trojan_password", "hysteria2_password"):
        if col_name not in cols:
            op.add_column("users", sa.Column(col_name, sa.Text, nullable=False, server_default=""))

    # Back-fill: copy existing password into trojan_password and hysteria2_password,
    # and generate a new UUID for vless_uuid for existing users that have empty values.
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE users SET"
            "  trojan_password = CASE WHEN trojan_password = '' THEN password ELSE trojan_password END,"
            "  hysteria2_password = CASE WHEN hysteria2_password = '' THEN password ELSE hysteria2_password END"
        )
    )
    # vless_uuid must be a valid UUID; reuse the existing password (already a UUID) for old rows.
    conn.execute(
        sa.text(
            "UPDATE users SET vless_uuid = password WHERE vless_uuid = ''"
        )
    )


def downgrade() -> None:
    for col_name in ("hysteria2_password", "trojan_password", "vless_uuid"):
        op.drop_column("users", col_name)
