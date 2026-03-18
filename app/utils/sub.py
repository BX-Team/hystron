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


def make_links(uname: str, pwd: str) -> list[dict]:
    return [
        {
            "uri": f"hysteria2://{uname}:{pwd}@{h['address']}:{h['port']}/?sni={h['address']}#{h['name']}",
            "label": h["name"],
            "host": h["address"],
        }
        for h in list_hosts(active_only=True)
    ]


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
    profile_name_tpl = get_config("profile_name_tpl", "hysteria for {uname}")
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
    config = json.load(open(get_template_file("singbox.json")))
    proxy_names = []
    for h in hosts:
        proxy_names.append(h["name"])
        config["outbounds"].append(
            {
                "type": "hysteria2",
                "tag": h["name"],
                "server": h["address"],
                "server_port": h["port"],
                "password": f"{uname}:{pwd}",
                "tls": {"enabled": True, "server_name": h["address"]},
            }
        )
    config["outbounds"][0]["outbounds"] = proxy_names
    return PlainTextResponse(
        json.dumps(config, indent=4, ensure_ascii=False),
        media_type="application/json",
        headers=base_headers,
    )


def build_clash(uname: str, pwd: str, base_headers: dict) -> PlainTextResponse:
    hosts = list_hosts(active_only=True)
    proxies_yaml = "".join(
        f"  - name: {h['name']}\n"
        f"    type: hysteria2\n"
        f"    server: {h['address']}\n"
        f"    port: {h['port']}\n"
        f"    password: {uname}:{pwd}\n"
        f"    skip-cert-verify: true\n"
        for h in hosts
    )
    proxy_names_yaml = "\n      - ".join(h["name"] for h in hosts)
    template = open(get_template_file("clash.yaml")).read()
    return PlainTextResponse(
        template.format(proxy_names_yaml, proxies=proxies_yaml.rstrip("\n")),
        media_type="text/yaml",
        headers=base_headers,
    )


def build_xray(uname: str, pwd: str, base_headers: dict) -> PlainTextResponse:
    hosts = list_hosts(active_only=True)
    configs = []
    for h in hosts:
        config = json.load(open(get_template_file("xray.json")))
        config["remarks"] = h["name"]
        config["outbounds"].insert(
            0,
            {
                "tag": "proxy",
                "protocol": "hysteria",
                "settings": {
                    "version": 2,
                    "address": h["address"],
                    "port": h["port"],
                },
                "streamSettings": {
                    "network": "hysteria",
                    "hysteriaSettings": {
                        "version": 2,
                        "auth": f"{uname}:{pwd}",
                    },
                    "security": "tls",
                    "tlsSettings": {
                        "serverName": h["address"],
                        "allowInsecure": True,
                        "alpn": ["h3"],
                    },
                },
            },
        )
        configs.append(config)

    return PlainTextResponse(
        json.dumps(configs, indent=2, ensure_ascii=False),
        media_type="application/json",
        headers=base_headers,
    )


def build_plain(uname: str, pwd: str, base_headers: dict) -> PlainTextResponse:
    hosts = list_hosts(active_only=True)
    body = "\n".join(
        f"hysteria2://{uname}:{pwd}@{h['address']}:{h['port']}/?sni={h['address']}#{h['name']}" for h in hosts
    )
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
