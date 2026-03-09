#!/usr/bin/env python3
"""Hystron CLI — manage users, traffic, hosts, config and the Docker service."""

import os
import subprocess
from typing import Any, Optional

import httpx
import typer
from rich.console import Console
from rich.table import Table

# ── constants ─────────────────────────────────────────────────────────────────
CONTAINER_NAME = os.environ.get("HYSTRON_CONTAINER", "hystron")
IMAGE_NAME = os.environ.get("HYSTRON_IMAGE", "ghcr.io/bx-team/hystron")
INSTALL_DIR = os.environ.get("HYSTRON_INSTALL_DIR", "/opt/hystron")

API_URL = os.environ.get("HYSTRON_API", "http://127.0.0.1:9001").rstrip("/")

# Automatically updated during release process
VERSION = "1.1.1"

console = Console()


# ── helpers ───────────────────────────────────────────────────────────────────
def _fmt_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024  # type: ignore
    return f"{n:.1f} PB"


def _api(method: str, path: str, **kwargs: Any) -> Any:
    """Execute an HTTP request against the Hystron internal API."""
    url = f"{API_URL}{path}"
    try:
        r = httpx.request(method, url, timeout=10, **kwargs)
    except httpx.ConnectError:
        console.print(
            f"[red]Cannot reach API at[/red] [bold]{API_URL}[/bold]\n"
            "Is the container running?  "
            "Override the address with [bold]HYSTRON_API[/bold]."
        )
        raise typer.Exit(1)
    except httpx.TimeoutException:
        console.print(f"[red]Request timed out[/red] — {url}")
        raise typer.Exit(1)
    if r.status_code >= 400:
        try:
            err = r.json().get("error", r.text)
        except Exception:
            err = r.text
        console.print(f"[red]API {r.status_code}:[/red] {err}")
        raise typer.Exit(1)
    return r.json()


def _docker(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], check=check)


def _compose_cmd() -> list[str] | None:
    """Return the available docker compose command as a list, or None."""
    try:
        subprocess.run(["docker", "compose", "version"], check=True, capture_output=True)
        return ["docker", "compose"]
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    try:
        subprocess.run(["docker-compose", "version"], check=True, capture_output=True)
        return ["docker-compose"]
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _compose_file() -> str:
    return os.path.join(INSTALL_DIR, "docker-compose.yml")


def _compose_env() -> str:
    return os.path.join(INSTALL_DIR, ".env")


# ─────────────────────────────────────────────────────────────────────────────
# Root app
# ─────────────────────────────────────────────────────────────────────────────
app = typer.Typer(
    name="hystron",
    help="[bold green]Hystron[/bold green] — Hysteria2 panel management CLI.",
    add_completion=False,
    rich_markup_mode="rich",
    no_args_is_help=True,
)


# ── version ───────────────────────────────────────────────────────────────────
@app.command()
def version():
    """Show Hystron version."""
    console.print(f"[bold]Hystron[/bold] {VERSION}")


# ── tui ────────────────────────────────────────────────────────────────────────
@app.command()
def tui():
    """Open the interactive terminal admin UI (runs inside the container)."""
    try:
        os.execvp(
            "docker",
            [
                "docker",
                "exec",
                "-it",
                CONTAINER_NAME,
                "/code/.venv/bin/python",
                "-m",
                "tui",
            ],
        )
    except FileNotFoundError:
        console.print("[red]docker not found.[/red] Make sure Docker is installed and in PATH.")
        raise typer.Exit(1)


