import base64
import os
import urllib.parse

from app.db.database import get_config, list_hosts_for_user

_BUNDLED_TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "templates")

_TEMPLATE_CONFIG_KEY: dict[str, str] = {
    "singbox.json": "template_singbox",
    "clash.yaml": "template_clash",
    "index.html": "template_index",
    "xray.json": "template_xray",
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


def make_links(uname: str, pwd: str) -> list[dict]:
    links = []
    for h in list_hosts_for_user(uname, active_only=True):
        if h.get("host_type") == "hystron_node":
            proto = (h.get("protocol") or "").lower()
            addr = h["address"]
            port = h.get("inbound_port") or h["port"]
            label = h["name"]
            sub_params = h.get("sub_params") or ""
            if proto == "vless":
                flow = h.get("flow") or ""
                qs = sub_params
                if flow:
                    qs = f"{qs}&flow={flow}" if qs else f"flow={flow}"
                uri = f"vless://{pwd}@{addr}:{port}?{qs}#{label}" if qs else f"vless://{pwd}@{addr}:{port}#{label}"
            else:
                uri = (
                    f"trojan://{pwd}@{addr}:{port}?{sub_params}#{label}"
                    if sub_params
                    else f"trojan://{pwd}@{addr}:{port}#{label}"
                )
        else:
            qs = f"sni={h['address']}"
            if h.get("up_mbps"):
                qs += f"&up={h['up_mbps']}"
            if h.get("down_mbps"):
                qs += f"&down={h['down_mbps']}"
            uri = f"hysteria2://{uname}:{pwd}@{h['address']}:{h['port']}/?{qs}#{h['name']}"
            proto = "hysteria2"
        links.append(
            {"uri": uri, "label": h["name"], "host": h["address"], "protocol": h.get("protocol") or "hysteria2"}
        )
    return links


def build_browser_ctx(
    uname: str,
    active: int,
    sub_url: str,
    link_list: list[dict],
    hour: int,
    day: int,
    week: int,
    alltime: int,
    expires_at: int = 0,
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
        "expires_at": expires_at,
        "support_url": get_config("support_url", ""),
    }
