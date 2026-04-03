from fastapi.responses import PlainTextResponse

from app.db.database import list_hosts_for_user

from .clash import ClashSubscription
from .plain import PlainSubscription
from .singbox import SingBoxSubscription
from .xray import XraySubscription


def _build_subscription(cls: type, uname: str, pwd: str, base_headers: dict) -> PlainTextResponse:
    sub = cls()
    for h in list_hosts_for_user(uname, active_only=True):
        sub.add(h, uname, pwd)
    return sub.render(base_headers)


def build_singbox(uname: str, pwd: str, base_headers: dict) -> PlainTextResponse:
    return _build_subscription(SingBoxSubscription, uname, pwd, base_headers)


def build_clash(uname: str, pwd: str, base_headers: dict) -> PlainTextResponse:
    return _build_subscription(ClashSubscription, uname, pwd, base_headers)


def build_plain(uname: str, pwd: str, base_headers: dict) -> PlainTextResponse:
    return _build_subscription(PlainSubscription, uname, pwd, base_headers)


def build_xray(uname: str, pwd: str, base_headers: dict) -> PlainTextResponse:
    return _build_subscription(XraySubscription, uname, pwd, base_headers)
