from typing import Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ...database import (
    get_user,
    list_users_with_traffic,
    create_user,
    edit_user,
    delete_user,
    user_exists,
)

router = APIRouter(prefix="/api", tags=["Users"])


class CreateBody(BaseModel):
    username: str
    traffic_limit: int = 0  # 0 = unlimited
    expires_at: int = 0  # 0 = never


class EditBody(BaseModel):
    password: Optional[str] = None
    sid: Optional[str] = None
    active: Optional[bool] = None
    traffic_limit: Optional[int] = None
    expires_at: Optional[int] = None


def _row_to_dict(row) -> dict:
    return {
        "username": row["username"],
        "password": row["password"],
        "sid": row["sid"],
        "active": bool(row["active"]),
        "traffic_limit": row["traffic_limit"],
        "expires_at": row["expires_at"],
    }


@router.get("/users")
def users_list():
    return [{**_row_to_dict(r), "traffic_total": r["total"]} for r in list_users_with_traffic()]


@router.post("/users", status_code=201)
def users_create(body: CreateBody):
    username = body.username.strip()
    if not username:
        return JSONResponse({"error": "username required"}, status_code=400)
    result = create_user(username, traffic_limit=body.traffic_limit, expires_at=body.expires_at)
    if result is None:
        return JSONResponse({"error": "already exists"}, status_code=409)
    return result


@router.get("/users/{username}")
def users_get(username: str):
    row = get_user(username)
    if not row:
        return JSONResponse({"error": "not found"}, status_code=404)
    return _row_to_dict(row)


@router.patch("/users/{username}")
def users_edit(username: str, body: EditBody):
    if not user_exists(username):
        return JSONResponse({"error": "not found"}, status_code=404)
    edit_user(
        username,
        password=body.password,
        sid=body.sid,
        active=body.active,
        traffic_limit=body.traffic_limit,
        expires_at=body.expires_at,
    )
    return _row_to_dict(get_user(username))


@router.delete("/users/{username}")
def users_delete(username: str):
    if not delete_user(username):
        return JSONResponse({"error": "not found"}, status_code=404)
    return {"ok": True}
