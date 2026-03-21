import secrets
import uuid

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.engine import CursorResult

from .db import SessionLocal
from .models import Config, Device, Host, HostTag, Traffic, User, UserTag

_CONFIG_DEFAULTS = {
    "profile_name_tpl": "Hystron for {uname}",
    "poll_interval": "600",
    "base_url": "",
    "support_url": "https://discord.gg/qNyybSSPm5",
    "announce": "",
    "announce-url": "",
    "subscription_path": "/sub",
    # Template overrides: directory and per-format paths.
    # Per-format paths take precedence over templates_dir.
    # If empty, falls back to templates_dir/<filename>, then bundled template.
    "templates_dir": "/var/lib/hystron/templates",
    "template_singbox": "",
    "template_clash": "",
    "template_xray": "",
    "template_index": "",
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
                SELECT u.username, u.password, u.vless_uuid, u.trojan_password, u.hysteria2_password,
                       u.sid, u.active, u.traffic_limit, u.expires_at, u.device_limit,
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
    vless_uuid = str(uuid.uuid4())
    trojan_password = str(uuid.uuid4())
    hysteria2_password = str(uuid.uuid4())
    sid = secrets.token_urlsafe(12)
    with SessionLocal() as session:
        session.add(
            User(
                username=username,
                password=password,
                vless_uuid=vless_uuid,
                trojan_password=trojan_password,
                hysteria2_password=hysteria2_password,
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
        "vless_uuid": vless_uuid,
        "trojan_password": trojan_password,
        "hysteria2_password": hysteria2_password,
        "sid": sid,
        "traffic_limit": traffic_limit,
        "expires_at": expires_at,
        "device_limit": device_limit,
    }


def edit_user(
    username: str,
    *,
    password: str | None = None,
    vless_uuid: str | None = None,
    trojan_password: str | None = None,
    hysteria2_password: str | None = None,
    sid: str | None = None,
    active: bool | None = None,
    traffic_limit: int | None = None,
    expires_at: int | None = None,
    device_limit: int | None = None,
) -> bool:
    with SessionLocal() as session:
        user = session.get(User, username)
        if user is None:
            return False
        if password is not None:
            user.password = password
        if vless_uuid is not None:
            user.vless_uuid = vless_uuid
        if trojan_password is not None:
            user.trojan_password = trojan_password
        if hysteria2_password is not None:
            user.hysteria2_password = hysteria2_password
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
        SUM(CASE WHEN ts >= strftime('%Y-%m-%dT%H:%M:%SZ', 'now', 'start of day')            THEN tx + rx ELSE 0 END) AS day,
        SUM(CASE WHEN ts >= strftime('%Y-%m-%dT%H:%M:%SZ', 'now', '-6 days', 'start of day') THEN tx + rx ELSE 0 END) AS week,
        SUM(CASE WHEN ts >= strftime('%Y-%m-%dT%H:%M:%SZ', 'now', 'start of month')          THEN tx + rx ELSE 0 END) AS month,
        SUM(tx + rx) AS total
    FROM traffic
"""


def get_traffic(username: str | None = None) -> list[dict]:
    where = "WHERE username = :username" if username else ""
    params = {"username": username} if username else {}
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
            "day": int(r["day"] or 0),
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
    """Reactivate users that were deactivated due to daily traffic limits. Returns count of reactivated users."""
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


def get_host(address: str) -> dict | None:
    with SessionLocal() as session:
        host = session.get(Host, address)
        if host is None:
            return None
        return {c.key: getattr(host, c.key) for c in Host.__table__.columns}


def host_exists(address: str) -> bool:
    return get_host(address) is not None


def create_host(
    address: str,
    name: str,
    grpc_address: str,
    *,
    protocol: str = "vless_reality",
    inbound_tag: str = "",
    sni: str = "",
    reality_public_key: str = "",
    reality_short_id: str = "",
    port: int = 443,
    active: bool = True,
) -> dict | None:
    if host_exists(address):
        return None
    with SessionLocal() as session:
        session.add(
            Host(
                address=address,
                name=name,
                port=port,
                grpc_address=grpc_address,
                protocol=protocol,
                inbound_tag=inbound_tag,
                sni=sni,
                reality_public_key=reality_public_key,
                reality_short_id=reality_short_id,
                active=int(active),
            )
        )
        session.commit()
    return {
        "address": address,
        "name": name,
        "port": port,
        "grpc_address": grpc_address,
        "protocol": protocol,
        "inbound_tag": inbound_tag,
        "sni": sni,
        "reality_public_key": reality_public_key,
        "reality_short_id": reality_short_id,
        "active": active,
    }


def edit_host(
    address: str,
    *,
    name: str | None = None,
    port: int | None = None,
    grpc_address: str | None = None,
    protocol: str | None = None,
    inbound_tag: str | None = None,
    sni: str | None = None,
    reality_public_key: str | None = None,
    reality_short_id: str | None = None,
    active: bool | None = None,
) -> bool:
    with SessionLocal() as session:
        host = session.get(Host, address)
        if host is None:
            return False
        if name is not None:
            host.name = name
        if port is not None:
            host.port = port
        if grpc_address is not None:
            host.grpc_address = grpc_address
        if protocol is not None:
            host.protocol = protocol
        if inbound_tag is not None:
            host.inbound_tag = inbound_tag
        if sni is not None:
            host.sni = sni
        if reality_public_key is not None:
            host.reality_public_key = reality_public_key
        if reality_short_id is not None:
            host.reality_short_id = reality_short_id
        if active is not None:
            host.active = int(active)
        session.commit()
    return True


def delete_host(address: str) -> bool:
    with SessionLocal() as session:
        host = session.get(Host, address)
        if host is None:
            return False
        session.execute(delete(HostTag).where(HostTag.host_address == address))
        session.delete(host)
        session.commit()
    return True


# ── tags ──────────────────────────────────────────────────────────────────────


def get_host_tags(address: str) -> list[str]:
    with SessionLocal() as session:
        tags = session.scalars(select(HostTag.tag).where(HostTag.host_address == address).order_by(HostTag.tag)).all()
        return list(tags)


def set_host_tags(address: str, tags: list[str]) -> None:
    with SessionLocal() as session:
        session.execute(delete(HostTag).where(HostTag.host_address == address))
        for tag in set(tags):
            session.add(HostTag(host_address=address, tag=tag))
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
                    NOT EXISTS (SELECT 1 FROM host_tags ht WHERE ht.host_address = h.address)
                    OR EXISTS (
                        SELECT 1 FROM host_tags ht
                        JOIN user_tags ut ON ut.tag = ht.tag
                        WHERE ht.host_address = h.address AND ut.username = :username
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
