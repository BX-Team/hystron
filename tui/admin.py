import os
import sys

# Allow running as a plain script: python tui/admin.py
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collections.abc import Callable
from datetime import datetime

import qrcode
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.coordinate import Coordinate
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    Static,
    Switch,
    TabbedContent,
    TabPane,
)

from app.database import (
    create_host,
    create_user,
    delete_config,
    delete_device,
    delete_host,
    delete_user,
    edit_host,
    edit_user,
    get_config,
    get_host,
    get_traffic,
    get_user,
    list_config,
    list_devices,
    list_hosts,
    list_users_with_traffic,
    set_config,
)
from app.utils.sub import fmt_bytes
from tui import BaseModal

# ── helpers ──────────────────────────────────────────────────────────────────


def _fmt_ts(ts: int) -> str:
    """Format unix timestamp → date string, or '—' when zero."""
    if not ts:
        return "\u2014"
    try:
        return datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")
    except (OSError, OverflowError, ValueError):
        return str(ts)


def _center(text: str, width: int) -> str:
    pad = width - len(text)
    left = pad // 2
    return " " * left + text + " " * (pad - left)


def _qr_unicode(text: str) -> str:
    """Render a QR code as a compact Unicode string using half-block characters.

    Each terminal row encodes two QR module rows using:
      █  both dark
      ▀  top dark, bottom light
      ▄  top light, bottom dark
      (space) both light
    """
    qr = qrcode.QRCode(border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(text)
    qr.make(fit=True)
    matrix = qr.get_matrix()  # list[list[bool]], True = dark

    # Pad to even number of rows
    if len(matrix) % 2:
        matrix.append([False] * len(matrix[0]))

    lines: list[str] = []
    for y in range(0, len(matrix), 2):
        row_top = matrix[y]
        row_bot = matrix[y + 1]
        line = ""
        for top, bot in zip(row_top, row_bot):
            if top and bot:
                line += "█"
            elif top:
                line += "▀"
            elif bot:
                line += "▄"
            else:
                line += " "
        lines.append(line)
    return "\n".join(lines)


# ── modal: user QR ────────────────────────────────────────────────────────────


class UserQRModal(BaseModal):
    """Show a subscription QR code for a user."""

    def __init__(self, username: str, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.username = username

    def compose(self) -> ComposeResult:
        with Container(classes="modal-box-qr"):
            yield Static(f"QR code — {self.username}", classes="modal-title")
            yield Static("", id="qr-display", classes="qr-display")
            yield Static("", id="qr-url", classes="qr-url")
            with Horizontal(classes="button-row"):
                yield Button("Close", id="close", variant="primary")

    async def on_mount(self) -> None:
        row = get_user(self.username)
        if not row:
            self.query_one("#qr-display").update("[red]User not found.[/red]")
            return

        sid = row["sid"]
        sub_path = get_config("subscription_path", "/sub")
        base_url = get_config("base_url", "").rstrip("/")
        if not base_url:
            url = f"(set base_url in config){sub_path}/{sid}"
            self.query_one("#qr-display").update(
                "[yellow]Set [bold]base_url[/bold] config key to generate a QR code.[/yellow]"
            )
        else:
            url = f"{base_url}{sub_path}/{sid}"
            self.query_one("#qr-display").update(_qr_unicode(url))

        self.query_one("#qr-url").update(url)
        self.set_focus(self.query_one("#close"))

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        await self.key_escape()

# ── modal: user devices ───────────────────────────────────────────────────────


class UserDevicesModal(BaseModal):
    """Show and manage registered devices for a user."""

    BINDINGS = [
        Binding("d", "delete_device", "Delete"),
        Binding("r", "refresh", "Refresh"),
    ]

    def __init__(self, username: str, on_close: Callable, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.username = username
        self.on_close = on_close

    def compose(self) -> ComposeResult:
        with Container(classes="modal-box-devices"):
            yield Static(f"Devices — {self.username}", classes="modal-title")
            yield DataTable(id="devices-table", classes="devices-table")
            with Horizontal(classes="button-row"):
                yield Button("Delete", id="delete", variant="error")
                yield Button("Close", id="close", variant="primary")

    async def on_mount(self) -> None:
        self.table = self.query_one("#devices-table", DataTable)
        self.table.cursor_type = "row"
        await self.action_refresh()
        self.set_focus(self.table)

    async def action_refresh(self) -> None:
        self.table.clear(columns=True)
        devices = list_devices(self.username)
        if not devices:
            self.table.add_columns("  (no devices registered)  ")
            return
        columns = ["#", "HWID", "OS", "Ver OS", "Model", "App Version"]
        data = [
            [
                str(idx),
                d["hwid"],
                d["device_os"],
                d["ver_os"],
                d["device_model"],
                d["app_version"],
            ]
            for idx, d in enumerate(devices, 1)
        ]
        col_widths = [max(len(columns[i]), max(len(row[i]) for row in data)) for i in range(len(columns))]
        self.table.add_columns(*[_center(c, col_widths[i]) for i, c in enumerate(columns)])
        for row, orig in zip(data, devices):
            self.table.add_row(
                *[_center(cell, col_widths[i]) for i, cell in enumerate(row)],
                key=str(orig["id"]),
            )

    @property
    def _selected_device_id(self) -> int | None:
        try:
            key = self.table.coordinate_to_cell_key(Coordinate(self.table.cursor_row, 0)).row_key.value
            return int(key) if key is not None else None
        except Exception:
            return None

    async def action_delete_device(self) -> None:
        device_id = self._selected_device_id
        if device_id is None:
            return
        delete_device(device_id)
        self.notify("Device removed", severity="success", title="Deleted")
        self.on_close()
        await self.action_refresh()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "delete":
            await self.action_delete_device()
        elif event.button.id == "close":
            await self.key_escape()

# ── modals: users ─────────────────────────────────────────────────────────────


class UserCreateModal(BaseModal):
    """Create a new user."""

    def __init__(self, on_close: Callable, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.on_close = on_close

    def compose(self) -> ComposeResult:
        with Container(classes="modal-box"):
            yield Static("Create user", classes="modal-title")
            with Vertical(classes="input-container"):
                yield Input(placeholder="Username", id="username")
                yield Input(
                    placeholder="Traffic limit GB     (0 = unlimited)",
                    id="traffic_limit",
                )
                yield Input(
                    placeholder="Device limit         (0 = unlimited)",
                    id="device_limit",
                )
                yield Input(placeholder="Expires at unix ts   (0 = never)", id="expires_at")
            with Horizontal(classes="button-row"):
                yield Button("Create", id="create", variant="success")
                yield Button("Cancel", id="cancel", variant="error")

    async def on_mount(self) -> None:
        self.set_focus(self.query_one("#username"))

    async def key_enter(self) -> None:
        if not self.query_one("#cancel").has_focus:
            await self.on_button_pressed(Button.Pressed(self.query_one("#create")))

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "create":
            username = self.query_one("#username").value.strip()
            if not username:
                self.notify("Username is required", severity="error", title="Error")
                return
            tl_raw = self.query_one("#traffic_limit").value.strip()
            dl_raw = self.query_one("#device_limit").value.strip()
            ea_raw = self.query_one("#expires_at").value.strip()
            try:
                traffic_limit = int(float(tl_raw) * 1024**3) if tl_raw else 0
                device_limit = int(dl_raw) if dl_raw else 0
                expires_at = int(ea_raw) if ea_raw else 0
            except ValueError:
                self.notify(
                    "Traffic limit must be a number (GB), device limit and expires must be integers",
                    severity="error",
                    title="Error",
                )
                return
            result = create_user(
                username, traffic_limit=traffic_limit, expires_at=expires_at, device_limit=device_limit
            )
            if result is None:
                self.notify(f"User '{username}' already exists", severity="error", title="Error")
                return
            self.notify(
                f"User created\npw: {result['password']}",
                severity="success",
                title=f"User '{username}'",
            )
            self.on_close()
        await self.key_escape()


class UserEditModal(BaseModal):
    """Edit an existing user."""

    def __init__(self, username: str, on_close: Callable, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.username = username
        self.on_close = on_close

    def compose(self) -> ComposeResult:
        with Container(classes="modal-box"):
            yield Static(f"Edit user '{self.username}'", classes="modal-title")
            with Vertical(classes="input-container"):
                yield Input(
                    placeholder="New password       (empty = keep)",
                    id="password",
                    password=True,
                )
                yield Input(placeholder="New SID            (empty = keep)", id="sid")
                yield Input(placeholder="Traffic limit GB    (empty = keep)", id="traffic_limit")
                yield Input(placeholder="Device limit        (empty = keep)", id="device_limit")
                yield Input(placeholder="Expires at unix ts  (empty = keep)", id="expires_at")
                with Horizontal(classes="switch-row"):
                    yield Label("Active: ")
                    yield Switch(animate=False, id="active", value=True)
            with Horizontal(classes="button-row"):
                yield Button("Save", id="save", variant="success")
                yield Button("Cancel", id="cancel", variant="error")

    async def on_mount(self) -> None:
        row = get_user(self.username)
        if row:
            self.query_one("#active").value = bool(row["active"])
        self.set_focus(self.query_one("#password"))

    async def key_enter(self) -> None:
        if not self.query_one("#active").has_focus and not self.query_one("#cancel").has_focus:
            await self.on_button_pressed(Button.Pressed(self.query_one("#save")))

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save":
            password = self.query_one("#password").value.strip() or None
            sid = self.query_one("#sid").value.strip() or None
            active = self.query_one("#active").value
            tl_raw = self.query_one("#traffic_limit").value.strip()
            dl_raw = self.query_one("#device_limit").value.strip()
            ea_raw = self.query_one("#expires_at").value.strip()
            try:
                traffic_limit = int(float(tl_raw) * 1024**3) if tl_raw else None
                device_limit = int(dl_raw) if dl_raw else None
                expires_at = int(ea_raw) if ea_raw else None
            except ValueError:
                self.notify(
                    "Traffic limit must be a number (GB), device limit and expires must be integers",
                    severity="error",
                    title="Error",
                )
                return
            edit_user(
                self.username,
                password=password,
                sid=sid,
                active=active,
                traffic_limit=traffic_limit,
                expires_at=expires_at,
                device_limit=device_limit,
            )
            self.notify(f"User '{self.username}' updated", severity="success", title="Success")
            self.on_close()
        await self.key_escape()


class UserDeleteModal(BaseModal):
    """Confirm user deletion."""

    def __init__(self, username: str, on_close: Callable, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.username = username
        self.on_close = on_close

    def compose(self) -> ComposeResult:
        with Container(classes="modal-box-delete"):
            yield Static(
                f"Delete user '{self.username}'?\nThis cannot be undone.",
                classes="modal-title",
            )
            with Horizontal(classes="button-row"):
                yield Button("Delete", id="delete", variant="error")
                yield Button("Cancel", id="cancel", variant="primary")

    async def on_mount(self) -> None:
        self.set_focus(self.query_one("#cancel"))

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "delete":
            delete_user(self.username)
            self.notify(f"User '{self.username}' deleted", severity="success", title="Deleted")
            self.on_close()
        await self.key_escape()


# ── modals: hosts ─────────────────────────────────────────────────────────────


class HostCreateModal(BaseModal):
    """Create a new host."""

    def __init__(self, on_close: Callable, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.on_close = on_close

    def compose(self) -> ComposeResult:
        with Container(classes="modal-box"):
            yield Static("Create node", classes="modal-title")
            with Vertical(classes="input-container"):
                yield Input(placeholder="Address   (e.g. vpn.example.com)", id="address")
                yield Input(placeholder="Name      (display label)", id="name")
                yield Input(placeholder="Port      (default 443)", id="port")
                yield Input(
                    placeholder="Protocols (default: hysteria2,vless,trojan)",
                    id="protocols",
                )
                with Horizontal(classes="switch-row"):
                    yield Label("Active: ")
                    yield Switch(animate=False, id="active", value=True)
            with Horizontal(classes="button-row"):
                yield Button("Create", id="create", variant="success")
                yield Button("Cancel", id="cancel", variant="error")

    async def on_mount(self) -> None:
        self.set_focus(self.query_one("#address"))

    async def key_enter(self) -> None:
        if not self.query_one("#active").has_focus and not self.query_one("#cancel").has_focus:
            await self.on_button_pressed(Button.Pressed(self.query_one("#create")))

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "create":
            address = self.query_one("#address").value.strip()
            if not address:
                self.notify("Address is required", severity="error", title="Error")
                return
            name = self.query_one("#name").value.strip() or address
            port_raw = self.query_one("#port").value.strip()
            protocols_raw = self.query_one("#protocols").value.strip()
            active = self.query_one("#active").value
            try:
                port = int(port_raw) if port_raw else 443
            except ValueError:
                self.notify("Port must be a number", severity="error", title="Error")
                return
            protocols = [p.strip() for p in protocols_raw.split(",") if p.strip()] or ["hysteria2"]
            node_ports = {p: port for p in protocols}
            result = create_host(address, name, port=port, active=active, protocols=protocols, node_ports=node_ports)
            if result is None:
                self.notify(f"Node '{address}' already exists", severity="error", title="Error")
                return
            token = result.get("node_token", "?")
            self.notify(
                f"Node '{address}' created.\nToken: {token}\n(copy to node's .env)",
                severity="success",
                title="Success",
                timeout=15,
            )
            self.on_close()
        await self.key_escape()


class HostEditModal(BaseModal):
    """Edit an existing host."""

    def __init__(self, address: str, on_close: Callable, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.address = address
        self.on_close = on_close

    def compose(self) -> ComposeResult:
        with Container(classes="modal-box"):
            yield Static(f"Edit node '{self.address}'", classes="modal-title")
            with Vertical(classes="input-container"):
                yield Input(placeholder="Name      (empty = keep)", id="name")
                yield Input(placeholder="Port      (empty = keep)", id="port")
                yield Input(placeholder="Protocols (empty = keep, e.g. hysteria2,vless)", id="protocols")
                with Horizontal(classes="switch-row"):
                    yield Label("Active: ")
                    yield Switch(animate=False, id="active", value=True)
            with Horizontal(classes="button-row"):
                yield Button("Save", id="save", variant="success")
                yield Button("Cancel", id="cancel", variant="error")

    async def on_mount(self) -> None:
        row = get_host(self.address)
        if row:
            self.query_one("#active").value = bool(row["active"])
        self.set_focus(self.query_one("#name"))

    async def key_enter(self) -> None:
        if not self.query_one("#active").has_focus and not self.query_one("#cancel").has_focus:
            await self.on_button_pressed(Button.Pressed(self.query_one("#save")))

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save":
            import json as _json
            name = self.query_one("#name").value.strip() or None
            port_raw = self.query_one("#port").value.strip()
            protocols_raw = self.query_one("#protocols").value.strip()
            active = self.query_one("#active").value
            try:
                port = int(port_raw) if port_raw else None
            except ValueError:
                self.notify("Port must be a number", severity="error", title="Error")
                return
            protocols = [p.strip() for p in protocols_raw.split(",") if p.strip()] or None
            edit_host(
                self.address,
                name=name,
                port=port,
                active=active,
                protocols=protocols,
            )
            self.notify(f"Node '{self.address}' updated", severity="success", title="Success")
            self.on_close()
        await self.key_escape()


class HostDeleteModal(BaseModal):
    """Confirm host deletion."""

    def __init__(self, address: str, on_close: Callable, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.address = address
        self.on_close = on_close

    def compose(self) -> ComposeResult:
        with Container(classes="modal-box-delete"):
            yield Static(
                f"Delete node '{self.address}'?\nThis cannot be undone.",
                classes="modal-title",
            )
            with Horizontal(classes="button-row"):
                yield Button("Delete", id="delete", variant="error")
                yield Button("Cancel", id="cancel", variant="primary")

    async def on_mount(self) -> None:
        self.set_focus(self.query_one("#cancel"))

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "delete":
            delete_host(self.address)
            self.notify(f"Node '{self.address}' deleted", severity="success", title="Deleted")
            self.on_close()
        await self.key_escape()


# ── modals: config ────────────────────────────────────────────────────────────


class ConfigEditModal(BaseModal):
    """Edit the value of an existing config key."""

    def __init__(self, key: str, value: str, on_close: Callable, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._key = key
        self._value = value
        self.on_close = on_close

    def compose(self) -> ComposeResult:
        with Container(classes="modal-box"):
            yield Static(f"Edit config '{self._key}'", classes="modal-title")
            with Vertical(classes="input-container"):
                yield Input(placeholder="Value", id="value")
            with Horizontal(classes="button-row"):
                yield Button("Save", id="save", variant="success")
                yield Button("Cancel", id="cancel", variant="error")

    async def on_mount(self) -> None:
        inp = self.query_one("#value")
        inp.value = self._value
        self.set_focus(inp)

    async def key_enter(self) -> None:
        if not self.query_one("#cancel").has_focus:
            await self.on_button_pressed(Button.Pressed(self.query_one("#save")))

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save":
            value = self.query_one("#value").value
            set_config(self._key, value)
            self.notify(f"Config '{self._key}' updated", severity="success", title="Success")
            self.on_close()
        await self.key_escape()


class ConfigNewModal(BaseModal):
    """Create a new config key/value pair."""

    def __init__(self, on_close: Callable, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.on_close = on_close

    def compose(self) -> ComposeResult:
        with Container(classes="modal-box"):
            yield Static("New config entry", classes="modal-title")
            with Vertical(classes="input-container"):
                yield Input(placeholder="Key", id="key")
                yield Input(placeholder="Value", id="value")
            with Horizontal(classes="button-row"):
                yield Button("Create", id="create", variant="success")
                yield Button("Cancel", id="cancel", variant="error")

    async def on_mount(self) -> None:
        self.set_focus(self.query_one("#key"))

    async def key_enter(self) -> None:
        if not self.query_one("#cancel").has_focus:
            await self.on_button_pressed(Button.Pressed(self.query_one("#create")))

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "create":
            key = self.query_one("#key").value.strip()
            value = self.query_one("#value").value
            if not key:
                self.notify("Key is required", severity="error", title="Error")
                return
            set_config(key, value)
            self.notify(f"Config '{key}' created", severity="success", title="Success")
            self.on_close()
        await self.key_escape()


class ConfigDeleteModal(BaseModal):
    """Confirm config key deletion."""

    def __init__(self, key: str, on_close: Callable, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._key = key
        self.on_close = on_close

    def compose(self) -> ComposeResult:
        with Container(classes="modal-box-delete"):
            yield Static(
                f"Delete config key '{self._key}'?\nThis cannot be undone.",
                classes="modal-title",
            )
            with Horizontal(classes="button-row"):
                yield Button("Delete", id="delete", variant="error")
                yield Button("Cancel", id="cancel", variant="primary")

    async def on_mount(self) -> None:
        self.set_focus(self.query_one("#cancel"))

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "delete":
            delete_config(self._key)
            self.notify(f"Config '{self._key}' deleted", severity="success", title="Deleted")
            self.on_close()
        await self.key_escape()


# ── tab content widgets ───────────────────────────────────────────────────────


class UsersContent(Static):
    """Users tab — CRUD for user accounts."""

    BINDINGS = [
        Binding("c", "create_user", "Create"),
        Binding("e", "edit_user", "Edit"),
        Binding("d", "delete_user", "Delete"),
        Binding("q", "show_qr", "QR code"),
        Binding("v", "show_devices", "Devices"),
        Binding("r", "refresh", "Refresh"),
    ]

    def compose(self) -> ComposeResult:
        yield DataTable(id="users-table")

    async def on_mount(self) -> None:
        self.table = self.query_one("#users-table", DataTable)
        self.table.cursor_type = "row"
        await self.action_refresh()

    # ── data loading ──────────────────────────────────────────────────────────

    async def action_refresh(self) -> None:
        self.table.clear(columns=True)
        rows = list_users_with_traffic()
        if not rows:
            self.table.add_columns("  (no users — press 'c' to create one)  ")
            return

        columns = [
            "#",
            "Username",
            "Active",
            "Traffic Limit",
            "Devices",
            "Expires At",
            "Total Traffic",
            "SID",
        ]
        data = [
            [
                str(idx),
                r["username"],
                "\u2714" if r["active"] else "\u2716",
                fmt_bytes(r["traffic_limit"]) if r["traffic_limit"] else "unlimited",
                f"{r.get('device_count', 0)}/{r['device_limit']}"
                if r["device_limit"]
                else f"{r.get('device_count', 0)}/\u221e",
                _fmt_ts(r["expires_at"]),
                fmt_bytes(r["total"]),
                r["sid"],
            ]
            for idx, r in enumerate(rows, 1)
        ]
        col_widths = [max(len(columns[i]), max(len(row[i]) for row in data)) for i in range(len(columns))]
        self.table.add_columns(*[_center(c, col_widths[i]) for i, c in enumerate(columns)])
        for row, orig in zip(data, rows):
            self.table.add_row(
                *[_center(cell, col_widths[i]) for i, cell in enumerate(row)],
                key=orig["username"],
            )

    # ── selection helper ──────────────────────────────────────────────────────

    @property
    def _selected_username(self) -> str | None:
        if not self.table.columns:
            return None
        try:
            return self.table.coordinate_to_cell_key(Coordinate(self.table.cursor_row, 1)).row_key.value
        except Exception:
            return None

    def _refresh_table(self) -> None:
        self.run_worker(self.action_refresh)

    # ── actions ───────────────────────────────────────────────────────────────

    async def action_create_user(self) -> None:
        self.app.push_screen(UserCreateModal(self._refresh_table))

    async def action_edit_user(self) -> None:
        username = self._selected_username
        if not username:
            return
        self.app.push_screen(UserEditModal(username, self._refresh_table))

    async def key_enter(self) -> None:
        await self.action_edit_user()

    async def action_delete_user(self) -> None:
        username = self._selected_username
        if not username:
            return
        self.app.push_screen(UserDeleteModal(username, self._refresh_table))

    async def action_show_qr(self) -> None:
        username = self._selected_username
        if not username:
            return
        self.app.push_screen(UserQRModal(username))

    async def action_show_devices(self) -> None:
        username = self._selected_username
        if not username:
            return
        self.app.push_screen(UserDevicesModal(username, self._refresh_table))


class TrafficContent(Static):
    """Traffic tab — read-only per-user usage overview."""

    BINDINGS = [
        Binding("r", "refresh", "Refresh"),
    ]

    def compose(self) -> ComposeResult:
        yield DataTable(id="traffic-table")

    async def on_mount(self) -> None:
        self.table = self.query_one("#traffic-table", DataTable)
        self.table.cursor_type = "row"
        await self.action_refresh()

    async def action_refresh(self) -> None:
        self.table.clear(columns=True)
        rows = get_traffic()
        if not rows:
            self.table.add_columns("  (no traffic data yet)  ")
            return

        columns = ["#", "Username", "Hour", "Day", "Week", "Month", "Total"]
        data = [
            [
                str(idx),
                r["username"],
                fmt_bytes(r["hour"]),
                fmt_bytes(r["day"]),
                fmt_bytes(r["week"]),
                fmt_bytes(r["month"]),
                fmt_bytes(r["total"]),
            ]
            for idx, r in enumerate(rows, 1)
        ]
        col_widths = [max(len(columns[i]), max(len(row[i]) for row in data)) for i in range(len(columns))]
        self.table.add_columns(*[_center(c, col_widths[i]) for i, c in enumerate(columns)])
        for row, orig in zip(data, rows):
            self.table.add_row(
                *[_center(cell, col_widths[i]) for i, cell in enumerate(row)],
                key=orig["username"],
            )


class HostsContent(Static):
    """Hosts tab — CRUD for Hysteria2 server hosts."""

    BINDINGS = [
        Binding("c", "create_host", "Create"),
        Binding("e", "edit_host", "Edit"),
        Binding("d", "delete_host", "Delete"),
        Binding("r", "refresh", "Refresh"),
    ]

    def compose(self) -> ComposeResult:
        yield DataTable(id="hosts-table")

    async def on_mount(self) -> None:
        self.table = self.query_one("#hosts-table", DataTable)
        self.table.cursor_type = "row"
        await self.action_refresh()

    async def action_refresh(self) -> None:
        self.table.clear(columns=True)
        rows = list_hosts()
        if not rows:
            self.table.add_columns("  (no nodes — press 'c' to create one)  ")
            return

        import json as _json
        import time as _time
        _now = int(_time.time())
        columns = ["#", "Address", "Name", "Port", "Protocols", "Online", "Active"]
        data = [
            [
                str(idx),
                r["address"],
                r["name"],
                str(r["port"]),
                ", ".join(_json.loads(r["protocols"]) if isinstance(r["protocols"], str) else (r.get("protocols") or ["hysteria2"])),
                "\u2714" if (r.get("last_seen", 0) or 0) > _now - 60 else "\u2716",
                "\u2714" if r["active"] else "\u2716",
            ]
            for idx, r in enumerate(rows, 1)
        ]
        col_widths = [max(len(columns[i]), max(len(row[i]) for row in data)) for i in range(len(columns))]
        self.table.add_columns(*[_center(c, col_widths[i]) for i, c in enumerate(columns)])
        for row, orig in zip(data, rows):
            self.table.add_row(
                *[_center(cell, col_widths[i]) for i, cell in enumerate(row)],
                key=orig["address"],
            )

    @property
    def _selected_address(self) -> str | None:
        if not self.table.columns:
            return None
        try:
            return self.table.coordinate_to_cell_key(Coordinate(self.table.cursor_row, 1)).row_key.value
        except Exception:
            return None

    def _refresh_table(self) -> None:
        self.run_worker(self.action_refresh)

    async def action_create_host(self) -> None:
        self.app.push_screen(HostCreateModal(self._refresh_table))

    async def action_edit_host(self) -> None:
        address = self._selected_address
        if not address:
            return
        self.app.push_screen(HostEditModal(address, self._refresh_table))

    async def key_enter(self) -> None:
        await self.action_edit_host()

    async def action_delete_host(self) -> None:
        address = self._selected_address
        if not address:
            return
        self.app.push_screen(HostDeleteModal(address, self._refresh_table))


class ConfigContent(Static):
    """Config tab — manage key/value settings."""

    BINDINGS = [
        Binding("e", "edit_config", "Edit"),
        Binding("n", "new_config", "New"),
        Binding("d", "delete_config", "Delete"),
        Binding("r", "refresh", "Refresh"),
    ]

    def compose(self) -> ComposeResult:
        yield DataTable(id="config-table")

    async def on_mount(self) -> None:
        self.table = self.query_one("#config-table", DataTable)
        self.table.cursor_type = "row"
        await self.action_refresh()

    async def action_refresh(self) -> None:
        self.table.clear(columns=True)
        cfg = list_config()
        if not cfg:
            self.table.add_columns("  (no config)  ")
            return

        items = list(cfg.items())
        columns = ["#", "Key", "Value"]
        data = [[str(idx), k, v] for idx, (k, v) in enumerate(items, 1)]
        col_widths = [max(len(columns[i]), max(len(row[i]) for row in data)) for i in range(len(columns))]
        self.table.add_columns(*[_center(c, col_widths[i]) for i, c in enumerate(columns)])
        for row, (k, _) in zip(data, items):
            self.table.add_row(*[_center(cell, col_widths[i]) for i, cell in enumerate(row)], key=k)

    @property
    def _selected_key(self) -> str | None:
        if not self.table.columns:
            return None
        try:
            return self.table.coordinate_to_cell_key(Coordinate(self.table.cursor_row, 1)).row_key.value
        except Exception:
            return None

    def _refresh_table(self) -> None:
        self.run_worker(self.action_refresh)

    async def action_edit_config(self) -> None:
        key = self._selected_key
        if not key:
            return
        value = list_config().get(key, "")
        self.app.push_screen(ConfigEditModal(key, value, self._refresh_table))

    async def key_enter(self) -> None:
        await self.action_edit_config()

    async def action_new_config(self) -> None:
        self.app.push_screen(ConfigNewModal(self._refresh_table))

    async def action_delete_config(self) -> None:
        key = self._selected_key
        if not key:
            return
        self.app.push_screen(ConfigDeleteModal(key, self._refresh_table))


# ── application ───────────────────────────────────────────────────────────────


class AdminApp(App):
    """Hystron Admin — terminal management interface."""

    TITLE = "Hystron Admin"
    SUB_TITLE = "terminal management interface"

    CSS = """
Screen {
    background: $surface;
}

TabbedContent, TabPane {
    height: 1fr;
}

DataTable {
    height: 1fr;
}

UsersContent, TrafficContent, HostsContent, ConfigContent {
    height: 1fr;
}

/* ── modal overlay ─────────────────────────────────────── */
BaseModal > Container {
    align: center middle;
}

.modal-box-qr {
    background: $panel;
    border: round $primary;
    padding: 1 2;
    width: 70;
    height: auto;
    max-height: 90vh;
}

.qr-display {
    text-align: center;
    width: 1fr;
    padding: 1 0;
}

.qr-url {
    text-align: center;
    color: $text-muted;
    width: 1fr;
    margin-bottom: 1;
    overflow: hidden;
}

.modal-box {
    background: $panel;
    border: round $primary;
    padding: 1 2;
    width: 66;
    height: auto;
}

.modal-box-delete {
    background: $panel;
    border: round $error;
    padding: 1 2;
    width: 52;
    height: auto;
}

.modal-title {
    text-style: bold;
    margin-bottom: 1;
    text-align: center;
    width: 1fr;
}

.input-container {
    height: auto;
    margin-bottom: 1;
}

.input-container Input {
    margin-bottom: 1;
}

.switch-row {
    height: 3;
    align: left middle;
}

.switch-row Label {
    width: auto;
    margin-right: 1;
    padding-top: 1;
}

.button-row {
    height: auto;
    align: center middle;
    margin-top: 1;
}

.button-row Button {
    margin: 0 1;
}

.modal-box-devices {
    background: $panel;
    border: round $primary;
    padding: 1 2;
    width: 100;
    height: 22;
}

.devices-table {
    height: 1fr;
}
"""

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("1", "switch_tab('users')", "Users", show=False),
        Binding("2", "switch_tab('traffic')", "Traffic", show=False),
        Binding("3", "switch_tab('hosts')", "Hosts", show=False),
        Binding("4", "switch_tab('config')", "Config", show=False),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent(initial="users"):
            with TabPane("Users [1]", id="users"):
                yield UsersContent()
            with TabPane("Traffic [2]", id="traffic"):
                yield TrafficContent()
            with TabPane("Hosts [3]", id="hosts"):
                yield HostsContent()
            with TabPane("Config [4]", id="config"):
                yield ConfigContent()
        yield Footer()

    def action_switch_tab(self, tab_id: str) -> None:
        self.query_one(TabbedContent).active = tab_id


# ── entrypoint ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    AdminApp().run()
