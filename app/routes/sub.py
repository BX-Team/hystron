import os
import re

from fastapi import APIRouter, Request
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates

from ..database import get_db, get_traffic
from ..utils.sub import (
    make_links, make_base_headers,
    build_singbox, build_clash, build_plain, build_browser_ctx,
)

router    = APIRouter(tags=["Subscription"])
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "templates"))

_BROWSER_KW = ("Mozilla", "Chrome", "Safari", "Firefox", "Opera", "Edge", "TelegramBot", "WhatsApp")
_RE_SINGBOX = re.compile(r"sing-box|Hiddify|SFI|SFA|SFM", re.IGNORECASE)
_RE_CLASH   = re.compile(r"Clash|Stash|mihomo", re.IGNORECASE)


def _get_base_url(request: Request) -> str:
    return f"{request.url.scheme}://{request.url.netloc}"


@router.head("/sub/{sid}")
@router.get("/sub/{sid}")
async def subscription(sid: str, request: Request):
    conn = get_db()
    cur  = conn.cursor()
    cur.execute("SELECT * FROM users WHERE sid = ?", (sid,))
    user = cur.fetchone()
    conn.close()

    if not user:
        return Response(status_code=404)

    base_url   = _get_base_url(request)
    uname, pwd = user["username"], user["password"]
    sub_url    = f"{base_url}/sub/{sid}"
    link_list  = make_links(uname, pwd)
    ua         = request.headers.get("user-agent", "")
    accept     = request.headers.get("accept", "")
    is_browser = "text/html" in accept or any(k in ua for k in _BROWSER_KW)

    stats   = get_traffic(uname)
    t       = stats[0] if stats else {}
    hour    = t.get("hour",  0)
    day     = t.get("day",   0)
    week    = t.get("week",  0)
    alltime = t.get("total", 0)

    if not is_browser:
        print(f"\nsub: {uname} | {ua} | {request.client.host}\n")
        title_b64, base_headers = make_base_headers(uname, day, alltime, base_url, sid)

        if _RE_SINGBOX.search(ua):
            return build_singbox(uname, pwd, base_headers)
        if _RE_CLASH.search(ua):
            return build_clash(uname, pwd, base_headers)
        return build_plain(uname, pwd, title_b64, base_headers)

    print(f"\nbrowser: {uname} | {request.client.host}\n")

    ctx = build_browser_ctx(uname, user["active"], sub_url, link_list, hour, day, week, alltime)
    return templates.TemplateResponse("index.html", {"request": request, **ctx})
