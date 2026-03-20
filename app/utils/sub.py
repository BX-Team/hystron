import base64
import json
import os
import urllib.parse

from fastapi.responses import PlainTextResponse

from app.database import get_config, list_hosts

_BUNDLED_TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "templates")

_TEMPLATE_CONFIG_KEY: dict[str, str] = {
    "singbox.json": "template_singbox",
    "clash.yaml": "template_clash",
    "xray.json": "template_xray",
    "index.html": "template_index",
}


def get_template_file(filename: str) -> str:
    """
    Resolve the path for *filename* using the following priority:
      1. Per-format config key (e.g. ``template_singbox``) — if set and the file exists.
      2. ``{templates_dir}/{filename}`` — if the file exists.
      3. Bundled template shipped with the application.
    """
    cfg_key = _TEMPLATE_CONFIG_KEY.get(filename, "")
    if cfg_key:
        specific = get_config(cfg_key, "")
        if specific and os.path.isfile(specific):
            return specific

    templates_dir = get_config("templates_dir", "/var/lib/hystron/templates")
    if templates_dir:
        candidate = os.path.join(templates_dir, filename)
        if os.path.isfile(candidate):
            return candidate

    return os.path.join(_BUNDLED_TEMPLATES_DIR, filename)


def get_templates_search_dirs() -> list[str]:
    """
    Return an ordered list of directories for Jinja2 template lookup.
    Override directory (if it exists) comes first, bundled directory last.
    """
    dirs: list[str] = []
    templates_dir = get_config("templates_dir", "/var/lib/hystron/templates")
    if templates_dir and os.path.isdir(templates_dir):
        dirs.append(templates_dir)
    dirs.append(_BUNDLED_TEMPLATES_DIR)
    return dirs


def _build_uri(proto: str, uname: str, pwd: str, host: str, port: int, label: str) -> str:
    enc_label = urllib.parse.quote(label)
    if proto == "hysteria2":
        return f"hysteria2://{uname}:{pwd}@{host}:{port}/?sni={host}#{enc_label}"
    if proto == "vless":
        reality_sni = os.environ.get("REALITY_SNI", "www.microsoft.com")
        return (
            f"vless://{pwd}@{host}:{port}"
            f"?encryption=none&flow=xtls-rprx-vision&security=reality"
            f"&sni={reality_sni}&fp=chrome&type=tcp#{enc_label}"
        )
    if proto == "trojan":
        return f"trojan://{pwd}@{host}:{port}?sni={host}#{enc_label}"
    return ""


def make_links(uname: str, pwd: str) -> list[dict]:
    links = []
    for h in list_hosts(active_only=True):
        protocols = h.get("protocols", '["hysteria2"]')
        node_ports = h.get("node_ports", "{}")
        if isinstance(protocols, str):
            protocols = json.loads(protocols)
        if isinstance(node_ports, str):
            node_ports = json.loads(node_ports)
        for proto in protocols:
            port = node_ports.get(proto, h["port"])
            label = f"{h['name']} ({proto})"
            uri = _build_uri(proto, uname, pwd, h["address"], port, label)
            if uri:
                links.append({"uri": uri, "label": label, "host": h["address"], "proto": proto})
    return links


def fmt_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024  # type: ignore
    return f"{n:.1f} PB"


def make_base_headers(
    uname: str,
    day: int,
    base_url: str,
    subscription_path: str,
    sid: str,
    traffic_limit: int = 0,
    expires_at: int = 0,
) -> tuple[str, dict]:
    profile_name_tpl = get_config("profile_name_tpl", "hystron for {uname}")
    profile_name = profile_name_tpl.format(uname=uname)
    title_b64 = base64.b64encode(profile_name.encode()).decode()
    headers = {
        "profile-update-interval": "12",
        "subscription-userinfo": f"upload=0; download={day}; total={traffic_limit}; expire={expires_at}",
        "content-disposition": f"attachment; filename*=UTF-8''{urllib.parse.quote(profile_name)}",
        "profile-web-page-url": f"{base_url}{subscription_path}/{sid}",
        "profile-title": f"base64:{title_b64}",
        "support-url": get_config("support_url", ""),
    }
    announce_text = get_config("announce", "")
    if announce_text:
        announce_text = announce_text[:200]
        headers["announce"] = "base64:" + base64.b64encode(announce_text.encode()).decode()
    announce_url = get_config("announce-url", "")
    if announce_url:
        headers["announce-url"] = announce_url
    return title_b64, headers


