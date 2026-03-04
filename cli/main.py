#!/usr/bin/env python3
"""Hystron CLI — manage users, traffic, hosts, config and the Docker service."""

import importlib.metadata
import os
import subprocess
import sys
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

# ── app bootstrap (database is available only inside the container or if
#    HYST_DB_PATH points to a real file on the host) ─────────────────────────
try:
    from app.database import (
        create_user, edit_user, delete_user, get_user, list_users, user_exists,
        get_traffic,
        create_host, edit_host, delete_host, get_host, list_hosts,
        list_config, set_config, delete_config,
    )
    from app.utils.sub import fmt_bytes
    _DB_AVAILABLE = True
except Exception:
    _DB_AVAILABLE = False

# ── constants ─────────────────────────────────────────────────────────────────
CONTAINER_NAME = os.environ.get("HYSTRON_CONTAINER", "hystron")
IMAGE_NAME      = os.environ.get("HYSTRON_IMAGE",     "hystron")

console = Console()


# ── helpers ───────────────────────────────────────────────────────────────────
def _require_db() -> None:
    if not _DB_AVAILABLE:
        console.print("[red]Database not accessible.[/red] Run this command inside the container "
                      "or set [bold]HYST_DB_PATH[/bold] correctly.")
        raise typer.Exit(1)


def _docker(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], check=check)


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
    ver = os.environ.get("APP_VERSION")
    if not ver:
        try:
            ver = importlib.metadata.version("Hystron")
        except importlib.metadata.PackageNotFoundError:
            ver = "unknown"
    console.print(f"[bold]Hystron[/bold] {ver}")


# ── tui ────────────────────────────────────────────────────────────────────────
@app.command()
def tui():
    """Open the interactive terminal admin UI."""
    try:
        from tui.admin import AdminApp
    except ImportError as exc:
        console.print(f"[red]TUI unavailable:[/red] {exc}")
        raise typer.Exit(1)
    AdminApp().run()


