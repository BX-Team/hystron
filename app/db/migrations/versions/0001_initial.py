"""Initial schema

Revision ID: 0001
Revises:
Create Date: 2026-03-20

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    existing = inspect(op.get_bind()).get_table_names()

    if "users" not in existing:
        op.create_table(
            "users",
            sa.Column("username", sa.Text, primary_key=True),
            sa.Column("password", sa.Text, nullable=False),
            sa.Column("sid", sa.Text, unique=True, nullable=False),
            sa.Column("active", sa.Integer, nullable=False, server_default="1"),
            sa.Column("traffic_limit", sa.Integer, nullable=False, server_default="0"),
            sa.Column("expires_at", sa.Integer, nullable=False, server_default="0"),
            sa.Column("device_limit", sa.Integer, nullable=False, server_default="0"),
        )
    else:
        # Ensure device_limit column exists (legacy databases)
        cols = [c["name"] for c in inspect(op.get_bind()).get_columns("users")]
        if "device_limit" not in cols:
            op.add_column("users", sa.Column("device_limit", sa.Integer, nullable=False, server_default="0"))

    if "devices" not in existing:
        op.create_table(
            "devices",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("username", sa.Text, nullable=False),
            sa.Column("hwid", sa.Text, nullable=False),
            sa.Column("device_os", sa.Text, nullable=False),
            sa.Column("ver_os", sa.Text, nullable=False),
            sa.Column("device_model", sa.Text, nullable=False),
            sa.Column("app_version", sa.Text, nullable=False),
        )

    if "traffic" not in existing:
        op.create_table(
            "traffic",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("ts", sa.Text, nullable=False),
            sa.Column("server", sa.Text, nullable=False),
            sa.Column("username", sa.Text, nullable=False),
            sa.Column("tx", sa.Integer, nullable=False),
            sa.Column("rx", sa.Integer, nullable=False),
        )
        op.create_index("traffic_ts", "traffic", ["ts"])
        op.create_index("traffic_user", "traffic", ["username"])

    if "hosts" not in existing:
        op.create_table(
            "hosts",
            sa.Column("address", sa.Text, primary_key=True),
            sa.Column("name", sa.Text, nullable=False),
            sa.Column("port", sa.Integer, nullable=False, server_default="443"),
            sa.Column("api_address", sa.Text, nullable=False),
            sa.Column("api_secret", sa.Text, nullable=False),
            sa.Column("active", sa.Integer, nullable=False, server_default="1"),
        )

    if "host_tags" not in existing:
        op.create_table(
            "host_tags",
            sa.Column("host_address", sa.Text, primary_key=True),
            sa.Column("tag", sa.Text, primary_key=True),
        )

    if "user_tags" not in existing:
        op.create_table(
            "user_tags",
            sa.Column("username", sa.Text, primary_key=True),
            sa.Column("tag", sa.Text, primary_key=True),
        )

    if "config" not in existing:
        op.create_table(
            "config",
            sa.Column("key", sa.Text, primary_key=True),
            sa.Column("value", sa.Text, nullable=False),
        )


def downgrade() -> None:
    op.drop_table("config")
    op.drop_table("user_tags")
    op.drop_table("host_tags")
    op.drop_table("hosts")
    op.drop_index("traffic_user", "traffic")
    op.drop_index("traffic_ts", "traffic")
    op.drop_table("traffic")
    op.drop_table("devices")
    op.drop_table("users")
