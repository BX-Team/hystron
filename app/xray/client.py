"""
Async gRPC client for xray-core HandlerService and StatsService.

Channels are created lazily and cached per grpc_address. The type URLs used in
TypedMessage.type must match the fully-qualified protobuf names that xray-core
registers at startup.
"""
from __future__ import annotations

import grpc
import grpc.aio

from app.xray.proto import xray_api_pb2, xray_api_pb2_grpc

# Type URLs as expected by xray-core's TypedMessage dispatcher
_TYPE_URL = {
    "vless_reality": "type.googleapis.com/xray.proxy.vless.Account",
    "trojan": "type.googleapis.com/xray.proxy.trojan.Account",
    "hysteria2": "type.googleapis.com/xray.proxy.hysteria2.Account",
    "add_user_op": "type.googleapis.com/xray.app.proxyman.command.AddUserOperation",
    "remove_user_op": "type.googleapis.com/xray.app.proxyman.command.RemoveUserOperation",
}

_channels: dict[str, grpc.aio.Channel] = {}


def _get_channel(grpc_address: str) -> grpc.aio.Channel:
    if grpc_address not in _channels:
        _channels[grpc_address] = grpc.aio.insecure_channel(grpc_address)
    return _channels[grpc_address]


async def close_all_channels() -> None:
    for ch in list(_channels.values()):
        await ch.close()
    _channels.clear()


def _build_account(protocol: str, password: str) -> bytes:
    """Serialize a protocol-specific account proto as bytes."""
    if protocol == "vless_reality":
        acc = xray_api_pb2.VlessAccount(id=password, flow="xtls-rprx-vision")
    elif protocol == "trojan":
        acc = xray_api_pb2.TrojanAccount(password=password)
    elif protocol == "hysteria2":
        acc = xray_api_pb2.Hy2Account(password=password)
    else:
        raise ValueError(f"Unknown protocol: {protocol!r}")
    return acc.SerializeToString()


async def add_user(
    grpc_address: str,
    inbound_tag: str,
    protocol: str,
    username: str,
    password: str,
    *,
    timeout: float = 10,
) -> None:
    """Add a user to an xray inbound via gRPC HandlerService."""
    email = f"{username}@{inbound_tag}"
    user = xray_api_pb2.User(
        email=email,
        account=xray_api_pb2.TypedMessage(
            type=_TYPE_URL[protocol],
            value=_build_account(protocol, password),
        ),
    )
    operation = xray_api_pb2.AddUserOperation(user=user)
    request = xray_api_pb2.AlterInboundRequest(
        tag=inbound_tag,
        operation=xray_api_pb2.TypedMessage(
            type=_TYPE_URL["add_user_op"],
            value=operation.SerializeToString(),
        ),
    )
    channel = _get_channel(grpc_address)
    stub = xray_api_pb2_grpc.HandlerServiceStub(channel)
    try:
        await stub.AlterInbound(request, timeout=timeout)
    except grpc.aio.AioRpcError as e:
        details = (e.details() or "").lower()
        if "already exists" in details or "duplicate" in details:
            return  # idempotent — user is already there
        raise


async def remove_user(
    grpc_address: str,
    inbound_tag: str,
    username: str,
    *,
    timeout: float = 10,
) -> None:
    """Remove a user from an xray inbound via gRPC HandlerService."""
    email = f"{username}@{inbound_tag}"
    operation = xray_api_pb2.RemoveUserOperation(email=email)
    request = xray_api_pb2.AlterInboundRequest(
        tag=inbound_tag,
        operation=xray_api_pb2.TypedMessage(
            type=_TYPE_URL["remove_user_op"],
            value=operation.SerializeToString(),
        ),
    )
    channel = _get_channel(grpc_address)
    stub = xray_api_pb2_grpc.HandlerServiceStub(channel)
    try:
        await stub.AlterInbound(request, timeout=timeout)
    except grpc.aio.AioRpcError as e:
        details = (e.details() or "").lower()
        if "not found" in details or "user" in details and "exist" in details:
            return  # idempotent — user is already gone
        raise


async def query_traffic(
    grpc_address: str,
    *,
    reset: bool = True,
    timeout: float = 10,
) -> dict[str, dict[str, int]]:
    """
    Query per-user traffic counters via gRPC StatsService.

    Returns {username: {"tx": N, "rx": N}}.
    Stat name format: user>>>email@tag>>>traffic>>>uplink|downlink
    """
    request = xray_api_pb2.QueryStatsRequest(pattern="user>>>", reset=reset)
    channel = _get_channel(grpc_address)
    stub = xray_api_pb2_grpc.StatsServiceStub(channel)
    resp = await stub.QueryStats(request, timeout=timeout)

    result: dict[str, dict[str, int]] = {}
    for stat in resp.stat:
        # name example: "user>>>alice@vless_in>>>traffic>>>uplink"
        parts = stat.name.split(">>>")
        if len(parts) != 4 or parts[0] != "user" or parts[2] != "traffic":
            continue
        username = parts[1].split("@")[0]
        direction = parts[3]  # "uplink" or "downlink"
        entry = result.setdefault(username, {"tx": 0, "rx": 0})
        if direction == "uplink":
            entry["tx"] += int(stat.value)
        elif direction == "downlink":
            entry["rx"] += int(stat.value)
    return result
