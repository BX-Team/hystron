from dataclasses import dataclass, field


@dataclass
class UserEntry:
    username: str
    password: str
    active: bool
    expires_at: int
    traffic_limit: int


@dataclass
class NodeInfo:
    address: str
    protocols: list[str]
    ports: dict[str, int]


@dataclass
class SyncResponse:
    config_version: str
    poll_interval: int
    node: NodeInfo
    users: list[UserEntry]


@dataclass
class TrafficStat:
    username: str
    tx: int
    rx: int
