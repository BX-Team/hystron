import secrets
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.engine import CursorResult

from . import SessionLocal
from .models import Config, Device, Host, HostTag, Traffic, User, UserTag


def _billing_period_start() -> str:
    """Return ISO timestamp of the current billing period start based on traffic_reset config.

    Config format: "DD HH:MM" — day of month and UTC time.
    If current date is before reset day/time, period started last month.
    """
    raw = get_config("traffic_reset", "01 00:00")
    try:
        parts = raw.strip().split()
        reset_day = int(parts[0])
        hm = parts[1].split(":")
        reset_hour, reset_minute = int(hm[0]), int(hm[1])
    except (IndexError, ValueError):
        reset_day, reset_hour, reset_minute = 1, 0, 0

    now = datetime.now(timezone.utc)
    # Clamp reset_day to valid range
    reset_day = max(1, min(28, reset_day))

    try:
        period_start = now.replace(day=reset_day, hour=reset_hour, minute=reset_minute, second=0, microsecond=0)
    except ValueError:
        period_start = now.replace(day=1, hour=reset_hour, minute=reset_minute, second=0, microsecond=0)

    if now < period_start:
        # Go to previous month
        if now.month == 1:
            period_start = period_start.replace(year=now.year - 1, month=12)
        else:
            period_start = period_start.replace(month=now.month - 1)

    return period_start.strftime("%Y-%m-%dT%H:%M:%SZ")

_CONFIG_DEFAULTS = {
    "profile_name_tpl": "Hystron for {uname}",
    "poll_interval": "600",
    "base_url": "",
    "support_url": "https://discord.gg/qNyybSSPm5",
    "announce": "",
    "announce-url": "",
    "subscription_path": "/sub",
    "whitelist_enable": "false",
    "whitelist": "",
    # Traffic reset: "DD HH:MM" — day of month and time (UTC) to reset traffic.
    # e.g. "01 03:00" means reset on the 1st of each month at 03:00 UTC.
    "traffic_reset": "01 00:00",
    # Template overrides: directory and per-format paths.
    # Per-format paths take precedence over templates_dir.
    # If empty, falls back to templates_dir/<filename>, then bundled template.
    "templates_dir": "/var/lib/hystron/templates",
    "template_singbox": "",
    "template_clash": "",
    "template_index": "",
    "template_xray": "",
}


def init_db():
    """Seed default config values. Schema is managed by Alembic."""
    with SessionLocal() as session:
        for k, v in _CONFIG_DEFAULTS.items():
            if session.get(Config, k) is None:
                session.add(Config(key=k, value=v))
        session.commit()


# ── users ─────────────────────────────────────────────────────────────────────


def user_exists(username: str) -> bool:
    with SessionLocal() as session:
        return session.get(User, username) is not None


def get_user(username: str) -> dict | None:
    with SessionLocal() as session:
        user = session.get(User, username)
        if user is None:
            return None
        return {c.key: getattr(user, c.key) for c in User.__table__.columns}


def get_user_by_sid(sid: str) -> dict | None:
    with SessionLocal() as session:
        user = session.scalars(select(User).where(User.sid == sid)).one_or_none()
        if user is None:
            return None
        return {c.key: getattr(user, c.key) for c in User.__table__.columns}


def list_users() -> list:
    with SessionLocal() as session:
        users = session.scalars(select(User).order_by(User.username)).all()
        return [{c.key: getattr(u, c.key) for c in User.__table__.columns} for u in users]


def list_users_with_traffic() -> list[dict]:
    with SessionLocal() as session:
        rows = (
            session.execute(
                text("""
                SELECT u.username, u.password, u.sid, u.active,
                       u.traffic_limit, u.expires_at, u.device_limit, u.sub_url,
                       COALESCE(SUM(t.tx + t.rx), 0) AS total,
                       (SELECT COUNT(*) FROM devices d WHERE d.username = u.username) AS device_count
                FROM users u
                LEFT JOIN traffic t ON t.username = u.username
                GROUP BY u.username
                ORDER BY u.username
            """)
            )
            .mappings()
            .all()
        )
        return [dict(r) for r in rows]


