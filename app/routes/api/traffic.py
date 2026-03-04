from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ...database import get_traffic, user_exists

router = APIRouter(prefix="/api", tags=["Traffic"])


@router.get("/traffic")
def traffic_all():
    return get_traffic()


@router.get("/traffic/{username}")
def traffic_user(username: str):
    if not user_exists(username):
        return JSONResponse({"error": "not found"}, status_code=404)
    rows = get_traffic(username)
    return rows[0] if rows else {"username": username, "hour": 0, "day": 0, "week": 0, "month": 0, "total": 0}