# ── status ────────────────────────────────────────────────────────────────────
@app.command()
def status():
    """Show Docker container status."""
    result = subprocess.run(
        ["docker", "inspect", "--format",
         "{{.Name}}\t{{.State.Status}}\t{{.State.StartedAt}}",
         CONTAINER_NAME],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        console.print(f"[red]Container '{CONTAINER_NAME}' not found.[/red]")
        raise typer.Exit(1)
    name, state, started = result.stdout.strip().split("\t")
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_row("[bold]container[/bold]", name.lstrip("/"))
    table.add_row("[bold]status[/bold]",    f"[green]{state}[/green]" if state == "running" else f"[red]{state}[/red]")
    table.add_row("[bold]started[/bold]",   started)
    console.print(table)


# ── restart ───────────────────────────────────────────────────────────────────
@app.command()
def restart():
    """Restart the Hystron Docker container."""
    console.print(f"Restarting [bold]{CONTAINER_NAME}[/bold]...")
    _docker("restart", CONTAINER_NAME)
    console.print("[green]Done.[/green]")


# ── update ────────────────────────────────────────────────────────────────────
@app.command()
def update():
    """Rebuild the Docker image and restart the container."""
    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    console.print(f"Building image [bold]{IMAGE_NAME}[/bold]...")
    _docker("build", "-t", f"{IMAGE_NAME}:latest", script_dir)

    console.print(f"Stopping container [bold]{CONTAINER_NAME}[/bold]...")
    _docker("stop", CONTAINER_NAME, check=False)
    _docker("rm",   CONTAINER_NAME, check=False)

    # Re-run with the same flags by inspecting the old container first.
    # Fall back to a simple restart when inspect data is unavailable.
    inspect = subprocess.run(
        ["docker", "inspect", "--format",
         "{{range .HostConfig.PortBindings}}{{.}}{{end}}",
         CONTAINER_NAME],
        capture_output=True, text=True,
    )
    console.print(f"Starting new container [bold]{CONTAINER_NAME}[/bold]...")
    _docker(
        "run", "-d",
        "--name", CONTAINER_NAME,
        "--restart", "unless-stopped",
        "-p", "9000:9000",
        "-p", "9001:9001",
        "-v", "/var/lib/hystron:/var/lib/hystron",
        f"{IMAGE_NAME}:latest",
    )
    console.print("[green]Update complete.[/green]")


# ─────────────────────────────────────────────────────────────────────────────
# Users sub-app
# ─────────────────────────────────────────────────────────────────────────────
users_app = typer.Typer(
    help="Manage users.", add_completion=False,
    rich_markup_mode="rich", no_args_is_help=True,
)
app.add_typer(users_app, name="users")


@users_app.command("list")
def users_list():
    """List all users."""
    _require_db()
    rows = list_users()
    if not rows:
        console.print("No users found.")
        return
    table = Table("username", "password", "active", "sid", "traffic_limit", "expires_at")
    for u in rows:
        table.add_row(
            u["username"],
            u["password"],
            "[green]yes[/green]" if u["active"] else "[red]no[/red]",
            u["sid"],
            str(u["traffic_limit"]),
            str(u["expires_at"]),
        )
    console.print(table)


@users_app.command("create")
def users_create(
    username: str = typer.Argument(..., help="New username"),
    traffic_limit: int = typer.Option(0, "--traffic-limit", "-t", help="Traffic limit in bytes (0 = unlimited)"),
    expires_at: int = typer.Option(0, "--expires-at", "-e", help="Expiry UNIX timestamp (0 = never)"),
):
    """Create a new user."""
    _require_db()
    result = create_user(username, traffic_limit=traffic_limit, expires_at=expires_at)
    if result is None:
        console.print(f"[red]User '{username}' already exists.[/red]")
        raise typer.Exit(1)
    console.print(f"[green]Created[/green]")
    console.print(f"  username : {result['username']}")
    console.print(f"  password : {result['password']}")
    console.print(f"  sid      : {result['sid']}")


@users_app.command("info")
def users_info(username: str = typer.Argument(..., help="Username")):
    """Show details of a user."""
    _require_db()
    row = get_user(username)
    if not row:
        console.print(f"[red]User '{username}' not found.[/red]")
        raise typer.Exit(1)
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_row("username",      row["username"])
    table.add_row("password",      row["password"])
    table.add_row("sid",           row["sid"])
    table.add_row("active",        "yes" if row["active"] else "no")
    table.add_row("traffic_limit", str(row["traffic_limit"]))
    table.add_row("expires_at",    str(row["expires_at"]))
    console.print(table)


@users_app.command("edit")
def users_edit(
    username: str = typer.Argument(..., help="Username to edit"),
    password: Optional[str]  = typer.Option(None, "--password", "-p"),
    sid:      Optional[str]  = typer.Option(None, "--sid",      "-s"),
    active:   Optional[bool] = typer.Option(None, "--active",   "-a"),
    traffic_limit: Optional[int] = typer.Option(None, "--traffic-limit", "-t"),
    expires_at:    Optional[int] = typer.Option(None, "--expires-at",    "-e"),
):
    """Edit an existing user."""
    _require_db()
    if not user_exists(username):
        console.print(f"[red]User '{username}' not found.[/red]")
        raise typer.Exit(1)
    edit_user(username, password=password, sid=sid, active=active,
              traffic_limit=traffic_limit, expires_at=expires_at)
    console.print(f"[green]User '{username}' updated.[/green]")


@users_app.command("delete")
def users_delete(
    username: str = typer.Argument(..., help="Username to delete"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Delete a user."""
    _require_db()
    if not yes:
        typer.confirm(f"Delete user '{username}'?", abort=True)
    if delete_user(username):
        console.print(f"[green]Deleted '{username}'.[/green]")
    else:
        console.print(f"[red]User '{username}' not found.[/red]")
        raise typer.Exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# Traffic sub-app
# ─────────────────────────────────────────────────────────────────────────────
traffic_app = typer.Typer(
    help="Show traffic statistics.", add_completion=False,
    rich_markup_mode="rich", no_args_is_help=False,
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
    _require_db()
    if username and not user_exists(username):
        console.print(f"[red]User '{username}' not found.[/red]")
        raise typer.Exit(1)
    rows = get_traffic(username)
    if not rows:
        console.print("No traffic data yet.")
        return
    periods = ["hour", "day", "week", "month", "total"]
    if username:
        r = rows[0]
        table = Table(show_header=False, box=None, padding=(0, 2))
        for p in periods:
            table.add_row(f"[bold]{p}[/bold]", fmt_bytes(r[p]))
        console.print(table)
    else:
        table = Table("username", *periods)
        for r in rows:
            table.add_row(r["username"], *[fmt_bytes(r[p]) for p in periods])
        console.print(table)


# ─────────────────────────────────────────────────────────────────────────────
# Hosts sub-app
# ─────────────────────────────────────────────────────────────────────────────
hosts_app = typer.Typer(
    help="Manage Hysteria2 hosts.", add_completion=False,
    rich_markup_mode="rich", no_args_is_help=True,
)
app.add_typer(hosts_app, name="hosts")


@hosts_app.command("list")
def hosts_list():
    """List all hosts."""
    _require_db()
    rows = list_hosts()
    if not rows:
        console.print("No hosts found.")
        return
    table = Table("address", "name", "port", "active", "api_address")
    for h in rows:
        table.add_row(
            h["address"], h["name"], str(h["port"]),
            "[green]yes[/green]" if h["active"] else "[red]no[/red]",
            h["api_address"],
        )
    console.print(table)


@hosts_app.command("create")
def hosts_create(
    address:    str = typer.Argument(..., help="Host address (domain or IP)"),
    name:       str = typer.Option(..., "--name",       "-n", help="Display name"),
    api_address:str = typer.Option(..., "--api-address","-a", help="Hysteria2 API address"),
    api_secret: str = typer.Option(..., "--api-secret", "-s", help="Hysteria2 API secret"),
    port:       int = typer.Option(443, "--port",       "-p", help="Port"),
    active:    bool = typer.Option(True,"--active",           help="Enable host"),
):
    """Add a new Hysteria2 host."""
    _require_db()
    result = create_host(address, name, api_address, api_secret, port=port, active=active)
    if result is None:
        console.print(f"[red]Host '{address}' already exists.[/red]")
        raise typer.Exit(1)
    console.print(f"[green]Host '{address}' created.[/green]")


@hosts_app.command("info")
def hosts_info(address: str = typer.Argument(..., help="Host address")):
    """Show details of a host."""
    _require_db()
    row = get_host(address)
    if not row:
        console.print(f"[red]Host '{address}' not found.[/red]")
        raise typer.Exit(1)
    table = Table(show_header=False, box=None, padding=(0, 2))
    for key in ("address", "name", "port", "api_address", "api_secret", "active"):
        val = row[key]
        table.add_row(key, str(val))
    console.print(table)


@hosts_app.command("edit")
def hosts_edit(
    address:     str            = typer.Argument(..., help="Host address"),
    name:        Optional[str]  = typer.Option(None, "--name",        "-n"),
    port:        Optional[int]  = typer.Option(None, "--port",        "-p"),
    api_address: Optional[str]  = typer.Option(None, "--api-address", "-a"),
    api_secret:  Optional[str]  = typer.Option(None, "--api-secret",  "-s"),
    active:      Optional[bool] = typer.Option(None, "--active"),
):
    """Edit an existing host."""
    _require_db()
    if not get_host(address):
        console.print(f"[red]Host '{address}' not found.[/red]")
        raise typer.Exit(1)
    edit_host(address, name=name, port=port,
              api_address=api_address, api_secret=api_secret, active=active)
    console.print(f"[green]Host '{address}' updated.[/green]")


@hosts_app.command("delete")
def hosts_delete(
    address: str  = typer.Argument(..., help="Host address"),
    yes:     bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Delete a host."""
    _require_db()
    if not yes:
        typer.confirm(f"Delete host '{address}'?", abort=True)
    if delete_host(address):
        console.print(f"[green]Deleted '{address}'.[/green]")
    else:
        console.print(f"[red]Host '{address}' not found.[/red]")
        raise typer.Exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# Config sub-app
# ─────────────────────────────────────────────────────────────────────────────
config_app = typer.Typer(
    help="Manage application configuration.", add_completion=False,
    rich_markup_mode="rich", no_args_is_help=True,
)
app.add_typer(config_app, name="config")


@config_app.command("list")
def config_list():
    """List all config keys."""
    _require_db()
    cfg = list_config()
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
    _require_db()
    cfg = list_config()
    if key not in cfg:
        console.print(f"[red]Key '{key}' not found.[/red]")
        raise typer.Exit(1)
    console.print(f"{key} = {cfg[key]}")


@config_app.command("set")
def config_set(
    key:   str = typer.Argument(..., help="Config key"),
    value: str = typer.Argument(..., help="New value"),
):
    """Set a config value."""
    _require_db()
    set_config(key, value)
    console.print(f"[green]{key}[/green] = {value}")


@config_app.command("delete")
def config_delete(
    key: str  = typer.Argument(..., help="Config key"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Delete a config key."""
    _require_db()
    if not yes:
        typer.confirm(f"Delete config key '{key}'?", abort=True)
    if delete_config(key):
        console.print(f"[green]Deleted '{key}'.[/green]")
    else:
        console.print(f"[red]Key '{key}' not found.[/red]")
        raise typer.Exit(1)


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app()

