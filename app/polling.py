import asyncio
from datetime import datetime, timezone

import httpx

from .database import get_db, list_hosts, get_config


async def poll_hysteria():
    async with httpx.AsyncClient(timeout=10) as client:
        while True:
            forbidden_raw = get_config("forbidden_domains", "")
            forbidden = [d.strip() for d in forbidden_raw.split(",") if d.strip()]

            for host in list_hosts(active_only=True):
                address = host["address"]
                api_address = host["api_address"].rstrip("/")
                api_secret = host["api_secret"]
                headers = {"Authorization": api_secret}

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
                        conn = get_db()
                        cur = conn.cursor()
                        for username, stats in r.json().items():
                            tx, rx = stats.get("tx", 0), stats.get("rx", 0)
                            if tx or rx:
                                cur.execute(
                                    "INSERT INTO traffic (ts, server, username, tx, rx) VALUES (?, ?, ?, ?, ?)",
                                    (ts, address, username, tx, rx),
                                )
                        conn.commit()
                        conn.close()
                        await client.get(f"{api_address}/traffic?clear=1", headers=headers)
                except Exception as e:
                    print(f"error traffic {address}: {e}")

            poll_interval = int(get_config("poll_interval", "600"))
            await asyncio.sleep(poll_interval)
