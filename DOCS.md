# Hystron Configuration Reference

All configuration is stored as key-value pairs in the database. You can manage it via:

- **TUI**: Config tab (press `n` to create, `e` to edit, `d` to delete)
- **CLI**: `hystron config list`, `hystron config set <key> <value>`
- **API**: `GET/PUT/DELETE /api/config/{key}`

---

## General

| Key | Default | Description |
|-----|---------|-------------|
| `base_url` | `""` | Public base URL of the Hystron instance (e.g. `https://vpn.example.com`). Used to build subscription links. |
| `profile_name_tpl` | `Hystron for {uname}` | Template for the subscription profile name shown in clients. `{uname}` is replaced with the username. |
| `subscription_path` | `/sub` | URL path prefix for the public subscription endpoint. |
| `support_url` | `https://discord.gg/qNyybSSPm5` | Support link included in subscription metadata. |
| `announce` | `""` | Announcement text shown to users in the subscription page. Empty = no announcement. |
| `announce-url` | `""` | URL linked from the announcement. |
| `poll_interval` | `600` | How often (in seconds) to poll hosts for traffic stats. Default is 10 minutes. |

## Traffic

| Key | Default | Description |
|-----|---------|-------------|
| `traffic_reset` | `01 00:00` | When to reset the billing period for traffic limits. Format: `DD HH:MM` (UTC). See details below. |

### Traffic reset (`traffic_reset`)

Controls when the monthly billing period starts. The traffic limit for each user is checked against usage accumulated since the last reset point.

**Format:** `DD HH:MM`
- `DD` — day of month (1-28)
- `HH:MM` — time in UTC

**Examples:**

| Value | Meaning |
|-------|---------|
| `01 00:00` | 1st of each month at midnight UTC (default) |
| `01 03:00` | 1st of each month at 03:00 UTC |
| `15 12:00` | 15th of each month at noon UTC |

When the billing period resets, all users that were deactivated due to exceeding their traffic limit are automatically reactivated and re-synced to all nodes.

> **Note:** The day is clamped to 1-28 to avoid issues with months that have fewer than 31 days.

## Access Control

| Key | Default | Description |
|-----|---------|-------------|
| `whitelist_enable` | `false` | Set to `true` to enable IP whitelist for auth and subscription endpoints. |
| `whitelist` | `""` | Space-separated list of allowed IP addresses when whitelist is enabled. |

## Templates

Custom templates let you override the default subscription output for each client format.

| Key | Default | Description |
|-----|---------|-------------|
| `templates_dir` | `/var/lib/hystron/templates` | Base directory for template files. |
| `template_clash` | `""` | Full path to a custom Clash template file. |
| `template_singbox` | `""` | Full path to a custom Sing-Box template file. |
| `template_xray` | `""` | Full path to a custom Xray template file. |
| `template_index` | `""` | Full path to a custom index HTML template. |

### Template resolution order

For each format (e.g. `clash`):

1. Per-format config key (`template_clash`) — if set and file exists, use it.
2. `{templates_dir}/clash.yaml` — if file exists, use it.
3. Bundled default template shipped with Hystron.

### Clash template placeholders

The Clash template (`clash.yaml`) supports these placeholders:

| Placeholder | Replaced with |
|-------------|---------------|
| `{proxies}` | Full YAML block of all proxy definitions. |
| `{proxy_names}` | List of proxy names for use in `proxy-groups`. |

**Example `proxy-groups` section:**

```yaml
proxy-groups:
  - name: PROXY
    type: select
    proxies:
      - {proxy_names}

  - name: Auto
    type: url-test
    url: http://www.gstatic.com/generate_204
    interval: 300
    proxies:
      - {proxy_names}
```

Literal curly braces `{}` in the template are safe and will not cause errors.

## User fields

These are not config keys but per-user settings, managed via the Users tab/CLI:

| Field | Description |
|-------|-------------|
| `traffic_limit` | Monthly traffic limit in bytes. `0` = unlimited. Set in GB via TUI/CLI. |
| `expires_at` | Unix timestamp when the user account expires. `0` = never. |
| `device_limit` | Maximum number of devices. `0` = unlimited. |

## Host fields

Per-host settings, managed via the Hosts tab/CLI:

| Field | Description |
|-------|-------------|
| `host_type` | `hysteria2` (classic Hysteria2 API) or `hystron_node` (gRPC-managed xray-core node). |
| `port` | Public port for client connections. |
| `api_address` | Hysteria2 HTTP API address (e.g. `http://127.0.0.1:9090`). |
| `api_secret` | Hysteria2 API authorization secret. |
| `grpc_address` | gRPC address for hystron-node hosts. |
| `api_key` | API key for hystron-node hosts. |
| `inbound_tag` | Xray inbound tag (hystron-node). |
| `inbound_port` | Xray inbound port, if different from `port`. |
| `protocol` | Protocol for hystron-node: `vless`, `trojan`. |
| `flow` | VLESS flow control (e.g. `xtls-rprx-vision`). |
| `sub_params` | Query string with extra subscription params (e.g. `sni=example.com&pbk=...&sid=...&fp=chrome&security=reality`). |
| `up_mbps` | Upload bandwidth limit in Mbps (Hysteria2 only). |
| `down_mbps` | Download bandwidth limit in Mbps (Hysteria2 only). |
