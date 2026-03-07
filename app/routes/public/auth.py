from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from app.database import check_auth, get_config

router = APIRouter(tags=["Auth"])


@router.post("/auth")
async def auth(request: Request):
    whitelist_enabled = get_config("whitelist_enable", "false").lower() in ("true", "1")
    if whitelist_enabled:
        whitelist = set(get_config("whitelist", "").split())
        if request.client.host not in whitelist:
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

    return JSONResponse({"ok": ok, "id": username} if ok else {"ok": False})
