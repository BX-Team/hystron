from typing import Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.db.database import (
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

_HOST_FIELDS = (
    "address", "name", "port", "active", "host_type",
    "api_address", "api_secret",
    "inbound_tag", "inbound_port", "grpc_address", "api_key",
    "sub_params", "protocol", "flow",
)


class CreateBody(BaseModel):
    address: str
    name: str
    port: int = 443
    active: bool = True
    host_type: str = "hysteria2"
    tags: list[str] = []
    # hysteria2 fields
    api_address: Optional[str] = None
    api_secret: Optional[str] = None
    # hystron_node fields
    inbound_tag: Optional[str] = None
    inbound_port: Optional[int] = None
    grpc_address: Optional[str] = None
    api_key: Optional[str] = None
    sub_params: Optional[str] = None
    protocol: Optional[str] = None
    flow: Optional[str] = None


class EditBody(BaseModel):
    name: Optional[str] = None
    port: Optional[int] = None
    active: Optional[bool] = None
    tags: Optional[list[str]] = None
    # hysteria2 fields
    api_address: Optional[str] = None
    api_secret: Optional[str] = None
    # hystron_node fields
    inbound_tag: Optional[str] = None
    inbound_port: Optional[int] = None
    grpc_address: Optional[str] = None
    api_key: Optional[str] = None
    sub_params: Optional[str] = None
    protocol: Optional[str] = None
    flow: Optional[str] = None


def _row_to_dict(row) -> dict:
    return {
        "id": row["id"],
        "address": row["address"],
        "name": row["name"],
        "port": row["port"],
        "active": bool(row["active"]),
        "host_type": row.get("host_type", "hysteria2"),
        "api_address": row.get("api_address"),
        "api_secret": row.get("api_secret"),
        "inbound_tag": row.get("inbound_tag"),
        "inbound_port": row.get("inbound_port"),
        "grpc_address": row.get("grpc_address"),
        "api_key": row.get("api_key"),
        "sub_params": row.get("sub_params"),
        "protocol": row.get("protocol"),
        "flow": row.get("flow"),
        "tags": get_host_tags(row["id"]),
    }


@router.get("/hosts")
def hosts_list():
    return [_row_to_dict(h) for h in list_hosts()]


@router.post("/hosts", status_code=201)
async def hosts_create(body: CreateBody):
    import asyncio

    from app.node.sync import sync_new_host

    address = body.address.strip()
    if not address:
        return JSONResponse({"error": "address required"}, status_code=400)
    result = create_host(
        address,
        body.name,
        host_type=body.host_type,
        port=body.port,
        active=body.active,
        api_address=body.api_address,
        api_secret=body.api_secret,
        inbound_tag=body.inbound_tag,
        inbound_port=body.inbound_port,
        grpc_address=body.grpc_address,
        api_key=body.api_key,
        sub_params=body.sub_params,
        protocol=body.protocol,
        flow=body.flow,
    )
    if result is None:
        return JSONResponse({"error": "already exists"}, status_code=409)
    host_id = result["id"]
    if body.tags:
        set_host_tags(host_id, body.tags)

    host_row = get_host(host_id)
    if body.host_type == "hystron_node" and host_row:
        asyncio.create_task(sync_new_host(host_row))

    return _row_to_dict(host_row)


@router.get("/hosts/{host_id}")
def hosts_get(host_id: int):
    row = get_host(host_id)
    if not row:
        return JSONResponse({"error": "not found"}, status_code=404)
    return _row_to_dict(row)


@router.patch("/hosts/{host_id}")
def hosts_edit(host_id: int, body: EditBody):
    if not host_exists(host_id):
        return JSONResponse({"error": "not found"}, status_code=404)
    edit_host(
        host_id,
        name=body.name,
        port=body.port,
        active=body.active,
        api_address=body.api_address,
        api_secret=body.api_secret,
        inbound_tag=body.inbound_tag,
        inbound_port=body.inbound_port,
        grpc_address=body.grpc_address,
        api_key=body.api_key,
        sub_params=body.sub_params,
        protocol=body.protocol,
        flow=body.flow,
    )
    if body.tags is not None:
        set_host_tags(host_id, body.tags)
    return _row_to_dict(get_host(host_id))


@router.delete("/hosts/{host_id}")
def hosts_delete(host_id: int):
    if not delete_host(host_id):
        return JSONResponse({"error": "not found"}, status_code=404)
    return {"ok": True}
