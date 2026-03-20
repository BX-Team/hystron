#!/usr/bin/env bash
set -euo pipefail

TEMPLATE="${XRAY_CONFIG_TEMPLATE:-/etc/xray/config.json}"
RUNTIME="/tmp/xray-runtime.json"
API_HOST="${XRAY_API_HOST:-0.0.0.0}"
API_PORT="${XRAY_API_PORT:-10085}"

echo "xray-node: injecting API config into ${TEMPLATE}"

python3 - <<PYEOF
import json, sys, os

template_path = "${TEMPLATE}"
api_host      = "${API_HOST}"
api_port      = int("${API_PORT}")

if not os.path.isfile(template_path):
    print(f"ERROR: config template not found at {template_path}", flush=True)
    sys.exit(1)

with open(template_path) as f:
    cfg = json.load(f)

# ── api section ──────────────────────────────────────────────────────────────
if "api" not in cfg:
    cfg["api"] = {"tag": "api", "services": ["HandlerService", "StatsService"]}

# ── stats section ─────────────────────────────────────────────────────────────
if "stats" not in cfg:
    cfg["stats"] = {}

# ── policy: enable per-user traffic counters ─────────────────────────────────
cfg.setdefault("policy", {})
cfg["policy"].setdefault("levels", {})
cfg["policy"]["levels"].setdefault("0", {})
cfg["policy"]["levels"]["0"]["statsUserUplink"]   = True
cfg["policy"]["levels"]["0"]["statsUserDownlink"] = True
cfg["policy"].setdefault("system", {})
cfg["policy"]["system"]["statsInboundUplink"]   = True
cfg["policy"]["system"]["statsInboundDownlink"] = True

# ── dokodemo-door API inbound (idempotent) ────────────────────────────────────
cfg.setdefault("inbounds", [])
existing_tags = {ib.get("tag") for ib in cfg["inbounds"]}
if "api" not in existing_tags:
    cfg["inbounds"].append({
        "tag": "api",
        "listen": api_host,
        "port": api_port,
        "protocol": "dokodemo-door",
        "settings": {"address": "127.0.0.1"},
    })

# ── routing rule for api tag (idempotent) ─────────────────────────────────────
cfg.setdefault("routing", {"rules": []})
cfg["routing"].setdefault("rules", [])
if not any(r.get("outboundTag") == "api" for r in cfg["routing"]["rules"]):
    cfg["routing"]["rules"].insert(0, {
        "type": "field",
        "inboundTag": ["api"],
        "outboundTag": "api",
    })

# ── api outbound (freedom, required for routing) ──────────────────────────────
cfg.setdefault("outbounds", [])
if not any(ob.get("tag") == "api" for ob in cfg["outbounds"]):
    cfg["outbounds"].append({"tag": "api", "protocol": "freedom"})

with open("${RUNTIME}", "w") as f:
    json.dump(cfg, f, indent=2, ensure_ascii=False)

print("xray-node: config written to ${RUNTIME}", flush=True)
PYEOF

exec /usr/local/bin/xray run -config "${RUNTIME}"
