import json
import time
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.database import (
    create_host,
    delete_host,
    edit_host,
    get_host,
    host_exists,
    list_hosts,
    regenerate_node_token,
)

router = APIRouter(prefix="/api", tags=["Hosts"])


class CreateBody(BaseModel):
    address: str
    name: str
    port: int = 443
    active: bool = True
    protocols: list[str] = ["hysteria2"]
    node_ports: dict = {}


class EditBody(BaseModel):
    name: Optional[str] = None
    port: Optional[int] = None
    active: Optional[bool] = None
    protocols: Optional[list[str]] = None
    node_ports: Optional[dict] = None


def _row_to_dict(row: dict) -> dict:
    protocols = row.get("protocols", '["hysteria2"]')
    node_ports = row.get("node_ports", "{}")
    if isinstance(protocols, str):
        protocols = json.loads(protocols)
    if isinstance(node_ports, str):
        node_ports = json.loads(node_ports)
    last_seen = row.get("last_seen", 0) or 0
    online = last_seen > 0 and (int(time.time()) - last_seen) < 60
    return {
        "address": row["address"],
        "name": row["name"],
        "port": row["port"],
        "active": bool(row["active"]),
        "protocols": protocols,
        "node_ports": node_ports,
        "last_seen": last_seen,
        "online": online,
    }


@router.get("/hosts")
def hosts_list():
    return [_row_to_dict(h) for h in list_hosts()]


@router.post("/hosts", status_code=201)
def hosts_create(body: CreateBody):
    address = body.address.strip()
    if not address:
        return JSONResponse({"error": "address required"}, status_code=400)
    node_ports = body.node_ports or {"hysteria2": body.port}
    result = create_host(
        address,
        body.name,
        port=body.port,
        active=body.active,
        protocols=body.protocols,
        node_ports=node_ports,
    )
    if result is None:
        return JSONResponse({"error": "already exists"}, status_code=409)
    # Return with token so admin can copy it
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
        active=body.active,
        protocols=body.protocols,
        node_ports=body.node_ports,
    )
    return _row_to_dict(get_host(address))


@router.post("/hosts/{address:path}/token")
def hosts_regen_token(address: str):
    token = regenerate_node_token(address)
    if token is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return {"address": address, "node_token": token}


@router.delete("/hosts/{address:path}")
def hosts_delete(address: str):
    if not delete_host(address):
        return JSONResponse({"error": "not found"}, status_code=404)
    return {"ok": True}
