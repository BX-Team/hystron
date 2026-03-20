import os
import secrets
import sqlite3
import time
import uuid

_DB_PATH = os.environ.get("HYST_DB_PATH", os.path.join(os.path.dirname(os.path.dirname(__file__)), "app.db"))


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username      TEXT    PRIMARY KEY,
            password      TEXT    NOT NULL,
            sid           TEXT    UNIQUE NOT NULL,
            active        INTEGER NOT NULL DEFAULT 1,
            traffic_limit INTEGER NOT NULL DEFAULT 0,
            expires_at    INTEGER NOT NULL DEFAULT 0,
            device_limit  INTEGER NOT NULL DEFAULT 0
        )
    """)
    # Migration: add device_limit to existing databases
    try:
        cur.execute("ALTER TABLE users ADD COLUMN device_limit INTEGER NOT NULL DEFAULT 0")
        conn.commit()
    except sqlite3.OperationalError:
        pass
    cur.execute("""
        CREATE TABLE IF NOT EXISTS devices (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            username     TEXT    NOT NULL,
            hwid         TEXT    NOT NULL,
            device_os    TEXT    NOT NULL,
            ver_os       TEXT    NOT NULL,
            device_model TEXT    NOT NULL,
            app_version  TEXT    NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS traffic (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            ts       TEXT    NOT NULL,
            server   TEXT    NOT NULL,
            username TEXT    NOT NULL,
            tx       INTEGER NOT NULL,
            rx       INTEGER NOT NULL
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS traffic_ts   ON traffic (ts)")
    cur.execute("CREATE INDEX IF NOT EXISTS traffic_user ON traffic (username)")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS hosts (
            address     TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            port        INTEGER NOT NULL DEFAULT 443,
            api_address TEXT NOT NULL,
            api_secret  TEXT NOT NULL,
            active      INTEGER NOT NULL DEFAULT 1
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS host_tags (
            host_address TEXT NOT NULL,
            tag          TEXT NOT NULL,
            PRIMARY KEY (host_address, tag)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_tags (
            username TEXT NOT NULL,
            tag      TEXT NOT NULL,
            PRIMARY KEY (username, tag)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS config (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    defaults = {
        "profile_name_tpl": "Hystron for {uname}",
        "poll_interval": "600",
        "base_url": "",
        "support_url": "https://discord.gg/qNyybSSPm5",
        "announce": "",
        "announce-url": "",
        "subscription_path": "/sub",
        "whitelist_enable": "false",
        "whitelist": "",
        "forbidden_domains": "",
        # Template overrides: directory and per-format paths.
        # Per-format paths take precedence over templates_dir.
        # If empty, falls back to templates_dir/<filename>, then bundled template.
        "templates_dir": "/var/lib/hystron/templates",
        "template_singbox": "",
        "template_clash": "",
        "template_xray": "",
        "template_index": "",
    }
    for k, v in defaults.items():
        cur.execute("INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)", (k, v))
    conn.commit()
    conn.close()


# ── users ─────────────────────────────────────────────────────────────────────


def user_exists(username: str) -> bool:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM users WHERE username = ?", (username,))
    exists = cur.fetchone() is not None
    conn.close()
    return exists


def get_user(username: str) -> sqlite3.Row | None:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE username = ?", (username,))
    row = cur.fetchone()
    conn.close()
    return row


def list_users() -> list:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users ORDER BY username")
    rows = cur.fetchall()
    conn.close()
    return rows


def list_users_with_traffic() -> list[dict]:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT u.username, u.password, u.sid, u.active,
               u.traffic_limit, u.expires_at, u.device_limit,
               COALESCE(SUM(t.tx + t.rx), 0) AS total,
               (SELECT COUNT(*) FROM devices d WHERE d.username = u.username) AS device_count
        FROM users u
        LEFT JOIN traffic t ON t.username = u.username
        GROUP BY u.username
        ORDER BY u.username
    """)
    rows = cur.fetchall()
    conn.close()
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
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (username, password, sid, traffic_limit, expires_at, device_limit) VALUES (?, ?, ?, ?, ?, ?)",
        (username, password, sid, traffic_limit, expires_at, device_limit),
    )
    conn.commit()
    conn.close()
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
) -> bool:
    if not user_exists(username):
        return False
    conn = get_db()
    cur = conn.cursor()
    if password is not None:
        cur.execute("UPDATE users SET password = ? WHERE username = ?", (password, username))
    if sid is not None:
        cur.execute("UPDATE users SET sid = ? WHERE username = ?", (sid, username))
    if active is not None:
        cur.execute("UPDATE users SET active = ? WHERE username = ?", (int(active), username))
    if traffic_limit is not None:
        cur.execute(
            "UPDATE users SET traffic_limit = ? WHERE username = ?",
            (traffic_limit, username),
        )
    if expires_at is not None:
        cur.execute("UPDATE users SET expires_at = ? WHERE username = ?", (expires_at, username))
    if device_limit is not None:
        cur.execute("UPDATE users SET device_limit = ? WHERE username = ?", (device_limit, username))
    conn.commit()
    conn.close()
    return True


def delete_user(username: str) -> bool:
    if not user_exists(username):
        return False
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM users WHERE username = ?", (username,))
    cur.execute("DELETE FROM traffic WHERE username = ?", (username,))
    cur.execute("DELETE FROM devices WHERE username = ?", (username,))
    cur.execute("DELETE FROM user_tags WHERE username = ?", (username,))
    conn.commit()
    conn.close()
    return True


# ── auth ──────────────────────────────────────────────────────────────────────


def check_auth(username: str, password: str) -> tuple[bool, str]:
    """
    Validates user credentials and checks limits.
    Returns (ok, reason) — reason is "" if ok, otherwise "invalid"/"inactive"/"expired"/"overlimit".
    """
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT u.active, u.traffic_limit, u.expires_at,
               COALESCE(SUM(CASE WHEN t.ts >= strftime('%Y-%m-%dT%H:%M:%SZ', 'now', 'start of day')
                                 THEN t.tx + t.rx ELSE 0 END), 0) AS total_traffic
        FROM users u
        LEFT JOIN traffic t ON t.username = u.username
        WHERE u.username = ? AND u.password = ?
        GROUP BY u.username
    """,
        (username, password),
    )
    row = cur.fetchone()
    conn.close()

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
    conn = get_db()
    cur = conn.cursor()
    if username:
        cur.execute("SELECT * FROM devices WHERE username = ? ORDER BY id", (username,))
    else:
        cur.execute("SELECT * FROM devices ORDER BY username, id")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


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
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT id FROM devices WHERE username = ? AND hwid = ?", (username, hwid))
    existing = cur.fetchone()

    if existing:
        cur.execute(
            "UPDATE devices SET device_os=?, ver_os=?, device_model=?, app_version=? WHERE id=?",
            (device_os, ver_os, device_model, app_version, existing["id"]),
        )
        conn.commit()
        conn.close()
        return True

    # New device — check limit
    cur.execute("SELECT device_limit FROM users WHERE username = ?", (username,))
    user_row = cur.fetchone()
    if user_row and user_row["device_limit"] > 0:
        cur.execute("SELECT COUNT(*) AS cnt FROM devices WHERE username = ?", (username,))
        cnt = cur.fetchone()["cnt"]
        if cnt >= user_row["device_limit"]:
            conn.close()
            return False

    cur.execute(
        "INSERT INTO devices (username, hwid, device_os, ver_os, device_model, app_version) VALUES (?, ?, ?, ?, ?, ?)",
        (username, hwid, device_os, ver_os, device_model, app_version),
    )
    conn.commit()
    conn.close()
    return True


def delete_device(device_id: int) -> bool:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM devices WHERE id = ?", (device_id,))
    count = cur.rowcount
    conn.commit()
    conn.close()
    return count > 0


def is_device_allowed(username: str, hwid: str) -> bool:
    """
    Returns True if the user has no device_limit set, or the HWID is already registered.
    Returns False if device_limit is set and the HWID is not yet registered.
    """
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT device_limit FROM users WHERE username = ?", (username,))
    user_row = cur.fetchone()
    if not user_row or not user_row["device_limit"]:
        conn.close()
        return True
    cur.execute("SELECT 1 FROM devices WHERE username = ? AND hwid = ?", (username, hwid))
    exists = cur.fetchone() is not None
    conn.close()
    return exists


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
    conn = get_db()
    cur = conn.cursor()
    where = "WHERE username = ?" if username else ""
    params = (username,) if username else ()
    cur.execute(f"{_TRAFFIC_SELECT} {where} GROUP BY username ORDER BY total DESC", params)
    rows = cur.fetchall()
    conn.close()
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


def delete_traffic(username: str | None = None) -> int:
    conn = get_db()
    cur = conn.cursor()
    if username:
        cur.execute("DELETE FROM traffic WHERE username = ?", (username,))
    else:
        cur.execute("DELETE FROM traffic")
    count = cur.rowcount
    conn.commit()
    conn.close()
    return count


# ── hosts ─────────────────────────────────────────────────────────────────────


def list_hosts(active_only: bool = False) -> list[dict]:
    conn = get_db()
    cur = conn.cursor()
    where = "WHERE active = 1" if active_only else ""
    cur.execute(f"SELECT * FROM hosts {where} ORDER BY address")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_host(address: str) -> sqlite3.Row | None:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM hosts WHERE address = ?", (address,))
    row = cur.fetchone()
    conn.close()
    return row


def host_exists(address: str) -> bool:
    return get_host(address) is not None


def create_host(
    address: str,
    name: str,
    api_address: str,
    api_secret: str,
    *,
    port: int = 443,
    active: bool = True,
) -> dict | None:
    if host_exists(address):
        return None
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO hosts (address, name, port, api_address, api_secret, active) VALUES (?, ?, ?, ?, ?, ?)",
        (address, name, port, api_address, api_secret, int(active)),
    )
    conn.commit()
    conn.close()
    return {
        "address": address,
        "name": name,
        "port": port,
        "api_address": api_address,
        "api_secret": api_secret,
        "active": active,
    }


def edit_host(
    address: str,
    *,
    name: str | None = None,
    port: int | None = None,
    api_address: str | None = None,
    api_secret: str | None = None,
    active: bool | None = None,
) -> bool:
    if not host_exists(address):
        return False
    conn = get_db()
    cur = conn.cursor()
    if name is not None:
        cur.execute("UPDATE hosts SET name = ? WHERE address = ?", (name, address))
    if port is not None:
        cur.execute("UPDATE hosts SET port = ? WHERE address = ?", (port, address))
    if api_address is not None:
        cur.execute("UPDATE hosts SET api_address = ? WHERE address = ?", (api_address, address))
    if api_secret is not None:
        cur.execute("UPDATE hosts SET api_secret = ? WHERE address = ?", (api_secret, address))
    if active is not None:
        cur.execute("UPDATE hosts SET active = ? WHERE address = ?", (int(active), address))
    conn.commit()
    conn.close()
    return True


def delete_host(address: str) -> bool:
    if not host_exists(address):
        return False
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM hosts WHERE address = ?", (address,))
    cur.execute("DELETE FROM host_tags WHERE host_address = ?", (address,))
    conn.commit()
    conn.close()
    return True


# ── tags ──────────────────────────────────────────────────────────────────────


def get_host_tags(address: str) -> list[str]:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT tag FROM host_tags WHERE host_address = ? ORDER BY tag", (address,))
    rows = cur.fetchall()
    conn.close()
    return [r["tag"] for r in rows]


def set_host_tags(address: str, tags: list[str]) -> None:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM host_tags WHERE host_address = ?", (address,))
    for tag in set(tags):
        cur.execute("INSERT OR IGNORE INTO host_tags (host_address, tag) VALUES (?, ?)", (address, tag))
    conn.commit()
    conn.close()


def get_user_tags(username: str) -> list[str]:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT tag FROM user_tags WHERE username = ? ORDER BY tag", (username,))
    rows = cur.fetchall()
    conn.close()
    return [r["tag"] for r in rows]


def set_user_tags(username: str, tags: list[str]) -> None:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM user_tags WHERE username = ?", (username,))
    for tag in set(tags):
        cur.execute("INSERT OR IGNORE INTO user_tags (username, tag) VALUES (?, ?)", (username, tag))
    conn.commit()
    conn.close()


def list_all_tags() -> list[str]:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT tag FROM host_tags
        UNION
        SELECT DISTINCT tag FROM user_tags
        ORDER BY tag
    """)
    rows = cur.fetchall()
    conn.close()
    return [r["tag"] for r in rows]


def list_hosts_for_user(username: str, active_only: bool = True) -> list[dict]:
    """
    Return hosts visible to the given user:
    - Hosts with no tags are visible to everyone.
    - Hosts with tags are visible only if the user shares at least one tag.
    """
    conn = get_db()
    cur = conn.cursor()
    where = "AND h.active = 1" if active_only else ""
    cur.execute(
        f"""
        SELECT h.* FROM hosts h
        WHERE (
            NOT EXISTS (SELECT 1 FROM host_tags ht WHERE ht.host_address = h.address)
            OR EXISTS (
                SELECT 1 FROM host_tags ht
                JOIN user_tags ut ON ut.tag = ht.tag
                WHERE ht.host_address = h.address AND ut.username = ?
            )
        )
        {where}
        ORDER BY h.address
    """,
        (username,),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── config ────────────────────────────────────────────────────────────────────


def get_config(key: str, default: str = "") -> str:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT value FROM config WHERE key = ?", (key,))
    row = cur.fetchone()
    conn.close()
    return row["value"] if row else default


def set_config(key: str, value: str) -> None:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()


def list_config() -> dict[str, str]:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT key, value FROM config ORDER BY key")
    rows = cur.fetchall()
    conn.close()
    return {r["key"]: r["value"] for r in rows}


def delete_config(key: str) -> bool:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM config WHERE key = ?", (key,))
    deleted = cur.rowcount > 0
    conn.commit()
    conn.close()
    return deleted
