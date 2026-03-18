import asyncio
import json

from .config import XRAY_STATS_PORT
from .models import TrafficStat


async def collect() -> list[TrafficStat]:
    """
    Query xray stats API for per-user traffic and reset counters.
    Uses `xray api statsquery --reset` which outputs JSON.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "xray", "api", "statsquery",
            f"--server=127.0.0.1:{XRAY_STATS_PORT}",
            "--pattern", "user>>>",
            "--reset",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        return _parse(stdout.decode())
    except asyncio.TimeoutError:
        print("[node/stats] statsquery timed out")
        return []
    except Exception as e:
        print(f"[node/stats] error collecting stats: {e}")
        return []


def _parse(output: str) -> list[TrafficStat]:
    """
    Parse xray statsquery JSON output.
    Each entry looks like:
      {"name": "user>>>alice@proxy>>>traffic>>>uplink", "value": 1234}
    """
    stats: dict[str, TrafficStat] = {}
    try:
        data = json.loads(output)
        entries = data.get("stat", [])
        for entry in entries:
            name: str = entry.get("name", "")
            value: int = int(entry.get("value", 0))
            # name format: user>>>email>>>traffic>>>uplink|downlink
            parts = name.split(">>>")
            if len(parts) != 4 or parts[0] != "user":
                continue
            email = parts[1].split("@")[0] if "@" in parts[1] else parts[1]
            direction = parts[3]
            if email not in stats:
                stats[email] = TrafficStat(username=email, tx=0, rx=0)
            if direction == "uplink":
                stats[email].tx += value
            elif direction == "downlink":
                stats[email].rx += value
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        print(f"[node/stats] parse error: {e}")
    return list(stats.values())
