from fastapi.responses import PlainTextResponse

from .utils import get_template_file

from .base import BaseHystronSubscription


class ClashSubscription(BaseHystronSubscription):
    def __init__(self):
        super().__init__()
        self.proxy_lines: list[str] = []

    def _add_hysteria2(self, h: dict, uname: str, pwd: str):
        lines = (
            f"  - name: {h['name']}\n"
            f"    type: hysteria2\n"
            f"    server: {h['address']}\n"
            f"    port: {h['port']}\n"
            f"    password: {uname}:{pwd}\n"
        )
        if h.get("up_mbps"):
            lines += f"    up: \"{h['up_mbps']} Mbps\"\n"
        if h.get("down_mbps"):
            lines += f"    down: \"{h['down_mbps']} Mbps\"\n"
        lines += "    skip-cert-verify: true\n"
        self.proxy_lines.append(lines)

    def _add_vless(self, h: dict, uname: str, pwd: str):
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

    def _add_trojan(self, h: dict, uname: str, pwd: str):
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
