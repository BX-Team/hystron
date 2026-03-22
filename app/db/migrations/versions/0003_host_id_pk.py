"""Replace hosts.address primary key with auto-increment id; migrate host_tags to host_id

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-23

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # Read all existing data before dropping tables
    hosts = bind.execute(sa.text("SELECT * FROM hosts")).mappings().fetchall()
    host_tags = bind.execute(sa.text("SELECT * FROM host_tags")).mappings().fetchall()

    # Drop dependent table first
    op.drop_table("host_tags")
    op.drop_table("hosts")

    # Recreate hosts with integer id as primary key
    op.create_table(
        "hosts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("address", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False, server_default="443"),
        sa.Column("api_address", sa.Text(), nullable=True),
        sa.Column("api_secret", sa.Text(), nullable=True),
        sa.Column("active", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("host_type", sa.Text(), nullable=False, server_default="hysteria2"),
        sa.Column("inbound_tag", sa.Text(), nullable=True),
        sa.Column("inbound_port", sa.Integer(), nullable=True),
        sa.Column("grpc_address", sa.Text(), nullable=True),
        sa.Column("api_key", sa.Text(), nullable=True),
        sa.Column("sub_params", sa.Text(), nullable=True),
        sa.Column("protocol", sa.Text(), nullable=True),
        sa.Column("flow", sa.Text(), nullable=True),
    )

    # Migrate hosts rows and record address → new id mapping
    addr_to_id: dict[str, int] = {}
    for row in hosts:
        bind.execute(
            sa.text(
                "INSERT INTO hosts "
                "(address, name, port, api_address, api_secret, active, host_type, "
                "inbound_tag, inbound_port, grpc_address, api_key, sub_params, protocol, flow) "
                "VALUES "
                "(:address, :name, :port, :api_address, :api_secret, :active, :host_type, "
                ":inbound_tag, :inbound_port, :grpc_address, :api_key, :sub_params, :protocol, :flow)"
            ),
            dict(row),
        )
        new_id = bind.execute(sa.text("SELECT last_insert_rowid()")).scalar()
        if new_id is not None:
            addr_to_id[row["address"]] = int(new_id)

    # Recreate host_tags with integer host_id
    op.create_table(
        "host_tags",
        sa.Column("host_id", sa.Integer(), primary_key=True),
        sa.Column("tag", sa.Text(), primary_key=True),
    )

    # Migrate host_tags rows using the address → id mapping
    for tag_row in host_tags:
        old_addr = tag_row["host_address"]
        if old_addr in addr_to_id:
            bind.execute(
                sa.text("INSERT INTO host_tags (host_id, tag) VALUES (:host_id, :tag)"),
                {"host_id": addr_to_id[old_addr], "tag": tag_row["tag"]},
            )


def downgrade() -> None:
    raise NotImplementedError("Downgrade not supported: original text-PK schema cannot be recovered automatically")
