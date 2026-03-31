<div align="center">

# Hystron

Multi-protocol proxy management panel with TUI, CLI and REST API

[![Chat on Discord](https://cdn.jsdelivr.net/npm/@intergrav/devins-badges@3/assets/cozy/social/discord-plural_vector.svg)](https://discord.gg/qNyybSSPm5)
[![github](https://cdn.jsdelivr.net/npm/@intergrav/devins-badges@3/assets/cozy/available/github_vector.svg)](https://github.com/BX-Team/hystron)

</div>

## Features

- Manage users with traffic limits, expiry dates and per-device (HWID) caps
- Multiple backends — Hysteria2 servers and [hystron-node](https://github.com/BX-Team/hystron-node) (xray-core over gRPC)
- Tag-based host filtering — assign tags to hosts and users; a host is only served to users sharing at least one tag
- Subscriptions auto-detect the client app and return Sing-Box, Clash or plain URI list; the browser gets an HTML dashboard with a QR code
- Per-user traffic stats: hour / day / week / month / total; auto-kick on limit exceeded
- TUI for interactive management, CLI for scripting, REST API for integrations
- Database migrations run automatically on startup (Alembic)

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/BX-Team/hystron/master/install.sh -o /tmp/hystron.sh \
  && sudo bash /tmp/hystron.sh install
```

After installation, get started by running:

```bash
hystron --help
```

## Update / Uninstall

```bash
hystron update
```

```bash
curl -fsSL https://raw.githubusercontent.com/BX-Team/hystron/master/install.sh -o /tmp/hystron.sh \
  && sudo bash /tmp/hystron.sh uninstall
```

## Protocols

| Protocol | Host type |
|---|---|
| Hysteria2 | `hysteria2` |
| VLESS + REALITY | `hystron_node` |
| Trojan | `hystron_node` |

`hystron_node` hosts connect to a companion [hystron-node](https://github.com/BX-Team/hystron-node) process running xray-core. The panel syncs users over gRPC and polls traffic stats from each node.

## License ![Static Badge](https://img.shields.io/badge/license-MIT-lightgreen)

Licensed under the [MIT License](LICENSE).
