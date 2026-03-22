import asyncio
from datetime import datetime, timezone

import httpx

from .database import (
    edit_user,
    get_config,
    get_traffic,
    get_user,
    list_hosts,
    record_traffic_batch,
    reset_traffic_limited_users,
)
from .node_client import get_traffic_stats, reset_traffic_stats

_last_reset_date = None


async def reset_daily_limits():
    """Reset user active status at the start of each day (00:00 UTC)."""
    global _last_reset_date
    now = datetime.now(timezone.utc)
    current_date = now.date()

    if _last_reset_date != current_date and now.hour == 0 and now.minute < 10:
        try:
            from .database import list_users
            from .node_sync import sync_user_to_all_nodes

            count = reset_traffic_limited_users()
            if count > 0:
                print(f"Daily reset: reactivated {count} users at {now.strftime('%Y-%m-%d %H:%M:%S')} UTC")
                # Re-add reactivated users to all nodes
                for user in list_users():
                    if user["active"] and user["traffic_limit"] > 0:
                        await sync_user_to_all_nodes(user, active=True)
            _last_reset_date = current_date
        except Exception as e:
            print(f"Error during daily reset: {e}")


async def poll_hysteria2(host: dict, client: httpx.AsyncClient) -> None:
    """Poll a classic Hysteria2 host via its HTTP API."""
    address = host["address"]
    api_address = (host["api_address"] or "").rstrip("/")
    api_secret = host["api_secret"] or ""
    headers = {"Authorization": api_secret}

    forbidden_raw = get_config("forbidden_domains", "")
    forbidden = [d.strip() for d in forbidden_raw.split(",") if d.strip()]

    if forbidden:
        try:
            r = await client.get(f"{api_address}/dump/streams", headers=headers)
            if r.status_code == 200:
                offenders: dict[str, list[str]] = {}
                for stream in r.json().get("streams", []):
                    addr = stream.get("hooked_req_addr") or stream.get("req_addr", "")
                    domain = addr.split(":")[0]
                    auth = stream.get("auth", "")
                    for fd in forbidden:
                        if domain == fd or domain.endswith("." + fd):
                            offenders.setdefault(auth, []).append(domain)
                for user, domains in offenders.items():
                    print(f"forbidden: {address} / {user}: {', '.join(sorted(set(domains)))}")
        except Exception as e:
            print(f"error streams {address}: {e}")

    try:
        r = await client.get(f"{api_address}/traffic", headers=headers)
        if r.status_code == 200:
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            entries = [
                (ts, address, username, stats.get("tx", 0), stats.get("rx", 0))
                for username, stats in r.json().items()
                if stats.get("tx", 0) or stats.get("rx", 0)
            ]
            if entries:
                record_traffic_batch(entries)
            await client.get(f"{api_address}/traffic?clear=1", headers=headers)

            for username in r.json().keys():
                try:
                    user = get_user(username)
                    if user and user["traffic_limit"] > 0:
                        total = get_traffic(username)
                        if total and total[0]["day"] >= user["traffic_limit"]:
                            edit_user(username, active=False)
                            await client.post(f"{api_address}/kick", json={"id": username}, headers=headers)
                            from .node_sync import sync_user_to_all_nodes

                            await sync_user_to_all_nodes(user, active=False)
                            print(f"kicked {username} on {address}: daily traffic limit exceeded")
                except Exception as e:
                    print(f"error checking limit for {username} on {address}: {e}")
    except Exception as e:
        print(f"error traffic {address}: {e}")


async def poll_hystron_node(host: dict) -> None:
    """Poll a hystron-node host via gRPC."""
    address = host["address"]
    try:
        stats = await asyncio.get_event_loop().run_in_executor(None, get_traffic_stats, host)
    except Exception as e:
        print(f"error grpc traffic {address}: {e}")
        return

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    entries = [(ts, address, username, tx, rx) for username, (tx, rx) in stats.items() if tx or rx]
    if entries:
        record_traffic_batch(entries)

    try:
        await asyncio.get_event_loop().run_in_executor(None, reset_traffic_stats, host)
    except Exception as e:
        print(f"error grpc reset {address}: {e}")

    for username, (tx, rx) in stats.items():
        if not (tx or rx):
            continue
        try:
            user = get_user(username)
            if user and user["traffic_limit"] > 0:
                total = get_traffic(username)
                if total and total[0]["day"] >= user["traffic_limit"]:
                    edit_user(username, active=False)
                    from .node_sync import sync_user_to_all_nodes

                    await sync_user_to_all_nodes(user, active=False)
                    print(f"deactivated {username} on {address}: daily traffic limit exceeded")
        except Exception as e:
            print(f"error checking limit for {username} on {address}: {e}")


async def poll_hysteria():
    async with httpx.AsyncClient(timeout=10) as client:
        while True:
            await reset_daily_limits()

            for host in list_hosts(active_only=True):
                if host.get("host_type", "hysteria2") == "hystron_node":
                    await poll_hystron_node(host)
                else:
                    await poll_hysteria2(host, client)

            poll_interval = int(get_config("poll_interval", "600"))
            await asyncio.sleep(poll_interval)
