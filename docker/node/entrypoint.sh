#!/usr/bin/env bash
set -euo pipefail

TEMPLATE="${XRAY_CONFIG_TEMPLATE:-/etc/xray/config.json}"
RUNTIME="/tmp/xray-runtime.json"
NODE_INFO="/tmp/node-info.json"
API_HOST="${XRAY_API_HOST:-0.0.0.0}"
API_PORT="${XRAY_API_PORT:-10085}"
INFO_PORT="${XRAY_INFO_PORT:-10086}"

echo "xray-node: injecting API config into ${TEMPLATE}"

python3 - <<PYEOF
import json, sys, os

template_path = "${TEMPLATE}"
api_host      = "${API_HOST}"
api_port      = int("${API_PORT}")
info_path     = "${NODE_INFO}"

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

# ── extract node info for the panel detect endpoint ───────────────────────────
# Find the first non-api inbound and extract its protocol and TLS/reality settings.
_PROTO_MAP = {"vless": "vless_reality", "trojan": "trojan", "hysteria2": "hysteria2"}
info = {"protocol": "", "inbound_tag": "", "sni": "", "reality_public_key": "", "reality_short_id": ""}

for ib in cfg.get("inbounds", []):
    if ib.get("tag") == "api":
        continue
    proto_raw = ib.get("protocol", "")
    info["inbound_tag"] = ib.get("tag", "")
    info["protocol"] = _PROTO_MAP.get(proto_raw, proto_raw)

    stream = ib.get("streamSettings", {})
    security = stream.get("security", "")

    if security == "reality":
        rs = stream.get("realitySettings", {})
        server_names = rs.get("serverNames", [])
        info["sni"] = server_names[0] if server_names else ""
        info["reality_public_key"] = rs.get("publicKey", "")
        short_ids = rs.get("shortIds", [])
        info["reality_short_id"] = short_ids[0] if short_ids else ""
    elif security in ("tls", "auto"):
        ts = stream.get("tlsSettings", {})
        info["sni"] = ts.get("serverName", "")

    # Hysteria2 uses its own settings block
    if proto_raw == "hysteria2":
        hy2 = ib.get("settings", {})
        info["sni"] = hy2.get("domain", info["sni"])

    break  # only use the first non-api inbound

with open(info_path, "w") as f:
    json.dump(info, f)

print(f"xray-node: node-info written to {info_path}", flush=True)
PYEOF

# ── start lightweight info HTTP server in background ─────────────────────────
# Serves GET / → node-info.json so the panel can auto-detect settings.
python3 -c "
import http.server, json, os
data = open('${NODE_INFO}').read().encode()
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(data)
    def log_message(self, *a): pass
http.server.HTTPServer(('0.0.0.0', int('${INFO_PORT}')), H).serve_forever()
" &

exec /usr/local/bin/xray run -config "${RUNTIME}"