# ── status ────────────────────────────────────────────────────────────────────
@app.command()
def status():
    """Show Docker container status."""
    result = subprocess.run(
        [
            "docker",
            "inspect",
            "--format",
            "{{.Name}}\t{{.State.Status}}\t{{.State.StartedAt}}",
            CONTAINER_NAME,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        console.print(f"[red]Container '{CONTAINER_NAME}' not found.[/red]")
        raise typer.Exit(1)
    name, state, started = result.stdout.strip().split("\t")
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_row("[bold]container[/bold]", name.lstrip("/"))
    table.add_row(
        "[bold]status[/bold]",
        f"[green]{state}[/green]" if state == "running" else f"[red]{state}[/red]",
    )
    table.add_row("[bold]started[/bold]", started)
    console.print(table)


# ── restart ───────────────────────────────────────────────────────────────────
@app.command()
def restart():
    """Restart the Hystron container (via docker compose if available)."""
    compose = _compose_cmd()
    cf = _compose_file()
    if compose and os.path.isfile(cf):
        console.print(f"Restarting via [bold]{''.join(compose)}[/bold]...")
        env_args = ["--env-file", _compose_env()] if os.path.isfile(_compose_env()) else []
        subprocess.run([*compose, "-f", cf, *env_args, "restart"], check=True)
    else:
        console.print(f"Restarting container [bold]{CONTAINER_NAME}[/bold]...")
        _docker("restart", CONTAINER_NAME)
    console.print("[green]Done.[/green]")


# ── update ────────────────────────────────────────────────────────────────────
@app.command()
def update(
    version: Optional[str] = typer.Option(
        None, "--version", "-v", help="Image tag to pull (default: current or latest)"
    ),
):
    """Update Hystron by running the remote install script with the 'update' flag."""
    cmd = (
        "curl -fsSL https://raw.githubusercontent.com/BX-Team/hystron/refs/heads/master/install.sh "
        "-o /tmp/hystron.sh && sudo bash /tmp/hystron.sh update"
    )
    console.print("Running update script...")
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        raise typer.Exit(result.returncode)


# ─────────────────────────────────────────────────────────────────────────────
# Users sub-app
# ─────────────────────────────────────────────────────────────────────────────
users_app = typer.Typer(
    help="Manage users.",
    add_completion=False,
    rich_markup_mode="rich",
    no_args_is_help=True,
)
app.add_typer(users_app, name="users")


@users_app.command("list")
def users_list():
    """List all users."""
    rows = _api("GET", "/api/users")
    if not rows:
        console.print("No users found.")
        return
    table = Table(
        "username",
        "password",
        "active",
        "sid",
        "traffic_limit",
        "device_limit",
        "expires_at",
        "traffic_total",
    )
    for u in rows:
        table.add_row(
            u["username"],
            u["password"],
            "[green]yes[/green]" if u["active"] else "[red]no[/red]",
            u["sid"],
            _fmt_bytes(u["traffic_limit"]) if u["traffic_limit"] else "unlimited",
            str(u["device_limit"]) if u["device_limit"] else "unlimited",
            str(u["expires_at"]),
            _fmt_bytes(u.get("traffic_total", 0)),
        )
    console.print(table)


@users_app.command("create")
def users_create(
    username: str = typer.Argument(..., help="New username"),
    traffic_limit: float = typer.Option(0.0, "--traffic-limit", "-t", help="Traffic limit in GB (0 = unlimited)"),
    expires_at: int = typer.Option(0, "--expires-at", "-e", help="Expiry UNIX timestamp (0 = never)"),
    device_limit: int = typer.Option(0, "--device-limit", "-d", help="Max number of devices (0 = unlimited)"),
):
    """Create a new user."""
    result = _api(
        "POST",
        "/api/users",
        json={
            "username": username,
            "traffic_limit": int(traffic_limit * 1024**3),
            "expires_at": expires_at,
            "device_limit": device_limit,
        },
    )
    console.print("[green]Created[/green]")
    console.print(f"  username     : {result['username']}")
    console.print(f"  password     : {result['password']}")
    console.print(f"  sid          : {result['sid']}")
    console.print(f"  device_limit : {result['device_limit'] or 'unlimited'}")


@users_app.command("info")
def users_info(username: str = typer.Argument(..., help="Username")):
    """Show details of a user."""
    row = _api("GET", f"/api/users/{username}")
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_row("username", row["username"])
    table.add_row("password", row["password"])
    table.add_row("sid", row["sid"])
    table.add_row("active", "[green]yes[/green]" if row["active"] else "[red]no[/red]")
    table.add_row(
        "traffic_limit",
        _fmt_bytes(row["traffic_limit"]) if row["traffic_limit"] else "unlimited",
    )
    table.add_row(
        "device_limit",
        str(row["device_limit"]) if row["device_limit"] else "unlimited",
    )
    table.add_row("expires_at", str(row["expires_at"]))
    console.print(table)


@users_app.command("edit")
def users_edit(
    username: str = typer.Argument(..., help="Username to edit"),
    password: Optional[str] = typer.Option(None, "--password", "-p"),
    sid: Optional[str] = typer.Option(None, "--sid", "-s"),
    active: Optional[bool] = typer.Option(None, "--active", "-a"),
    traffic_limit: Optional[float] = typer.Option(None, "--traffic-limit", "-t", help="Traffic limit in GB"),
    expires_at: Optional[int] = typer.Option(None, "--expires-at", "-e"),
    device_limit: Optional[int] = typer.Option(
        None, "--device-limit", "-d", help="Max number of devices (0 = unlimited)"
    ),
):
    """Edit an existing user."""
    body: dict[str, Any] = {}
    if password is not None:
        body["password"] = password
    if sid is not None:
        body["sid"] = sid
    if active is not None:
        body["active"] = active
    if traffic_limit is not None:
        body["traffic_limit"] = int(traffic_limit * 1024**3)
    if expires_at is not None:
        body["expires_at"] = expires_at
    if device_limit is not None:
        body["device_limit"] = device_limit
    _api("PATCH", f"/api/users/{username}", json=body)
    console.print(f"[green]User '{username}' updated.[/green]")


@users_app.command("delete")
def users_delete(
    username: str = typer.Argument(..., help="Username to delete"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Delete a user."""
    if not yes:
        typer.confirm(f"Delete user '{username}'?", abort=True)
    _api("DELETE", f"/api/users/{username}")
    console.print(f"[green]Deleted '{username}'.[/green]")


@users_app.command("devices")
def users_devices(
    username: str = typer.Argument(..., help="Username"),
    delete: Optional[int] = typer.Option(None, "--delete", help="Delete device by ID"),
):
    """List or delete registered devices for a user."""
    if delete is not None:
        _api("DELETE", f"/api/users/{username}/devices/{delete}")
        console.print(f"[green]Device {delete} deleted.[/green]")
        return
    rows = _api("GET", f"/api/users/{username}/devices")
    if not rows:
        console.print("No devices registered.")
        return
    table = Table("id", "hwid", "os", "ver_os", "model", "app_version")
    for d in rows:
        table.add_row(
            str(d["id"]),
            d["hwid"],
            d["device_os"],
            d["ver_os"],
            d["device_model"],
            d["app_version"],
        )
    console.print(table)


# ─────────────────────────────────────────────────────────────────────────────
# Traffic sub-app
# ─────────────────────────────────────────────────────────────────────────────
traffic_app = typer.Typer(
    help="Show traffic statistics.",
    add_completion=False,
    rich_markup_mode="rich",
    no_args_is_help=False,
)
app.add_typer(traffic_app, name="traffic")


@traffic_app.callback(invoke_without_command=True)
def traffic_list(
    ctx: typer.Context,
    username: Optional[str] = typer.Argument(None, help="Filter by username"),
):
    """Show traffic. Pass a username to see per-user stats."""
    if ctx.invoked_subcommand is not None:
        return
    periods = ["hour", "day", "week", "month", "total"]
    if username:
        r = _api("GET", f"/api/traffic/{username}")
        table = Table(show_header=False, box=None, padding=(0, 2))
        for p in periods:
            table.add_row(f"[bold]{p}[/bold]", _fmt_bytes(r.get(p, 0)))
        console.print(table)
    else:
        rows = _api("GET", "/api/traffic")
        if not rows:
            console.print("No traffic data yet.")
            return
        table = Table("username", *periods)
        for r in rows:
            table.add_row(r["username"], *[_fmt_bytes(r.get(p, 0)) for p in periods])
        console.print(table)


# ─────────────────────────────────────────────────────────────────────────────
# Hosts sub-app
# ─────────────────────────────────────────────────────────────────────────────
hosts_app = typer.Typer(
    help="Manage Hysteria2 hosts.",
    add_completion=False,
    rich_markup_mode="rich",
    no_args_is_help=True,
)
app.add_typer(hosts_app, name="hosts")


@hosts_app.command("list")
def hosts_list():
    """List all hosts."""
    rows = _api("GET", "/api/hosts")
    if not rows:
        console.print("No hosts found.")
        return
    table = Table("address", "name", "port", "active", "api_address")
    for h in rows:
        table.add_row(
            h["address"],
            h["name"],
            str(h["port"]),
            "[green]yes[/green]" if h["active"] else "[red]no[/red]",
            h["api_address"],
        )
    console.print(table)


@hosts_app.command("create")
def hosts_create(
    address: str = typer.Argument(..., help="Host address (domain or IP)"),
    name: str = typer.Option(..., "--name", "-n", help="Display name"),
    api_address: str = typer.Option(..., "--api-address", "-a", help="Hysteria2 API address"),
    api_secret: str = typer.Option(..., "--api-secret", "-s", help="Hysteria2 API secret"),
    port: int = typer.Option(443, "--port", "-p", help="Port"),
    active: bool = typer.Option(True, "--active", help="Enable host"),
):
    """Add a new Hysteria2 host."""
    _api(
        "POST",
        "/api/hosts",
        json={
            "address": address,
            "name": name,
            "api_address": api_address,
            "api_secret": api_secret,
            "port": port,
            "active": active,
        },
    )
    console.print(f"[green]Host '{address}' created.[/green]")


@hosts_app.command("info")
def hosts_info(address: str = typer.Argument(..., help="Host address")):
    """Show details of a host."""
    row = _api("GET", f"/api/hosts/{address}")
    table = Table(show_header=False, box=None, padding=(0, 2))
    for key in ("address", "name", "port", "api_address", "api_secret", "active"):
        table.add_row(key, str(row[key]))
    console.print(table)


@hosts_app.command("edit")
def hosts_edit(
    address: str = typer.Argument(..., help="Host address"),
    name: Optional[str] = typer.Option(None, "--name", "-n"),
    port: Optional[int] = typer.Option(None, "--port", "-p"),
    api_address: Optional[str] = typer.Option(None, "--api-address", "-a"),
    api_secret: Optional[str] = typer.Option(None, "--api-secret", "-s"),
    active: Optional[bool] = typer.Option(None, "--active"),
):
    """Edit an existing host."""
    body: dict[str, Any] = {}
    if name is not None:
        body["name"] = name
    if port is not None:
        body["port"] = port
    if api_address is not None:
        body["api_address"] = api_address
    if api_secret is not None:
        body["api_secret"] = api_secret
    if active is not None:
        body["active"] = active
    _api("PATCH", f"/api/hosts/{address}", json=body)
    console.print(f"[green]Host '{address}' updated.[/green]")


@hosts_app.command("delete")
def hosts_delete(
    address: str = typer.Argument(..., help="Host address"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Delete a host."""
    if not yes:
        typer.confirm(f"Delete host '{address}'?", abort=True)
    _api("DELETE", f"/api/hosts/{address}")
    console.print(f"[green]Deleted '{address}'.[/green]")


# ─────────────────────────────────────────────────────────────────────────────
# Config sub-app
# ─────────────────────────────────────────────────────────────────────────────
config_app = typer.Typer(
    help="Manage application configuration.",
    add_completion=False,
    rich_markup_mode="rich",
    no_args_is_help=True,
)
app.add_typer(config_app, name="config")


@config_app.command("list")
def config_list():
    """List all config keys."""
    cfg = _api("GET", "/api/config")
    if not cfg:
        console.print("No config found.")
        return
    table = Table("key", "value")
    for k, v in cfg.items():
        table.add_row(k, v)
    console.print(table)


@config_app.command("get")
def config_get(key: str = typer.Argument(..., help="Config key")):
    """Get a config value."""
    result = _api("GET", f"/api/config/{key}")
    console.print(f"{result['key']} = {result['value']}")


@config_app.command("set")
def config_set(
    key: str = typer.Argument(..., help="Config key"),
    value: list[str] = typer.Argument(..., help="New value (words joined by spaces)"),
):
    """Set a config value."""
    v = " ".join(value)
    _api("PUT", f"/api/config/{key}", json={"value": v})
    console.print(f"[green]{key}[/green] = {v}")


@config_app.command("delete")
def config_delete(
    key: str = typer.Argument(..., help="Config key"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Delete a config key."""
    if not yes:
        typer.confirm(f"Delete config key '{key}'?", abort=True)
    _api("DELETE", f"/api/config/{key}")
    console.print(f"[green]Deleted '{key}'.[/green]")


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app(prog_name="hystron")
