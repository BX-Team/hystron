<div align="center">

# Hystron
Multi-protocol proxy management panel with CLI, TUI and REST API

[![Chat on Discord](https://cdn.jsdelivr.net/npm/@intergrav/devins-badges@3/assets/cozy/social/discord-plural_vector.svg)](https://discord.gg/qNyybSSPm5)
[![github](https://cdn.jsdelivr.net/npm/@intergrav/devins-badges@3/assets/cozy/available/github_vector.svg)](https://github.com/BX-Team/hystron)
</div>

## ⚙️ Features

### Core
- **User management** — traffic limits, expiry dates, device (HWID) limits
- **Multi-server** — manage any number of backends; multiple hosts on the same IP are supported
- **Tag system** — assign tags to hosts and users; tagged hosts are only served to users sharing at least one tag
- **Traffic monitoring** — polls servers periodically, tracks usage per user (hour / day / week / month / total), auto-kicks users who exceed their daily limit
- **Device tracking** — devices register on first subscription fetch; auth blocks unregistered devices when a limit is set
- **CLI, TUI and REST API** — manage everything from the terminal or programmatically
- **Schema migrations** — database schema managed with Alembic; upgrades run automatically on startup

### Multi-protocol subscriptions
Subscriptions are auto-formatted based on the detected client (Sing-Box, Clash, Xray, plain URI list); the browser gets an HTML dashboard with a QR code.

All formats support all three protocols:

| Protocol | Host type | Notes |
|---|---|---|
| Hysteria2 | `hysteria2` | Native Hysteria2 backend via HTTP API |
| VLESS + REALITY | `hystron_node` | xray-core node managed via gRPC |
| Trojan | `hystron_node` | xray-core node managed via gRPC |

Subscription parameters (SNI, public key, short ID, fingerprint, flow, etc.) are configured per-host via the `sub_params` query string field.

### hystron-node
`hystron_node` hosts connect to a companion [**hystron-node**](https://github.com/BX-Team/hystron-node) process running xray-core. The panel communicates with each node over gRPC and:
- Syncs users (add / remove) on create, edit, and delete
- Polls traffic stats and resets counters after each poll
- Queries node status (xray version, uptime)

### Customizable templates
Subscription templates (Sing-Box JSON, Clash YAML, Xray JSON, HTML index) can be overridden globally via `templates_dir` or per-format via dedicated config keys.

## 📥 Quick Install

```bash
curl -fsSL https://raw.githubusercontent.com/BX-Team/hystron/master/install.sh -o /tmp/hystron.sh \
  && sudo bash /tmp/hystron.sh install
```

After installation, get started by running:

```bash
hystron --help
```

## 🔧 Other Commands

```bash
# Update
hystron update

# Uninstall
curl -fsSL https://raw.githubusercontent.com/BX-Team/hystron/master/install.sh -o /tmp/hystron.sh \
  && sudo bash /tmp/hystron.sh uninstall
```

## ⚖️ License ![Static Badge](https://img.shields.io/badge/license-MIT-lightgreen)

Hystron is licensed under the MIT License. You can find the license [here](LICENSE).
