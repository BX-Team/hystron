import json

from fastapi.responses import PlainTextResponse

from .utils import get_template_file

from .base import BaseHystronSubscription


class SingBoxSubscription(BaseHystronSubscription):
    def __init__(self):
        super().__init__()
        self.config = json.load(open(get_template_file("singbox.json")))

    def _add_hysteria2(self, h: dict, uname: str, pwd: str):
        outbound: dict = {
            "type": "hysteria2",
            "tag": h["name"],
            "server": h["address"],
            "server_port": h["port"],
            "password": f"{uname}:{pwd}",
            "tls": {"enabled": True, "server_name": h["address"]},
        }
        if h.get("up_mbps"):
            outbound["up_mbps"] = h["up_mbps"]
        if h.get("down_mbps"):
            outbound["down_mbps"] = h["down_mbps"]
        self.config["outbounds"].append(outbound)

    def _add_vless(self, h: dict, uname: str, pwd: str):
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

    def _add_trojan(self, h: dict, uname: str, pwd: str):
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
