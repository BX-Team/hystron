from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from app.db.database import check_auth, get_config

router = APIRouter(tags=["Auth"])


def is_ip_whitelisted(ip: str) -> bool:
    """Return True if whitelist is disabled or the IP is in the whitelist."""
    if get_config("whitelist_enable", "false").lower() not in ("true", "1"):
        return True
    whitelist = set(get_config("whitelist", "").split())
    return ip in whitelist


@router.post("/auth")
async def auth(request: Request):
    if not is_ip_whitelisted(request.client.host):
        return Response(status_code=403)

    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"ok": False}, status_code=400)

    auth_field = data.get("auth", "")
    if ":" not in auth_field:
        return JSONResponse({"ok": False})

    username, password = auth_field.split(":", 1)
    ok, reason = check_auth(username, password)

    status = "ok" if ok else reason
    print(f"\nauth: {username} → {status} ({request.client.host})\n")

    if not ok:
        return JSONResponse({"ok": False})

    return JSONResponse({"ok": True, "id": username})
