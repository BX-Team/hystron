"""
Fetch protocol/TLS settings from a running hystron-node info endpoint.

The node exposes a tiny HTTP server on port 10086 (XRAY_INFO_PORT) that
returns a JSON object with the inbound's protocol and TLS/reality settings.
This lets the panel auto-populate host fields instead of requiring manual entry.
"""
from __future__ import annotations

import httpx


def fetch_node_info(grpc_address: str, info_port: int = 10086) -> dict | None:
    """
    Query a node's info endpoint and return its settings dict, or None on failure.

    grpc_address should be in ``host:port`` form (e.g. ``10.0.0.1:10085``).
    The info endpoint is assumed to be on the same host at *info_port*.
    """
    host = grpc_address.split(":")[0]
    url = f"http://{host}:{info_port}/"
    try:
        r = httpx.get(url, timeout=5)
        r.raise_for_status()
        data = r.json()
        return {
            "protocol": data.get("protocol", ""),
            "inbound_tag": data.get("inbound_tag", ""),
            "sni": data.get("sni", ""),
            "reality_public_key": data.get("reality_public_key", ""),
            "reality_short_id": data.get("reality_short_id", ""),
        }
    except Exception:
        return None
