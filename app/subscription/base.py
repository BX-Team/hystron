import urllib.parse
from abc import ABC, abstractmethod

from fastapi.responses import PlainTextResponse


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