def create_user(
    username: str,
    *,
    traffic_limit: int = 0,
    expires_at: int = 0,
    device_limit: int = 0,
) -> dict | None:
    if user_exists(username):
        return None
    password = str(uuid.uuid4())
    sid = secrets.token_urlsafe(12)
    with SessionLocal() as session:
        session.add(
            User(
                username=username,
                password=password,
                sid=sid,
                traffic_limit=traffic_limit,
                expires_at=expires_at,
                device_limit=device_limit,
            )
        )
        session.commit()
    return {
        "username": username,
        "password": password,
        "sid": sid,
        "traffic_limit": traffic_limit,
        "expires_at": expires_at,
        "device_limit": device_limit,
    }


def edit_user(
    username: str,
    *,
    password: str | None = None,
    sid: str | None = None,
    active: bool | None = None,
    traffic_limit: int | None = None,
    expires_at: int | None = None,
    device_limit: int | None = None,
    sub_url: str | None = None,
    _set_sub_url: bool = False,
) -> bool:
    with SessionLocal() as session:
        user = session.get(User, username)
        if user is None:
            return False
        if password is not None:
            user.password = password
        if sid is not None:
            user.sid = sid
        if active is not None:
            user.active = int(active)
        if traffic_limit is not None:
            user.traffic_limit = traffic_limit
        if expires_at is not None:
            user.expires_at = expires_at
        if device_limit is not None:
            user.device_limit = device_limit
        if _set_sub_url:
            user.sub_url = sub_url or None
        session.commit()
    return True


def delete_user(username: str) -> bool:
    with SessionLocal() as session:
        user = session.get(User, username)
        if user is None:
            return False
        session.execute(delete(Traffic).where(Traffic.username == username))
        session.execute(delete(Device).where(Device.username == username))
        session.execute(delete(UserTag).where(UserTag.username == username))
        session.delete(user)
        session.commit()
    return True


# ── auth ──────────────────────────────────────────────────────────────────────


def check_auth(username: str, password: str) -> tuple[bool, str]:
    """
    Validates user credentials and checks limits.
    Returns (ok, reason) — reason is "" if ok, otherwise "invalid"/"inactive"/"expired"/"overlimit".
    """
    period_start = _billing_period_start()
    with SessionLocal() as session:
        row = (
            session.execute(
                text("""
                SELECT u.active, u.traffic_limit, u.expires_at,
                       COALESCE(SUM(CASE WHEN t.ts >= :period_start
                                         THEN t.tx + t.rx ELSE 0 END), 0) AS total_traffic
                FROM users u
                LEFT JOIN traffic t ON t.username = u.username
                WHERE u.username = :username AND u.password = :password
                GROUP BY u.username
            """),
                {"username": username, "password": password, "period_start": period_start},
            )
            .mappings()
            .one_or_none()
        )

    if not row:
        return False, "invalid"
    if not row["active"]:
        return False, "inactive"
    if row["expires_at"] and row["expires_at"] < int(time.time()):
        return False, "expired"
    if row["traffic_limit"] > 0 and row["total_traffic"] >= row["traffic_limit"]:
        return False, "overlimit"

    return True, ""


# ── devices ───────────────────────────────────────────────────────────────────


def list_devices(username: str | None = None) -> list[dict]:
    with SessionLocal() as session:
        if username:
            q = select(Device).where(Device.username == username).order_by(Device.id)
        else:
            q = select(Device).order_by(Device.username, Device.id)
        devices = session.scalars(q).all()
        return [{c.key: getattr(d, c.key) for c in Device.__table__.columns} for d in devices]


