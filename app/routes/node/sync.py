import json

from fastapi import APIRouter, Depends, Header, Response

from app.database import (
    compute_config_version,
    get_config,
    list_users,
    update_node_config_version,
)
from .auth import get_node

router = APIRouter(prefix="/node", tags=["Node"])


@router.get("/sync")
def node_sync(
    node: dict = Depends(get_node),
    x_config_version: str | None = Header(default=None),
):
    users = [dict(u) for u in list_users()]
    version = compute_config_version(node, users)

    if x_config_version and x_config_version == version:
        return Response(status_code=304)

    update_node_config_version(node["address"], version)

    poll_interval = int(get_config("node_poll_interval", "30"))
    protocols = json.loads(node.get("protocols") or '["hysteria2"]')
    node_ports = json.loads(node.get("node_ports") or "{}")

    return {
        "config_version": version,
        "poll_interval": poll_interval,
        "node": {
            "address": node["address"],
            "protocols": protocols,
            "ports": node_ports,
        },
        "users": [
            {
                "username": u["username"],
                "password": u["password"],
                "active": bool(u["active"]),
                "expires_at": u["expires_at"],
                "traffic_limit": u["traffic_limit"],
            }
            for u in users
        ],
    }
