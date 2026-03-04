from typing import Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ...database import list_hosts, get_host, create_host, edit_host, delete_host, host_exists

router = APIRouter(prefix="/api", tags=["Hosts"])


class CreateBody(BaseModel):
    address: str
    name: str
    api_address: str
    api_secret: str
    port: int = 443
    active: bool = True


class EditBody(BaseModel):
    name: Optional[str] = None
    port: Optional[int] = None
    api_address: Optional[str] = None
    api_secret: Optional[str] = None
    active: Optional[bool] = None


def _row_to_dict(row) -> dict:
    return {
        "address":     row["address"],
        "name":        row["name"],
        "port":        row["port"],
        "api_address": row["api_address"],
        "api_secret":  row["api_secret"],
        "active":      bool(row["active"]),
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
    return _row_to_dict(get_host(address))


@router.delete("/hosts/{address:path}")
def hosts_delete(address: str):
    if not delete_host(address):
        return JSONResponse({"error": "not found"}, status_code=404)
    return {"ok": True}