def register_device(
    username: str,
    hwid: str,
    device_os: str,
    ver_os: str,
    device_model: str,
    app_version: str,
) -> bool:
    """
    Register or update a device for a user.
    Returns False if the user's device_limit is reached and this is a new device.
    """
    with SessionLocal() as session:
        existing = session.scalars(select(Device).where(Device.username == username, Device.hwid == hwid)).one_or_none()

        if existing:
            existing.device_os = device_os
            existing.ver_os = ver_os
            existing.device_model = device_model
            existing.app_version = app_version
            session.commit()
            return True

        # New device — check limit
        user = session.get(User, username)
        if user and user.device_limit > 0:
            count = session.scalar(select(func.count()).select_from(Device).where(Device.username == username))
            if (count or 0) >= user.device_limit:
                return False

        session.add(
            Device(
                username=username,
                hwid=hwid,
                device_os=device_os,
                ver_os=ver_os,
                device_model=device_model,
                app_version=app_version,
            )
        )
        session.commit()
    return True


def delete_device(device_id: int) -> bool:
    with SessionLocal() as session:
        device = session.get(Device, device_id)
        if device is None:
            return False
        session.delete(device)
        session.commit()
    return True


def is_device_allowed(username: str, hwid: str) -> bool:
    """
    Returns True if the user has no device_limit set, or the HWID is already registered.
    Returns False if device_limit is set and the HWID is not yet registered.
    """
    with SessionLocal() as session:
        user = session.get(User, username)
        if not user or not user.device_limit:
            return True
        exists = session.scalars(select(Device).where(Device.username == username, Device.hwid == hwid)).one_or_none()
        return exists is not None


# ── traffic ───────────────────────────────────────────────────────────────────

_TRAFFIC_SELECT = """
    SELECT
        username,
        SUM(CASE WHEN ts >= strftime('%Y-%m-%dT%H:%M:%SZ', 'now', '-60 minutes')             THEN tx + rx ELSE 0 END) AS hour,
        SUM(CASE WHEN ts >= :period_start                                                     THEN tx + rx ELSE 0 END) AS period,
        SUM(CASE WHEN ts >= strftime('%Y-%m-%dT%H:%M:%SZ', 'now', '-6 days', 'start of day') THEN tx + rx ELSE 0 END) AS week,
        SUM(CASE WHEN ts >= strftime('%Y-%m-%dT%H:%M:%SZ', 'now', 'start of month')          THEN tx + rx ELSE 0 END) AS month,
        SUM(tx + rx) AS total
    FROM traffic
"""


def get_traffic(username: str | None = None) -> list[dict]:
    where = "WHERE username = :username" if username else ""
    params: dict = {"period_start": _billing_period_start()}
    if username:
        params["username"] = username
    with SessionLocal() as session:
        rows = (
            session.execute(
                text(f"{_TRAFFIC_SELECT} {where} GROUP BY username ORDER BY total DESC"),
                params,
            )
            .mappings()
            .all()
        )
    return [
        {
            "username": r["username"],
            "hour": int(r["hour"] or 0),
            "period": int(r["period"] or 0),
            "week": int(r["week"] or 0),
            "month": int(r["month"] or 0),
            "total": int(r["total"] or 0),
        }
        for r in rows
    ]


def record_traffic_batch(entries: list[tuple[str, str, str, int, int]]) -> None:
    """Insert multiple traffic records in one transaction. entries: [(ts, server, username, tx, rx)]"""
    with SessionLocal() as session:
        session.add_all(
            [Traffic(ts=ts, server=server, username=username, tx=tx, rx=rx) for ts, server, username, tx, rx in entries]
        )
        session.commit()


def reset_traffic_limited_users() -> int:
    """Reactivate users that were deactivated due to traffic limits. Returns count of reactivated users."""
    with SessionLocal() as session:
        result: CursorResult = session.execute(  # type: ignore[assignment]
            update(User).where(User.active == 0, User.traffic_limit > 0).values(active=1)
        )
        session.commit()
        return result.rowcount


