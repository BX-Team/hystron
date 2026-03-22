"""
Async synchronization of users with hystron-node hosts.

Fire-and-forget friendly — errors are logged but never re-raised so that
a single offline node cannot block user management.
"""
from __future__ import annotations

import asyncio


async def _run(fn, *args):
    """Run a blocking node_client function in a thread pool."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, fn, *args)


async def sync_user_to_host(host: dict, user: dict, action: str) -> None:
    """Push add/remove for a single user to one hystron_node host. Errors are logged."""
    from app.node_client import add_user_to_node, remove_user_from_node

    if host.get("host_type") != "hystron_node":
        return
    if not host.get("grpc_address") or not host.get("inbound_tag"):
        return

    username = user["username"]
    host_name = host.get("address", host.get("grpc_address", "?"))
    try:
        if action == "add":
            ok, msg = await _run(add_user_to_node, host, username, user["password"], user["password"])
            if not ok:
                print(f"node sync add {username!r} on {host_name}: {msg}")
        elif action == "remove":
            ok, msg = await _run(remove_user_from_node, host, username)
            if not ok:
                print(f"node sync remove {username!r} on {host_name}: {msg}")
    except Exception as e:
        print(f"node sync {action} {username!r} on {host_name}: {e}")


async def sync_user_to_all_nodes(user: dict, *, active: bool) -> None:
    """Push user state to all active hystron_node hosts simultaneously."""
    from app.database import list_hystron_nodes

    hosts = list_hystron_nodes(active_only=True)
    action = "add" if active else "remove"
    await asyncio.gather(
        *[sync_user_to_host(h, user, action) for h in hosts],
        return_exceptions=True,
    )


async def sync_new_host(host: dict) -> None:
    """When a new hystron_node host is added, push all active users to it."""
    from app.database import list_users

    if host.get("host_type") != "hystron_node":
        return

    users = list_users()
    active_users = [u for u in users if u["active"]]
    host_name = host.get("address", "?")
    print(f"node sync_new_host {host_name}: {len(active_users)} users")
    await asyncio.gather(
        *[sync_user_to_host(host, u, "add") for u in active_users],
        return_exceptions=True,
    )


async def full_resync() -> None:
    """
    Push all users to all active hystron_node hosts.
    Called on panel startup.
    """
    from app.database import list_hystron_nodes, list_users

    hosts = list_hystron_nodes(active_only=True)
    users = list_users()
    if not hosts:
        return
    print(f"node full_resync: {len(users)} users × {len(hosts)} nodes")
    for host in hosts:
        for user in users:
            action = "add" if user["active"] else "remove"
            await sync_user_to_host(host, user, action)
