from typing import Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.database import (
    create_user,
    delete_device,
    delete_user,
    edit_user,
    get_user,
    list_devices,
    list_users_with_traffic,
    user_exists,
)
from app.events import emit

router = APIRouter(prefix="/api", tags=["Users"])


class CreateBody(BaseModel):
    username: str
    traffic_limit: int = 0
    expires_at: int = 0
    device_limit: int = 0


class EditBody(BaseModel):
    password: Optional[str] = None
    sid: Optional[str] = None
    active: Optional[bool] = None
    traffic_limit: Optional[int] = None
    expires_at: Optional[int] = None
    device_limit: Optional[int] = None


def _row_to_dict(row) -> dict:
    return {
        "username": row["username"],
        "password": row["password"],
        "sid": row["sid"],
        "active": bool(row["active"]),
        "traffic_limit": row["traffic_limit"],
        "expires_at": row["expires_at"],
        "device_limit": row["device_limit"],
    }


@router.get("/users")
def users_list():
    return [{**_row_to_dict(r), "traffic_total": r["total"]} for r in list_users_with_traffic()]


@router.post("/users", status_code=201)
async def users_create(body: CreateBody):
    username = body.username.strip()
    if not username:
        return JSONResponse({"error": "username required"}, status_code=400)
    result = create_user(
        username,
        traffic_limit=body.traffic_limit,
        expires_at=body.expires_at,
        device_limit=body.device_limit,
    )
    if result is None:
        return JSONResponse({"error": "already exists"}, status_code=409)
    await emit(
        "user.created",
        {
            "username": username,
            "traffic_limit": body.traffic_limit,
            "expires_at": body.expires_at,
            "device_limit": body.device_limit,
        },
    )
    return result


@router.get("/users/{username}")
def users_get(username: str):
    row = get_user(username)
    if not row:
        return JSONResponse({"error": "not found"}, status_code=404)
    return _row_to_dict(row)


@router.patch("/users/{username}")
async def users_edit(username: str, body: EditBody):
    if not user_exists(username):
        return JSONResponse({"error": "not found"}, status_code=404)
    edit_user(
        username,
        password=body.password,
        sid=body.sid,
        active=body.active,
        traffic_limit=body.traffic_limit,
        expires_at=body.expires_at,
        device_limit=body.device_limit,
    )
    updated = _row_to_dict(get_user(username))
    await emit("user.updated", updated)
    return updated


@router.delete("/users/{username}")
async def users_delete(username: str):
    if not delete_user(username):
        return JSONResponse({"error": "not found"}, status_code=404)
    await emit("user.deleted", {"username": username})
    return {"ok": True}


@router.get("/users/{username}/devices")
def users_devices_list(username: str):
    if not user_exists(username):
        return JSONResponse({"error": "not found"}, status_code=404)
    return list_devices(username)


@router.delete("/users/{username}/devices/{device_id}")
def users_devices_delete(username: str, device_id: int):
    if not user_exists(username):
        return JSONResponse({"error": "not found"}, status_code=404)
    if not delete_device(device_id):
        return JSONResponse({"error": "not found"}, status_code=404)
    return {"ok": True}