def delete_traffic(username: str | None = None) -> int:
    with SessionLocal() as session:
        result: CursorResult
        if username:
            result = session.execute(delete(Traffic).where(Traffic.username == username))  # type: ignore[assignment]
        else:
            result = session.execute(delete(Traffic))  # type: ignore[assignment]
        count = result.rowcount
        session.commit()
    return count


# ── hosts ─────────────────────────────────────────────────────────────────────


def list_hosts(active_only: bool = False) -> list[dict]:
    with SessionLocal() as session:
        q = select(Host).order_by(Host.address)
        if active_only:
            q = q.where(Host.active == 1)
        hosts = session.scalars(q).all()
        return [{c.key: getattr(h, c.key) for c in Host.__table__.columns} for h in hosts]


def get_host(host_id: int) -> dict | None:
    with SessionLocal() as session:
        host = session.get(Host, host_id)
        if host is None:
            return None
        return {c.key: getattr(host, c.key) for c in Host.__table__.columns}


def host_exists(host_id: int) -> bool:
    return get_host(host_id) is not None


def _address_port_exists(address: str, port: int) -> bool:
    with SessionLocal() as session:
        return session.scalars(select(Host).where(Host.address == address, Host.port == port)).one_or_none() is not None


def create_host(
    address: str,
    name: str,
    *,
    host_type: str = "hysteria2",
    port: int = 443,
    active: bool = True,
    api_address: str | None = None,
    api_secret: str | None = None,
    inbound_tag: str | None = None,
    inbound_port: int | None = None,
    grpc_address: str | None = None,
    api_key: str | None = None,
    sub_params: str | None = None,
    protocol: str | None = None,
    flow: str | None = None,
    up_mbps: int | None = None,
    down_mbps: int | None = None,
) -> dict | None:
    if _address_port_exists(address, port):
        return None
    with SessionLocal() as session:
        host = Host(
            address=address,
            name=name,
            port=port,
            host_type=host_type,
            api_address=api_address,
            api_secret=api_secret,
            active=int(active),
            inbound_tag=inbound_tag,
            inbound_port=inbound_port,
            grpc_address=grpc_address,
            api_key=api_key,
            sub_params=sub_params,
            protocol=protocol,
            flow=flow,
            up_mbps=up_mbps,
            down_mbps=down_mbps,
        )
        session.add(host)
        session.commit()
        session.refresh(host)
        return {c.key: getattr(host, c.key) for c in Host.__table__.columns}


def edit_host(
    host_id: int,
    *,
    name: str | None = None,
    port: int | None = None,
    active: bool | None = None,
    api_address: str | None = None,
    api_secret: str | None = None,
    inbound_tag: str | None = None,
    inbound_port: int | None = None,
    grpc_address: str | None = None,
    api_key: str | None = None,
    sub_params: str | None = None,
    protocol: str | None = None,
    flow: str | None = None,
    up_mbps: int | None = None,
    down_mbps: int | None = None,
) -> bool:
    with SessionLocal() as session:
        host = session.get(Host, host_id)
        if host is None:
            return False
        if name is not None:
            host.name = name
        if port is not None:
            host.port = port
        if active is not None:
            host.active = int(active)
        if api_address is not None:
            host.api_address = api_address
        if api_secret is not None:
            host.api_secret = api_secret
        if inbound_tag is not None:
            host.inbound_tag = inbound_tag
        if inbound_port is not None:
            host.inbound_port = inbound_port
        if grpc_address is not None:
            host.grpc_address = grpc_address
        if api_key is not None:
            host.api_key = api_key
        if sub_params is not None:
            host.sub_params = sub_params
        if protocol is not None:
            host.protocol = protocol
        if flow is not None:
            host.flow = flow
        if up_mbps is not None:
            host.up_mbps = up_mbps
        if down_mbps is not None:
            host.down_mbps = down_mbps
        session.commit()
    return True


