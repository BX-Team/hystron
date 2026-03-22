"""gRPC client helpers for hystron-node.

Usage:
    stats = get_traffic_stats(host)          # -> dict[str, (tx, rx)]
    reset_traffic_stats(host)
    add_user_to_node(host, username, uuid, password)
    remove_user_from_node(host, username)
"""

import grpc

from app.gen import hystron_node_pb2 as pb2
from app.gen import hystron_node_pb2_grpc as pb2_grpc

_TIMEOUT = 10  # seconds


def _channel(host: dict) -> grpc.Channel:
    return grpc.insecure_channel(host["grpc_address"])


def _metadata(host: dict) -> list[tuple[str, str]]:
    return [("x-api-key", host["api_key"] or "")]


def get_node_status(host: dict) -> dict:
    """Call GetStatus on the node. Returns dict with xray_running, xray_version, node_version, uptime_seconds."""
    with _channel(host) as ch:
        stub = pb2_grpc.HystronNodeStub(ch)
        resp = stub.GetStatus(pb2.StatusRequest(), metadata=_metadata(host), timeout=_TIMEOUT)
    return {
        "xray_running": resp.xray_running,
        "xray_version": resp.xray_version,
        "node_version": resp.node_version,
        "uptime_seconds": resp.uptime_seconds,
    }


def get_traffic_stats(host: dict) -> dict[str, tuple[int, int]]:
    """Call GetTrafficStats. Returns {username: (tx, rx)}."""
    with _channel(host) as ch:
        stub = pb2_grpc.HystronNodeStub(ch)
        resp = stub.GetTrafficStats(pb2.TrafficRequest(), metadata=_metadata(host), timeout=_TIMEOUT)
    return {s.username: (s.tx, s.rx) for s in resp.stats}


def reset_traffic_stats(host: dict) -> bool:
    """Call ResetTrafficStats (resets all users). Returns success flag."""
    with _channel(host) as ch:
        stub = pb2_grpc.HystronNodeStub(ch)
        resp = stub.ResetTrafficStats(pb2.ResetRequest(), metadata=_metadata(host), timeout=_TIMEOUT)
    return resp.success


def add_user_to_node(
    host: dict,
    username: str,
    uuid: str,
    password: str,
) -> tuple[bool, str]:
    """Add a user to the node. Protocol and inbound_tag come from host config.
    Returns (success, message)."""
    proto_enum = pb2.Protocol.VLESS if host.get("protocol", "").lower() == "vless" else pb2.Protocol.TROJAN
    inbound_tags = [host["inbound_tag"]] if host.get("inbound_tag") else []
    req = pb2.UserRequest(
        username=username,
        uuid=uuid,
        password=password,
        protocol=proto_enum,
        inbound_tags=inbound_tags,
        flow=host.get("flow") or "",
    )
    with _channel(host) as ch:
        stub = pb2_grpc.HystronNodeStub(ch)
        resp = stub.AddUser(req, metadata=_metadata(host), timeout=_TIMEOUT)
    return resp.success, resp.message


def remove_user_from_node(host: dict, username: str) -> tuple[bool, str]:
    """Remove a user from the node. Returns (success, message)."""
    inbound_tags = [host["inbound_tag"]] if host.get("inbound_tag") else []
    req = pb2.RemoveUserRequest(username=username, inbound_tags=inbound_tags)
    with _channel(host) as ch:
        stub = pb2_grpc.HystronNodeStub(ch)
        resp = stub.RemoveUser(req, metadata=_metadata(host), timeout=_TIMEOUT)
    return resp.success, resp.message
