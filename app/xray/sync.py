"""
User synchronization with xray nodes.

All functions are async and fire-and-forget friendly — errors are logged but
never re-raised so that a single offline node cannot break user management.
"""
from __future__ import annotations

import asyncio

import grpc.aio

from app.xray.client import add_user, remove_user


def _credential_for(user: dict, protocol: str) -> str:
    """Pick the right per-protocol credential for the given user dict."""
    if protocol == "vless_reality":
        return user.get("vless_uuid") or user["password"]
    if protocol == "hysteria2":
        return user.get("hysteria2_password") or user["password"]
    # trojan (and any future protocols)
    return user.get("trojan_password") or user["password"]


async def sync_user_to_host(
    host: dict,
    user: dict,
    action: str,  # "add" | "remove"
) -> None:
    """Push a single user add/remove to one xray node. Errors are logged, not raised."""
    grpc_address = host.get("grpc_address", "")
    inbound_tag = host.get("inbound_tag", "")
    protocol = host.get("protocol", "vless_reality")
    host_name = host.get("address", grpc_address)

    if not grpc_address or not inbound_tag:
        return

    username = user["username"]
    try:
        if action == "add":
            credential = _credential_for(user, protocol)
            await add_user(grpc_address, inbound_tag, protocol, username, credential)
        elif action == "remove":
            await remove_user(grpc_address, inbound_tag, username)
    except grpc.aio.AioRpcError as e:
        print(f"xray sync {action} {username!r} on {host_name}: {e.code()} — {e.details()}")
    except Exception as e:
        print(f"xray sync {action} {username!r} on {host_name}: {e}")


async def sync_user_to_all_hosts(
    user: dict,
    *,
    active: bool,
) -> None:
    """Push user state to all active hosts simultaneously."""
    from app.database import list_hosts

    hosts = list_hosts(active_only=True)
    action = "add" if active else "remove"
    await asyncio.gather(
        *[sync_user_to_host(h, user, action) for h in hosts],
        return_exceptions=True,
    )


async def full_resync() -> None:
    """
    Push all users to all active hosts.
    Called on panel startup and after migrations.
    Active users are added; inactive users are removed (offline nodes tolerated).
    """
    from app.database import list_hosts, list_users

    hosts = list_hosts(active_only=True)
    users = list_users()
    print(f"xray full_resync: {len(users)} users × {len(hosts)} hosts")
    for host in hosts:
        for user in users:
            action = "add" if user["active"] else "remove"
            await sync_user_to_host(host, user, action)


async def sync_new_host(host: dict) -> None:
    """When a new host is added, push all active users to it."""
    from app.database import list_users

    users = list_users()
    active_users = [u for u in users if u["active"]]
    print(f"xray sync_new_host {host.get('address')}: {len(active_users)} users")
    await asyncio.gather(
        *[sync_user_to_host(host, u, "add") for u in active_users],
        return_exceptions=True,
    )
