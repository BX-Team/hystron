import asyncio
import os

import httpx

from . import config, stats, xray
from .models import NodeInfo, SyncResponse, UserEntry

CONTROL_URL = os.environ.get("HYSTRON_CONTROL_URL", "").rstrip("/")
NODE_TOKEN = os.environ.get("HYSTRON_NODE_TOKEN", "")

_DEFAULT_POLL_INTERVAL = 30


async def _sync(client: httpx.AsyncClient, last_version: str) -> SyncResponse | None:
    headers = {
        "Authorization": f"Bearer {NODE_TOKEN}",
        "X-Config-Version": last_version,
    }
    try:
        r = await client.get(f"{CONTROL_URL}/node/sync", headers=headers, timeout=15)
        if r.status_code == 304:
            return None
        r.raise_for_status()
        data = r.json()
        node_data = data["node"]
        return SyncResponse(
            config_version=data["config_version"],
            poll_interval=data.get("poll_interval", _DEFAULT_POLL_INTERVAL),
            node=NodeInfo(
                address=node_data["address"],
                protocols=node_data.get("protocols", []),
                ports=node_data.get("ports", {}),
            ),
            users=[
                UserEntry(
                    username=u["username"],
                    password=u["password"],
                    active=u["active"],
                    expires_at=u["expires_at"],
                    traffic_limit=u["traffic_limit"],
                )
                for u in data["users"]
            ],
        )
    except Exception as e:
        print(f"[node/agent] sync error: {e}")
        return None


async def _report_traffic(
    client: httpx.AsyncClient,
    traffic_stats,
    inbounds: list[dict],
) -> list[str]:
    payload = {
        "stats": [{"username": s.username, "tx": s.tx, "rx": s.rx} for s in traffic_stats],
        "inbounds": inbounds,
    }
    try:
        r = await client.post(
            f"{CONTROL_URL}/node/traffic",
            json=payload,
            headers={"Authorization": f"Bearer {NODE_TOKEN}"},
            timeout=15,
        )
        r.raise_for_status()
        return r.json().get("kicked", [])
    except Exception as e:
        print(f"[node/agent] traffic report error: {e}")
        return []


def _apply_users(users: list[UserEntry]) -> bool:
    """Fill clients in the template and write the final config. Returns True on success."""
    template = config.read_template()
    if template is None:
        print("[node/agent] no template — xray config not updated")
        return False
    filled = config.fill_clients(template, users)
    final = config.ensure_stats_inbound(filled)
    config.write(final)
    return True


async def run() -> None:
    if not CONTROL_URL:
        raise SystemExit("HYSTRON_CONTROL_URL is not set")
    if not NODE_TOKEN:
        raise SystemExit("HYSTRON_NODE_TOKEN is not set")

    print(f"[node/agent] starting, control={CONTROL_URL}")
    print(f"[node/agent] template={config.XRAY_TEMPLATE_PATH}")

    # Write initial empty config so xray can start
    template = config.read_template()
    if template:
        initial = config.ensure_stats_inbound(config.fill_clients(template, []))
        config.write(initial)
        inbounds = config.extract_inbounds(template)
    else:
        # Minimal fallback config — xray will start but do nothing useful
        config.write(
            {
                "log": {"loglevel": "warning"},
                "inbounds": [
                    {
                        "tag": "hystron-api",
                        "listen": "127.0.0.1",
                        "port": config.XRAY_STATS_PORT,
                        "protocol": "dokodemo-door",
                        "settings": {"address": "127.0.0.1"},
                    }
                ],
                "outbounds": [{"tag": "direct", "protocol": "freedom"}],
                "api": {"tag": "api", "services": ["StatsService", "HandlerService"]},
                "stats": {},
                "routing": {"rules": [{"type": "field", "inboundTag": ["hystron-api"], "outboundTag": "api"}]},
            }
        )
        inbounds = []

    await xray.start()
    await asyncio.sleep(2)  # let xray initialize

    last_version = ""
    poll_interval = _DEFAULT_POLL_INTERVAL
    current_users: list[UserEntry] = []

    async with httpx.AsyncClient() as client:
        while True:
            sync_data = await _sync(client, last_version)
            if sync_data is not None:
                poll_interval = sync_data.poll_interval
                current_users = sync_data.users
                if _apply_users(current_users):
                    await xray.reload()
                    last_version = sync_data.config_version
                    print(f"[node/agent] config updated: {last_version}")

            traffic_result = await stats.collect()
            kicked = await _report_traffic(client, traffic_result, inbounds)
            if kicked:
                await xray.kick_users(kicked)

            await asyncio.sleep(poll_interval)
