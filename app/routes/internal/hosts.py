import asyncio
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
    grpc_address: str
    protocol: str = "vless_reality"  # "vless_reality" | "trojan" | "hysteria2"
    inbound_tag: str = ""
    sni: str = ""
    reality_public_key: str = ""
    reality_short_id: str = ""
    port: int = 443
    active: bool = True
    tags: list[str] = []


class EditBody(BaseModel):
    name: Optional[str] = None
    port: Optional[int] = None
    grpc_address: Optional[str] = None
    protocol: Optional[str] = None
    inbound_tag: Optional[str] = None
    sni: Optional[str] = None
    reality_public_key: Optional[str] = None
    reality_short_id: Optional[str] = None
    active: Optional[bool] = None
    tags: Optional[list[str]] = None


def _row_to_dict(row) -> dict:
    address = row["address"]
    return {
        "address": address,
        "name": row["name"],
        "port": row["port"],
        "grpc_address": row["grpc_address"],
        "protocol": row["protocol"],
        "inbound_tag": row["inbound_tag"],
        "sni": row["sni"],
        "reality_public_key": row["reality_public_key"],
        "reality_short_id": row["reality_short_id"],
        "active": bool(row["active"]),
        "tags": get_host_tags(address),
    }


@router.get("/hosts/detect")
def hosts_detect(grpc_address: str, info_port: int = 10086):
    """
    Auto-detect a node's protocol settings from its info endpoint.
    Returns a partial host config (protocol, inbound_tag, sni, reality keys).
    """
    from app.xray.node_info import fetch_node_info

    info = fetch_node_info(grpc_address, info_port)
    if info is None:
        return JSONResponse(
            {"error": f"Could not reach node info endpoint at {grpc_address.split(':')[0]}:{info_port}"},
            status_code=502,
        )
    return info


@router.get("/hosts")
def hosts_list():
    return [_row_to_dict(h) for h in list_hosts()]


@router.post("/hosts", status_code=201)
async def hosts_create(body: CreateBody):
    address = body.address.strip()
    if not address:
        return JSONResponse({"error": "address required"}, status_code=400)
    result = create_host(
        address,
        body.name,
        body.grpc_address,
        protocol=body.protocol,
        inbound_tag=body.inbound_tag,
        sni=body.sni,
        reality_public_key=body.reality_public_key,
        reality_short_id=body.reality_short_id,
        port=body.port,
        active=body.active,
    )
    if result is None:
        return JSONResponse({"error": "already exists"}, status_code=409)
    if body.tags:
        set_host_tags(address, body.tags)
    result["tags"] = get_host_tags(address)

    # Push all active users to the new host in the background
    from app.xray.sync import sync_new_host

    asyncio.create_task(sync_new_host(result))

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
        grpc_address=body.grpc_address,
        protocol=body.protocol,
        inbound_tag=body.inbound_tag,
        sni=body.sni,
        reality_public_key=body.reality_public_key,
        reality_short_id=body.reality_short_id,
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
