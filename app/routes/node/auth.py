from fastapi import Header, HTTPException

from app.database import get_node_by_token, update_node_seen


async def get_node(authorization: str = Header(...)) -> dict:
    token = authorization.removeprefix("Bearer ").strip()
    node = get_node_by_token(token)
    if not node:
        raise HTTPException(status_code=401, detail="Invalid node token")
    update_node_seen(node["address"])
    return node