def list_hystron_nodes(active_only: bool = False) -> list[dict]:
    """Return only hystron_node type hosts."""
    with SessionLocal() as session:
        q = select(Host).where(Host.host_type == "hystron_node").order_by(Host.address)
        if active_only:
            q = q.where(Host.active == 1)
        hosts = session.scalars(q).all()
        return [{c.key: getattr(h, c.key) for c in Host.__table__.columns} for h in hosts]


def delete_host(host_id: int) -> bool:
    with SessionLocal() as session:
        host = session.get(Host, host_id)
        if host is None:
            return False
        session.execute(delete(HostTag).where(HostTag.host_id == host_id))
        session.delete(host)
        session.commit()
    return True


# ── tags ──────────────────────────────────────────────────────────────────────


def get_host_tags(host_id: int) -> list[str]:
    with SessionLocal() as session:
        tags = session.scalars(select(HostTag.tag).where(HostTag.host_id == host_id).order_by(HostTag.tag)).all()
        return list(tags)


def set_host_tags(host_id: int, tags: list[str]) -> None:
    with SessionLocal() as session:
        session.execute(delete(HostTag).where(HostTag.host_id == host_id))
        for tag in set(tags):
            session.add(HostTag(host_id=host_id, tag=tag))
        session.commit()


def get_user_tags(username: str) -> list[str]:
    with SessionLocal() as session:
        tags = session.scalars(select(UserTag.tag).where(UserTag.username == username).order_by(UserTag.tag)).all()
        return list(tags)


def set_user_tags(username: str, tags: list[str]) -> None:
    with SessionLocal() as session:
        session.execute(delete(UserTag).where(UserTag.username == username))
        for tag in set(tags):
            session.add(UserTag(username=username, tag=tag))
        session.commit()


def list_all_tags() -> list[str]:
    with SessionLocal() as session:
        rows = (
            session.execute(
                text("""
                SELECT DISTINCT tag FROM host_tags
                UNION
                SELECT DISTINCT tag FROM user_tags
                ORDER BY tag
            """)
            )
            .scalars()
            .all()
        )
        return list(rows)


def list_hosts_for_user(username: str, active_only: bool = True) -> list[dict]:
    """
    Return hosts visible to the given user:
    - Hosts with no tags are visible to everyone.
    - Hosts with tags are visible only if the user shares at least one tag.
    """
    where = "AND h.active = 1" if active_only else ""
    with SessionLocal() as session:
        rows = (
            session.execute(
                text(f"""
                SELECT h.* FROM hosts h
                WHERE (
                    NOT EXISTS (SELECT 1 FROM host_tags ht WHERE ht.host_id = h.id)
                    OR EXISTS (
                        SELECT 1 FROM host_tags ht
                        JOIN user_tags ut ON ut.tag = ht.tag
                        WHERE ht.host_id = h.id AND ut.username = :username
                    )
                )
                {where}
                ORDER BY h.address
            """),
                {"username": username},
            )
            .mappings()
            .all()
        )
        return [dict(r) for r in rows]


# ── config ────────────────────────────────────────────────────────────────────


def get_config(key: str, default: str = "") -> str:
    with SessionLocal() as session:
        cfg = session.get(Config, key)
        return cfg.value if cfg else default


def set_config(key: str, value: str) -> None:
    with SessionLocal() as session:
        cfg = session.get(Config, key)
        if cfg:
            cfg.value = value
        else:
            session.add(Config(key=key, value=value))
        session.commit()


def list_config() -> dict[str, str]:
    with SessionLocal() as session:
        rows = session.scalars(select(Config).order_by(Config.key)).all()
        return {row.key: row.value for row in rows}


def delete_config(key: str) -> bool:
    with SessionLocal() as session:
        cfg = session.get(Config, key)
        if cfg is None:
            return False
        session.delete(cfg)
        session.commit()
    return True
