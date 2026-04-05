import asyncio
import re

import httpx
import jinja2
from fastapi import APIRouter, Request
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates

from app.db.database import get_config, get_traffic, get_user_by_sid, list_hosts, register_device
from app.subscription import (
    build_browser_ctx,
    build_clash,
    build_plain,
    build_singbox,
    build_xray,
    get_templates_search_dirs,
    make_base_headers,
    make_links,
)

router = APIRouter(tags=["Subscription"])


def _make_templates() -> Jinja2Templates:
    """Build a Jinja2Templates instance that checks the override directory first."""
    return Jinja2Templates(
        env=jinja2.Environment(
            loader=jinja2.FileSystemLoader(get_templates_search_dirs()),
            autoescape=jinja2.select_autoescape(["html"]),
        )
    )


SUBSCRIPTION_PATH = get_config("subscription_path", "/sub")
_BROWSER_KW = (
    "Mozilla",
    "Chrome",
    "Safari",
    "Firefox",
    "Opera",
    "Edge",
    "TelegramBot",
    "WhatsApp",
)


@router.get("/hosts/status", include_in_schema=False)
async def hosts_status():
    """Return online/offline status for each active host (checked via their internal API)."""
    from app.node.client import get_node_status

    hosts = list_hosts(active_only=True)
    result = {}
    async with httpx.AsyncClient(timeout=3) as client:
        for h in hosts:
            if h.get("host_type") == "hystron_node":
                try:
                    loop = asyncio.get_event_loop()
                    status = await loop.run_in_executor(None, get_node_status, h)
                    result[h["address"]] = "online" if status.get("xray_running") else "offline"
                except Exception:
                    result[h["address"]] = "offline"
            else:
                api_address = h.get("api_address") or ""
                if not api_address:
                    result[h["address"]] = "offline"
                    continue
                api_url = api_address.rstrip("/")
                try:
                    r = await client.get(
                        f"{api_url}/traffic",
                        headers={"Authorization": h.get("api_secret") or ""},
                    )
                    result[h["address"]] = "online" if r.status_code == 200 else "offline"
                except Exception:
                    result[h["address"]] = "offline"
    return result


_RE_SINGBOX = re.compile(r"^(SFA|SFI|SFM|SFT|[Kk]aring|[Hh]iddify[Nn]ext)|.*[Ss]ing[\-b]?ox.*")
_RE_CLASH = re.compile(r"^([Cc]lash[\-\.]?[Vv]erge|[Cc]lash[\-\.]?[Mm]eta|[Ff][Ll][Cc]lash|[Mm]ihomo|[Ss]tash)")
_RE_XRAY = re.compile(r"^([Vv]2rayNG|[Vv]2rayN|[Ss]treisand|[Hh]app|[Kk]tor\-client)|INCY/[\d.]+")


def _get_base_url(request: Request) -> str:
    cfg = get_config("base_url", "").rstrip("/")
    if cfg:
        return cfg
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    return f"{proto}://{request.url.netloc}"


@router.head(f"{SUBSCRIPTION_PATH}/{{sid}}")
@router.get(f"{SUBSCRIPTION_PATH}/{{sid}}")
async def subscription(sid: str, request: Request):
    user = get_user_by_sid(sid)

    if not user:
        return Response(status_code=404)

    base_url = _get_base_url(request)
    uname, pwd = user["username"], user["password"]
    sub_url = f"{base_url}{SUBSCRIPTION_PATH}/{sid}"
    link_list = make_links(uname, pwd)
    ua = request.headers.get("user-agent", "")
    accept = request.headers.get("accept", "")
    is_browser = "text/html" in accept or any(k in ua for k in _BROWSER_KW)

    stats = get_traffic(uname)
    t = stats[0] if stats else {}
    hour = t.get("hour", 0)
    day = t.get("day", 0)
    week = t.get("week", 0)
    alltime = t.get("total", 0)

    if not is_browser:
        print(f"\nsub: {uname} | {ua} | {request.client.host}\n")

        hwid = request.headers.get("x-hwid", "").strip()
        if hwid:
            allowed = register_device(
                uname,
                hwid,
                request.headers.get("x-device-os", ""),
                request.headers.get("x-ver-os", ""),
                request.headers.get("x-device-model", ""),
                request.headers.get("x-app-version", ""),
            )
            if not allowed:
                print(f"\nsub: {uname} → devicelimit ({request.client.host})\n")
                return Response(status_code=403)

        _, base_headers = make_base_headers(
            uname,
            day,
            base_url,
            SUBSCRIPTION_PATH,
            sid,
            user["traffic_limit"],
            user["expires_at"],
        )

        if _RE_SINGBOX.search(ua):
            return build_singbox(uname, pwd, base_headers)
        if _RE_CLASH.search(ua):
            return build_clash(uname, pwd, base_headers)
        if _RE_XRAY.search(ua):
            return build_xray(uname, pwd, base_headers)
        return build_plain(uname, pwd, base_headers)

    print(f"\nbrowser: {uname} | {request.client.host}\n")

    ctx = build_browser_ctx(uname, user["active"], sub_url, link_list, hour, day, week, alltime, user["expires_at"])
    return _make_templates().TemplateResponse("index.html", {"request": request, **ctx})
