import base64
import json
import os
import urllib.parse
from abc import ABC, abstractmethod

from fastapi.responses import PlainTextResponse

from app.db.database import get_config, list_hosts_for_user

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
            uri = f"hysteria2://{uname}:{pwd}@{h['address']}:{h['port']}/?sni={h['address']}#{h['name']}"
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


# ---------------------------------------------------------------------------
# Class-based subscription builders (registry pattern)
# ---------------------------------------------------------------------------


class BaseHystronSubscription(ABC):
    """
    Base class for subscription format builders.
    Subclasses register protocol handlers and implement render().
    """

    def __init__(self):
        self.proxy_names: list[str] = []
        self.protocol_handlers: dict = {
            "hysteria2": self._add_hysteria2,
            "vless": self._add_vless,
            "trojan": self._add_trojan,
        }

    def _resolve_protocol(self, h: dict) -> str:
        if h.get("host_type") == "hystron_node":
            return (h.get("protocol") or "trojan").lower()
        return "hysteria2"

    @staticmethod
    def _parse_sub_params(h: dict) -> dict:
        """Parse sub_params query string into a dict."""
        return dict(urllib.parse.parse_qsl(h.get("sub_params") or ""))

    def add(self, h: dict, uname: str, pwd: str):
        proto = self._resolve_protocol(h)
        handler = self.protocol_handlers.get(proto)
        if handler:
            handler(h, uname, pwd)
            self.proxy_names.append(h["name"])

    @abstractmethod
    def _add_hysteria2(self, h: dict, uname: str, pwd: str): ...

    @abstractmethod
    def _add_vless(self, h: dict, uname: str, pwd: str): ...

    @abstractmethod
    def _add_trojan(self, h: dict, uname: str, pwd: str): ...

    @abstractmethod
    def render(self, base_headers: dict) -> PlainTextResponse: ...


class SingBoxSubscription(BaseHystronSubscription):
    def __init__(self):
        super().__init__()
        self.config = json.load(open(get_template_file("singbox.json")))

    def _add_hysteria2(self, h, uname, pwd):
        self.config["outbounds"].append(
            {
                "type": "hysteria2",
                "tag": h["name"],
                "server": h["address"],
                "server_port": h["port"],
                "password": f"{uname}:{pwd}",
                "tls": {"enabled": True, "server_name": h["address"]},
            }
        )

    def _add_vless(self, h, uname, pwd):
        params = self._parse_sub_params(h)
        port = h.get("inbound_port") or h["port"]
        sni = params.get("sni", "")
        pbk = params.get("pbk", "")
        sid = params.get("sid", "")
        fp = params.get("fp", "chrome")
        security = params.get("security", "tls")

        outbound: dict = {
            "type": "vless",
            "tag": h["name"],
            "server": h["address"],
            "server_port": port,
            "uuid": pwd,
            "packet_encoding": "xudp",
        }
        if h.get("flow"):
            outbound["flow"] = h["flow"]

        tls: dict = {"enabled": True, "server_name": sni}
        if fp:
            tls["utls"] = {"enabled": True, "fingerprint": fp}
        if security == "reality" and pbk:
            tls["reality"] = {"enabled": True, "public_key": pbk, "short_id": sid}
        outbound["tls"] = tls

        self.config["outbounds"].append(outbound)

    def _add_trojan(self, h, uname, pwd):
        params = self._parse_sub_params(h)
        port = h.get("inbound_port") or h["port"]
        sni = params.get("sni", h["address"])

        self.config["outbounds"].append(
            {
                "type": "trojan",
                "tag": h["name"],
                "server": h["address"],
                "server_port": port,
                "password": pwd,
                "tls": {"enabled": True, "server_name": sni},
            }
        )

    def render(self, base_headers: dict) -> PlainTextResponse:
        self.config["outbounds"][0]["outbounds"] = self.proxy_names
        return PlainTextResponse(
            json.dumps(self.config, indent=4, ensure_ascii=False),
            media_type="application/json",
            headers=base_headers,
        )


class ClashSubscription(BaseHystronSubscription):
    def __init__(self):
        super().__init__()
        self.proxy_lines: list[str] = []

    def _add_hysteria2(self, h, uname, pwd):
        self.proxy_lines.append(
            f"  - name: {h['name']}\n"
            f"    type: hysteria2\n"
            f"    server: {h['address']}\n"
            f"    port: {h['port']}\n"
            f"    password: {uname}:{pwd}\n"
            f"    skip-cert-verify: true\n"
        )

    def _add_vless(self, h, uname, pwd):
        params = self._parse_sub_params(h)
        port = h.get("inbound_port") or h["port"]
        flow = h.get("flow") or ""
        sni = params.get("sni", "")
        pbk = params.get("pbk", "")
        sid = params.get("sid", "")
        fp = params.get("fp", "chrome")
        security = params.get("security", "tls")

        lines = (
            f"  - name: {h['name']}\n"
            f"    type: vless\n"
            f"    server: {h['address']}\n"
            f"    port: {port}\n"
            f"    uuid: {pwd}\n"
            f"    network: tcp\n"
            f"    tls: true\n"
            f"    udp: true\n"
            f"    servername: {sni}\n"
            f"    client-fingerprint: {fp}\n"
        )
        if flow:
            lines += f"    flow: {flow}\n"
        if security == "reality" and pbk:
            lines += "    reality-opts:\n"
            lines += f"      public-key: {pbk}\n"
            if sid:
                lines += f"      short-id: {sid}\n"
        self.proxy_lines.append(lines)

    def _add_trojan(self, h, uname, pwd):
        params = self._parse_sub_params(h)
        port = h.get("inbound_port") or h["port"]
        sni = params.get("sni", h["address"])
        fp = params.get("fp", "")

        lines = (
            f"  - name: {h['name']}\n"
            f"    type: trojan\n"
            f"    server: {h['address']}\n"
            f"    port: {port}\n"
            f"    password: {pwd}\n"
            f"    sni: {sni}\n"
            f"    skip-cert-verify: true\n"
        )
        if fp:
            lines += f"    client-fingerprint: {fp}\n"
        self.proxy_lines.append(lines)

    def render(self, base_headers: dict) -> PlainTextResponse:
        proxies_yaml = "".join(self.proxy_lines)
        proxy_names_yaml = "\n      - ".join(self.proxy_names)
        template = open(get_template_file("clash.yaml")).read()
        return PlainTextResponse(
            template.format(proxy_names_yaml, proxies=proxies_yaml.rstrip("\n")),
            media_type="text/yaml",
            headers=base_headers,
        )


