import json

from fastapi.responses import PlainTextResponse

from .base import BaseHystronSubscription
from .utils import get_template_file


class XraySubscription(BaseHystronSubscription):
    """
    Builds a list of Xray JSON configs — one per host.
    Hysteria2 hosts use the `hysteria` protocol with `finalmask.quicParams`.
    VLESS/Trojan hosts use standard vnext/servers structure with TLS or REALITY.
    """

    def __init__(self):
        super().__init__()
        self._template: dict = json.load(open(get_template_file("xray.json")))
        self._configs: list[dict] = []

    # ------------------------------------------------------------------
    # Protocol handlers
    # ------------------------------------------------------------------

    def _add_hysteria2(self, h: dict, uname: str, pwd: str):
        params = self._parse_sub_params(h)
        sni = params.get("sni", h["address"])

        quic_params: dict = {}
        if h.get("up_mbps"):
            quic_params["congestion"] = "force-brutal"
            quic_params["brutalUp"] = f"{h['up_mbps']} mbps"
        if h.get("down_mbps"):
            quic_params["brutalDown"] = f"{h['down_mbps']} mbps"

        outbound: dict = {
            "protocol": "hysteria",
            "tag": "proxy",
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
                    "serverName": sni,
                    "alpn": ["h3"],
                },
            },
        }

        if quic_params:
            outbound["streamSettings"]["finalmask"] = {"quicParams": quic_params}

        self._configs.append(self._wrap(h["name"], outbound))

    def _add_vless(self, h: dict, uname: str, pwd: str):
        params = self._parse_sub_params(h)
        port = h.get("inbound_port") or h["port"]
        sni = params.get("sni", "")
        pbk = params.get("pbk", "")
        sid = params.get("sid", "")
        fp = params.get("fp", "chrome")
        security = params.get("security", "tls")

        user: dict = {"id": pwd, "encryption": "none"}
        if h.get("flow"):
            user["flow"] = h["flow"]

        stream: dict = {"network": "tcp", "security": security}
        if security == "reality":
            stream["realitySettings"] = {
                "serverName": sni,
                "fingerprint": fp,
                "publicKey": pbk,
                "shortId": sid,
            }
        else:
            tls: dict = {"serverName": sni}
            if fp:
                tls["fingerprint"] = fp
            stream["tlsSettings"] = tls

        outbound: dict = {
            "protocol": "vless",
            "tag": "proxy",
            "settings": {
                "vnext": [
                    {
                        "address": h["address"],
                        "port": port,
                        "users": [user],
                    }
                ]
            },
            "streamSettings": stream,
        }

        self._configs.append(self._wrap(h["name"], outbound))

    def _add_trojan(self, h: dict, uname: str, pwd: str):
        params = self._parse_sub_params(h)
        port = h.get("inbound_port") or h["port"]
        sni = params.get("sni", h["address"])
        fp = params.get("fp", "")

        tls_settings: dict = {"serverName": sni}
        if fp:
            tls_settings["fingerprint"] = fp

        outbound: dict = {
            "protocol": "trojan",
            "tag": "proxy",
            "settings": {
                "servers": [
                    {
                        "address": h["address"],
                        "port": port,
                        "password": pwd,
                    }
                ]
            },
            "streamSettings": {
                "network": "tcp",
                "security": "tls",
                "tlsSettings": tls_settings,
            },
        }

        self._configs.append(self._wrap(h["name"], outbound))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _wrap(self, remarks: str, proxy_outbound: dict) -> dict:
        """Merge proxy outbound into a copy of the base template."""
        cfg = json.loads(json.dumps(self._template))
        cfg["remarks"] = remarks
        cfg["outbounds"] = [proxy_outbound] + cfg["outbounds"]
        return cfg

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------

    def render(self, base_headers: dict) -> PlainTextResponse:
        return PlainTextResponse(
            json.dumps(self._configs, indent=4, ensure_ascii=False),
            media_type="application/json",
            headers=base_headers,
        )