def build_singbox(uname: str, pwd: str, base_headers: dict) -> PlainTextResponse:
    hosts = list_hosts(active_only=True)
    cfg = json.load(open(get_template_file("singbox.json")))
    proxy_names = []
    for h in hosts:
        protocols = h.get("protocols", '["hysteria2"]')
        node_ports = h.get("node_ports", "{}")
        if isinstance(protocols, str):
            protocols = json.loads(protocols)
        if isinstance(node_ports, str):
            node_ports = json.loads(node_ports)
        for proto in protocols:
            port = node_ports.get(proto, h["port"])
            tag = f"{h['name']} ({proto})"
            proxy_names.append(tag)
            outbound = _singbox_outbound(proto, uname, pwd, h["address"], port, tag)
            if outbound:
                cfg["outbounds"].append(outbound)
    cfg["outbounds"][0]["outbounds"] = proxy_names
    return PlainTextResponse(
        json.dumps(cfg, indent=4, ensure_ascii=False),
        media_type="application/json",
        headers=base_headers,
    )


def _singbox_outbound(proto: str, uname: str, pwd: str, host: str, port: int, tag: str) -> dict | None:
    if proto == "hysteria2":
        return {
            "type": "hysteria2",
            "tag": tag,
            "server": host,
            "server_port": port,
            "password": f"{uname}:{pwd}",
            "tls": {"enabled": True, "server_name": host},
        }
    if proto == "vless":
        reality_sni = os.environ.get("REALITY_SNI", "www.microsoft.com")
        return {
            "type": "vless",
            "tag": tag,
            "server": host,
            "server_port": port,
            "uuid": pwd,
            "flow": "xtls-rprx-vision",
            "tls": {
                "enabled": True,
                "server_name": reality_sni,
                "utls": {"enabled": True, "fingerprint": "chrome"},
                "reality": {"enabled": True},
            },
        }
    if proto == "trojan":
        return {
            "type": "trojan",
            "tag": tag,
            "server": host,
            "server_port": port,
            "password": pwd,
            "tls": {"enabled": True, "server_name": host},
        }
    return None


def build_clash(uname: str, pwd: str, base_headers: dict) -> PlainTextResponse:
    hosts = list_hosts(active_only=True)
    proxy_lines = []
    proxy_names = []
    for h in hosts:
        protocols = h.get("protocols", '["hysteria2"]')
        node_ports = h.get("node_ports", "{}")
        if isinstance(protocols, str):
            protocols = json.loads(protocols)
        if isinstance(node_ports, str):
            node_ports = json.loads(node_ports)
        for proto in protocols:
            port = node_ports.get(proto, h["port"])
            name = f"{h['name']} ({proto})"
            proxy_names.append(name)
            proxy_lines.append(_clash_proxy(proto, name, uname, pwd, h["address"], port))

    proxies_yaml = "".join(p for p in proxy_lines if p)
    proxy_names_yaml = "\n      - ".join(proxy_names)
    template = open(get_template_file("clash.yaml")).read()
    return PlainTextResponse(
        template.format(proxy_names_yaml, proxies=proxies_yaml.rstrip("\n")),
        media_type="text/yaml",
        headers=base_headers,
    )


def _clash_proxy(proto: str, name: str, uname: str, pwd: str, host: str, port: int) -> str:
    if proto == "hysteria2":
        return (
            f"  - name: {name}\n"
            f"    type: hysteria2\n"
            f"    server: {host}\n"
            f"    port: {port}\n"
            f"    password: {uname}:{pwd}\n"
            f"    skip-cert-verify: true\n"
        )
    if proto == "vless":
        reality_sni = os.environ.get("REALITY_SNI", "www.microsoft.com")
        return (
            f"  - name: {name}\n"
            f"    type: vless\n"
            f"    server: {host}\n"
            f"    port: {port}\n"
            f"    uuid: {pwd}\n"
            f"    flow: xtls-rprx-vision\n"
            f"    network: tcp\n"
            f"    tls: true\n"
            f"    servername: {reality_sni}\n"
            f"    reality-opts:\n"
            f"      public-key: ''\n"
            f"    client-fingerprint: chrome\n"
        )
    if proto == "trojan":
        return (
            f"  - name: {name}\n"
            f"    type: trojan\n"
            f"    server: {host}\n"
            f"    port: {port}\n"
            f"    password: {pwd}\n"
            f"    sni: {host}\n"
            f"    skip-cert-verify: true\n"
        )
    return ""


