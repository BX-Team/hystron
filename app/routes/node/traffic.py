import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.database import edit_user, get_db, get_traffic, get_user
from .auth import get_node

router = APIRouter(prefix="/node", tags=["Node"])


class TrafficStat(BaseModel):
    username: str
    tx: int
    rx: int


class InboundInfo(BaseModel):
    protocol: str
    port: int


class TrafficBody(BaseModel):
    stats: list[TrafficStat]
    inbounds: Optional[list[InboundInfo]] = None


@router.post("/traffic")
def node_traffic(body: TrafficBody, node: dict = Depends(get_node)):
    address = node["address"]
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    conn = get_db()
    cur = conn.cursor()

    # Daily reset: reactivate users whose limit was hit yesterday
    now = datetime.now(timezone.utc)
    if now.hour == 0 and now.minute < 1:
        cur.execute("UPDATE users SET active = 1 WHERE active = 0 AND traffic_limit > 0")

    # Update node inbound info (protocols/ports) if provided
    if body.inbounds:
        protocols = [i.protocol for i in body.inbounds]
        node_ports = {i.protocol: i.port for i in body.inbounds}
        cur.execute(
            "UPDATE hosts SET protocols = ?, node_ports = ? WHERE address = ?",
            (json.dumps(protocols), json.dumps(node_ports), address),
        )

    # Record traffic deltas
    for stat in body.stats:
        if stat.tx or stat.rx:
            cur.execute(
                "INSERT INTO traffic (ts, server, username, tx, rx) VALUES (?, ?, ?, ?, ?)",
                (ts, address, stat.username, stat.tx, stat.rx),
            )
    conn.commit()
    conn.close()

    # Enforce per-user daily traffic limits
    kicked: list[str] = []
    for stat in body.stats:
        user = get_user(stat.username)
        if user and user["traffic_limit"] > 0:
            totals = get_traffic(stat.username)
            if totals and totals[0]["day"] >= user["traffic_limit"]:
                edit_user(stat.username, active=False)
                kicked.append(stat.username)
                print(f"kicked {stat.username} on {address}: daily traffic limit exceeded")

    return {"ok": True, "kicked": kicked}