class XraySubscription(BaseHystronSubscription):
    def __init__(self):
        super().__init__()
        self.configs: list[dict] = []

    def _add_hysteria2(self, h, uname, pwd):
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
        self.configs.append(config)

    def _add_vless(self, h, uname, pwd):
        params = self._parse_sub_params(h)
        port = h.get("inbound_port") or h["port"]
        flow = h.get("flow") or ""
        sni = params.get("sni", "")
        pbk = params.get("pbk", "")
        sid = params.get("sid", "")
        fp = params.get("fp", "chrome")
        security = params.get("security", "tls")

        user: dict = {"id": pwd, "encryption": "none"}
        if flow:
            user["flow"] = flow

        stream: dict = {"network": "tcp", "security": security}
        if security == "reality":
            stream["realitySettings"] = {
                "fingerprint": fp,
                "serverName": sni,
                "publicKey": pbk,
                "shortId": sid,
            }
        else:
            stream["tlsSettings"] = {"serverName": sni, "fingerprint": fp}

        config = json.load(open(get_template_file("xray.json")))
        config["remarks"] = h["name"]
        config["outbounds"].insert(
            0,
            {
                "tag": "proxy",
                "protocol": "vless",
                "settings": {"vnext": [{"address": h["address"], "port": port, "users": [user]}]},
                "streamSettings": stream,
            },
        )
        self.configs.append(config)

    def _add_trojan(self, h, uname, pwd):
        params = self._parse_sub_params(h)
        port = h.get("inbound_port") or h["port"]
        sni = params.get("sni", h["address"])
        fp = params.get("fp", "")

        tls_settings: dict = {"serverName": sni, "allowInsecure": False}
        if fp:
            tls_settings["fingerprint"] = fp

        config = json.load(open(get_template_file("xray.json")))
        config["remarks"] = h["name"]
        config["outbounds"].insert(
            0,
            {
                "tag": "proxy",
                "protocol": "trojan",
                "settings": {"servers": [{"address": h["address"], "port": port, "password": pwd}]},
                "streamSettings": {"network": "tcp", "security": "tls", "tlsSettings": tls_settings},
            },
        )
        self.configs.append(config)

    def render(self, base_headers: dict) -> PlainTextResponse:
        return PlainTextResponse(
            json.dumps(self.configs, indent=2, ensure_ascii=False),
            media_type="application/json",
            headers=base_headers,
        )


class PlainSubscription(BaseHystronSubscription):
    def __init__(self):
        super().__init__()
        self.uris: list[str] = []

    def _add_hysteria2(self, h, uname, pwd):
        self.uris.append(f"hysteria2://{uname}:{pwd}@{h['address']}:{h['port']}/?sni={h['address']}#{h['name']}")

    def _add_vless(self, h, uname, pwd):
        addr = h["address"]
        port = h.get("inbound_port") or h["port"]
        label = h["name"]
        flow = h.get("flow") or ""
        qs = h.get("sub_params") or ""
        if flow:
            qs = f"{qs}&flow={flow}" if qs else f"flow={flow}"
        self.uris.append(f"vless://{pwd}@{addr}:{port}?{qs}#{label}" if qs else f"vless://{pwd}@{addr}:{port}#{label}")

    def _add_trojan(self, h, uname, pwd):
        addr = h["address"]
        port = h.get("inbound_port") or h["port"]
        label = h["name"]
        qs = h.get("sub_params") or ""
        self.uris.append(
            f"trojan://{pwd}@{addr}:{port}?{qs}#{label}" if qs else f"trojan://{pwd}@{addr}:{port}#{label}"
        )

    def render(self, base_headers: dict) -> PlainTextResponse:
        body = "\n".join(self.uris)
        return PlainTextResponse(
            base64.b64encode(body.encode()).decode(),
            headers=base_headers,
        )


# ---------------------------------------------------------------------------
# Backward-compatible builder functions (used by routes)
# ---------------------------------------------------------------------------


def _build_subscription(cls: type, uname: str, pwd: str, base_headers: dict) -> PlainTextResponse:
    sub = cls()
    for h in list_hosts_for_user(uname, active_only=True):
        sub.add(h, uname, pwd)
    return sub.render(base_headers)


def build_singbox(uname: str, pwd: str, base_headers: dict) -> PlainTextResponse:
    return _build_subscription(SingBoxSubscription, uname, pwd, base_headers)


def build_clash(uname: str, pwd: str, base_headers: dict) -> PlainTextResponse:
    return _build_subscription(ClashSubscription, uname, pwd, base_headers)


def build_xray(uname: str, pwd: str, base_headers: dict) -> PlainTextResponse:
    return _build_subscription(XraySubscription, uname, pwd, base_headers)


def build_plain(uname: str, pwd: str, base_headers: dict) -> PlainTextResponse:
    return _build_subscription(PlainSubscription, uname, pwd, base_headers)