def build_xray(uname: str, pwd: str, base_headers: dict) -> PlainTextResponse:
    hosts = list_hosts(active_only=True)
    configs = []
    for h in hosts:
        protocols = h.get("protocols", '["hysteria2"]')
        node_ports = h.get("node_ports", "{}")
        if isinstance(protocols, str):
            protocols = json.loads(protocols)
        if isinstance(node_ports, str):
            node_ports = json.loads(node_ports)
        for proto in protocols:
            port = node_ports.get(proto, h["port"])
            tag = f"{h['name']} ({proto})"
            cfg = json.load(open(get_template_file("xray.json")))
            cfg["remarks"] = tag
            outbound = _xray_outbound(proto, uname, pwd, h["address"], port, tag)
            if outbound:
                cfg["outbounds"].append(outbound)
            configs.append(cfg)
    return PlainTextResponse(
        json.dumps(configs, indent=2, ensure_ascii=False),
        media_type="application/json",
        headers=base_headers,
    )


def _xray_outbound(proto: str, uname: str, pwd: str, host: str, port: int, tag: str) -> dict | None:
    if proto == "hysteria2":
        return {
            "tag": tag,
            "protocol": "hysteria",
            "settings": {
                "version": 2,
                "address": host,
                "port": port,
            },
            "streamSettings": {
                "network": "hysteria",
                "hysteriaSettings": {"version": 2, "auth": f"{uname}:{pwd}"},
                "security": "tls",
                "tlsSettings": {
                    "serverName": host,
                    "allowInsecure": True,
                    "alpn": ["h3"],
                },
            },
        }
    if proto == "vless":
        reality_sni = os.environ.get("REALITY_SNI", "www.microsoft.com")
        return {
            "tag": tag,
            "protocol": "vless",
            "settings": {
                "vnext": [
                    {
                        "address": host,
                        "port": port,
                        "users": [{"id": pwd, "encryption": "none", "flow": "xtls-rprx-vision"}],
                    }
                ]
            },
            "streamSettings": {
                "network": "tcp",
                "security": "reality",
                "realitySettings": {
                    "serverName": reality_sni,
                    "fingerprint": "chrome",
                },
            },
        }
    if proto == "trojan":
        return {
            "tag": tag,
            "protocol": "trojan",
            "settings": {"servers": [{"address": host, "port": port, "password": pwd}]},
            "streamSettings": {
                "network": "tcp",
                "security": "tls",
                "tlsSettings": {"serverName": host, "allowInsecure": True},
            },
        }
    return None


def build_plain(uname: str, pwd: str, base_headers: dict) -> PlainTextResponse:
    links = make_links(uname, pwd)
    body = "\n".join(lnk["uri"] for lnk in links)
    return PlainTextResponse(
        base64.b64encode(body.encode()).decode(),
        headers=base_headers,
    )


def build_browser_ctx(
    uname: str,
    active: int,
    sub_url: str,
    link_list: list[dict],
    hour: int,
    day: int,
    week: int,
    alltime: int,
) -> dict:
    traffic_tiles = (
        [
            {"label": "hour", "val": fmt_bytes(hour)},
            {"label": "day", "val": fmt_bytes(day)},
            {"label": "week", "val": fmt_bytes(week)},
            {"label": "all-time", "val": fmt_bytes(alltime)},
        ]
        if alltime or hour
        else []
    )

    return {
        "username": uname,
        "sub_url": sub_url,
        "links": link_list,
        "traffic_tiles": traffic_tiles,
        "active": active,
        "support_url": get_config("support_url", ""),
    }
