from typing import Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.database import (
    create_host,
    delete_host,
    edit_host,
    get_host,
    get_host_tags,
    host_exists,
    list_hosts,
    set_host_tags,
)

router = APIRouter(prefix="/api", tags=["Hosts"])


class CreateBody(BaseModel):
    address: str
    name: str
    api_address: str
    api_secret: str
    port: int = 443
    active: bool = True
    tags: list[str] = []


class EditBody(BaseModel):
    name: Optional[str] = None
    port: Optional[int] = None
    api_address: Optional[str] = None
    api_secret: Optional[str] = None
    active: Optional[bool] = None
    tags: Optional[list[str]] = None


def _row_to_dict(row) -> dict:
    address = row["address"]
    return {
        "address": address,
        "name": row["name"],
        "port": row["port"],
        "api_address": row["api_address"],
        "api_secret": row["api_secret"],
        "active": bool(row["active"]),
        "tags": get_host_tags(address),
    }


@router.get("/hosts")
def hosts_list():
    return [_row_to_dict(h) for h in list_hosts()]


@router.post("/hosts", status_code=201)
def hosts_create(body: CreateBody):
    address = body.address.strip()
    if not address:
        return JSONResponse({"error": "address required"}, status_code=400)
    result = create_host(
        address,
        body.name,
        body.api_address,
        body.api_secret,
        port=body.port,
        active=body.active,
    )
    if result is None:
        return JSONResponse({"error": "already exists"}, status_code=409)
    if body.tags:
        set_host_tags(address, body.tags)
    result["tags"] = get_host_tags(address)
    return result


@router.get("/hosts/{address:path}")
def hosts_get(address: str):
    row = get_host(address)
    if not row:
        return JSONResponse({"error": "not found"}, status_code=404)
    return _row_to_dict(row)


@router.patch("/hosts/{address:path}")
def hosts_edit(address: str, body: EditBody):
    if not host_exists(address):
        return JSONResponse({"error": "not found"}, status_code=404)
    edit_host(
        address,
        name=body.name,
        port=body.port,
        api_address=body.api_address,
        api_secret=body.api_secret,
        active=body.active,
    )
    if body.tags is not None:
        set_host_tags(address, body.tags)
    return _row_to_dict(get_host(address))


@router.delete("/hosts/{address:path}")
def hosts_delete(address: str):
    if not delete_host(address):
        return JSONResponse({"error": "not found"}, status_code=404)
    return {"ok": True}
