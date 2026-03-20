import asyncio
from datetime import datetime, timezone

from app.database import (
    edit_user,
    get_config,
    get_traffic,
    get_user,
    list_hosts,
    list_users,
    record_traffic_batch,
    reset_traffic_limited_users,
)
from app.xray.client import query_traffic
from app.xray.sync import sync_user_to_all_hosts

_last_reset_date = None


async def _maybe_reset_daily_limits() -> None:
    """Reactivate traffic-limited users at midnight UTC and re-add them to xray nodes."""
    global _last_reset_date
    now = datetime.now(timezone.utc)
    current_date = now.date()

    if _last_reset_date != current_date and now.hour == 0 and now.minute < 10:
        try:
            count = reset_traffic_limited_users()
            if count > 0:
                print(f"Daily reset: reactivated {count} users at {now.strftime('%Y-%m-%d %H:%M:%S')} UTC")
                # Re-add reactivated users to all nodes
                for user in list_users():
                    if user["active"] and user["traffic_limit"] > 0:
                        asyncio.create_task(
                            sync_user_to_all_hosts(user["username"], user["password"], active=True)
                        )
            _last_reset_date = current_date
        except Exception as e:
            print(f"Error during daily reset: {e}")


async def poll_xray() -> None:
    while True:
        await _maybe_reset_daily_limits()

        # Deduplicate grpc_address: one xray node may appear as multiple hosts
        seen_grpc: set[str] = set()

        for host in list_hosts(active_only=True):
            grpc_address = host.get("grpc_address", "")
            if not grpc_address or grpc_address in seen_grpc:
                continue
            seen_grpc.add(grpc_address)

            try:
                traffic_map = await query_traffic(grpc_address, reset=True)
            except Exception as e:
                print(f"error polling {host['address']} ({grpc_address}): {e}")
                continue

            if not traffic_map:
                continue

            ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            entries = [
                (ts, host["address"], username, stats["tx"], stats["rx"])
                for username, stats in traffic_map.items()
                if stats["tx"] or stats["rx"]
            ]
            if entries:
                record_traffic_batch(entries)

            for username in traffic_map:
                try:
                    user = get_user(username)
                    if not user or user["traffic_limit"] <= 0:
                        continue
                    traffic = get_traffic(username)
                    if not traffic:
                        continue
                    day_usage = traffic[0]["day"]
                    if day_usage >= user["traffic_limit"]:
                        edit_user(username, active=False)
                        asyncio.create_task(
                            sync_user_to_all_hosts(username, user["password"], active=False)
                        )
                        print(f"deactivated {username}: daily traffic limit exceeded ({day_usage} >= {user['traffic_limit']})")
                except Exception as e:
                    print(f"error checking limit for {username}: {e}")

        poll_interval = int(get_config("poll_interval", "600"))
        await asyncio.sleep(poll_interval)
