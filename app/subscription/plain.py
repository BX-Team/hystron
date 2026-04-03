import base64

from fastapi.responses import PlainTextResponse

from .base import BaseHystronSubscription


class PlainSubscription(BaseHystronSubscription):
    def __init__(self):
        super().__init__()
        self.uris: list[str] = []

    def _add_hysteria2(self, h: dict, uname: str, pwd: str):
        qs = f"sni={h['address']}"
        if h.get("up_mbps"):
            qs += f"&up={h['up_mbps']}"
        if h.get("down_mbps"):
            qs += f"&down={h['down_mbps']}"
        self.uris.append(f"hysteria2://{uname}:{pwd}@{h['address']}:{h['port']}/?{qs}#{h['name']}")

    def _add_vless(self, h: dict, uname: str, pwd: str):
        addr = h["address"]
        port = h.get("inbound_port") or h["port"]
        label = h["name"]
        flow = h.get("flow") or ""
        qs = h.get("sub_params") or ""
        if flow:
            qs = f"{qs}&flow={flow}" if qs else f"flow={flow}"
        self.uris.append(f"vless://{pwd}@{addr}:{port}?{qs}#{label}" if qs else f"vless://{pwd}@{addr}:{port}#{label}")

    def _add_trojan(self, h: dict, uname: str, pwd: str):
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
