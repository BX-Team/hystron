from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.database import delete_config, get_config, list_config, set_config

router = APIRouter(prefix="/api", tags=["Config"])


class SetBody(BaseModel):
    value: str


@router.get("/config")
def config_list():
    return list_config()


@router.get("/config/{key}")
def config_get(key: str):
    value = get_config(key)
    if value == "" and key not in list_config():
        return JSONResponse({"error": "not found"}, status_code=404)
    return {"key": key, "value": value}


@router.put("/config/{key}")
def config_set(key: str, body: SetBody):
    set_config(key, body.value)
    return {"key": key, "value": body.value}


@router.delete("/config/{key}")
def config_delete(key: str):
    if not delete_config(key):
        return JSONResponse({"error": "not found"}, status_code=404)
    return {"ok": True}
