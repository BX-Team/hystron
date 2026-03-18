"""
Node config builder.

The user writes a standard xray-core config at XRAY_TEMPLATE_PATH
(e.g. /var/lib/hystron/xray-template.json) with inbounds fully configured
but with empty clients arrays:  "clients": []

This module reads that template, fills in the users from Control, and writes
the final config to XRAY_CONFIG_PATH for xray to pick up via SIGHUP.
"""

import json
import os

from .models import UserEntry

XRAY_TEMPLATE_PATH = os.environ.get(
    "XRAY_TEMPLATE_PATH", "/var/lib/hystron/xray-template.json"
)
XRAY_CONFIG_PATH = os.environ.get(
    "XRAY_CONFIG_PATH", "/var/lib/hystron/xray.json"
)
XRAY_STATS_PORT = int(os.environ.get("XRAY_STATS_PORT", "10085"))


def _make_client(proto: str, user: UserEntry) -> dict:
    if proto == "hysteria2":
        return {"id": f"{user.username}:{user.password}", "email": user.username}
    if proto in ("vless", "vmess"):
        return {"id": user.password, "email": user.username, "flow": "xtls-rprx-vision"}
    if proto == "trojan":
        return {"password": user.password, "email": user.username}
    # shadowsocks and others — best-effort
    return {"password": user.password, "email": user.username}


def fill_clients(template: dict, users: list[UserEntry]) -> dict:
    """Return a copy of *template* with clients arrays populated from *users*."""
    import copy
    cfg = copy.deepcopy(template)
    active_users = [u for u in users if u.active]

    for inbound in cfg.get("inbounds", []):
        proto = inbound.get("protocol", "")
        settings = inbound.get("settings", {})
        # Skip the stats/api inbound (dokodemo-door)
        if proto == "dokodemo-door":
            continue
        if "clients" in settings:
            settings["clients"] = [_make_client(proto, u) for u in active_users]

    return cfg


def ensure_stats_inbound(cfg: dict) -> dict:
    """Add the xray stats API inbound if it isn't already present."""
    import copy
    cfg = copy.deepcopy(cfg)

    # Check if stats API inbound already exists
    has_stats_inbound = any(
        inb.get("protocol") == "dokodemo-door" and
        inb.get("listen") == "127.0.0.1"
        for inb in cfg.get("inbounds", [])
    )
    if not has_stats_inbound:
        cfg.setdefault("inbounds", []).append({
            "tag": "hystron-api",
            "listen": "127.0.0.1",
            "port": XRAY_STATS_PORT,
            "protocol": "dokodemo-door",
            "settings": {"address": "127.0.0.1"},
        })

    # Ensure stats/api/policy blocks exist
    cfg.setdefault("api", {"tag": "api", "services": ["StatsService", "HandlerService"]})
    cfg.setdefault("stats", {})
    cfg.setdefault("policy", {
        "levels": {"0": {"statsUserUplink": True, "statsUserDownlink": True}},
        "system": {"statsInboundUplink": True, "statsInboundDownlink": True},
    })

    # Ensure routing rule for stats API
    routing = cfg.setdefault("routing", {"rules": []})
    rules = routing.setdefault("rules", [])
    has_api_rule = any(
        "hystron-api" in r.get("inboundTag", []) or "api-inbound" in r.get("inboundTag", [])
        for r in rules
    )
    if not has_api_rule:
        rules.insert(0, {
            "type": "field",
            "inboundTag": ["hystron-api"],
            "outboundTag": "api",
        })

    return cfg


def extract_inbounds(cfg: dict) -> list[dict]:
    """Return [{protocol, port}] for non-API inbounds — used to report to Control."""
    result = []
    for inb in cfg.get("inbounds", []):
        proto = inb.get("protocol", "")
        port = inb.get("port")
        if proto and port and proto != "dokodemo-door":
            result.append({"protocol": proto, "port": port})
    return result


def read_template() -> dict | None:
    """Read the user-provided xray template. Returns None if not found."""
    if not os.path.isfile(XRAY_TEMPLATE_PATH):
        print(f"[node/config] template not found: {XRAY_TEMPLATE_PATH}")
        return None
    with open(XRAY_TEMPLATE_PATH) as f:
        return json.load(f)


def write(cfg: dict) -> None:
    os.makedirs(os.path.dirname(XRAY_CONFIG_PATH) or ".", exist_ok=True)
    with open(XRAY_CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)
