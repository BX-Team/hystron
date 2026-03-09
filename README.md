<div align="center">

# Hystron
Simple CLI, TUI and API management panel for [Hysteria2](https://v2.hysteria.network) proxy servers

[![Chat on Discord](https://cdn.jsdelivr.net/npm/@intergrav/devins-badges@3/assets/cozy/social/discord-plural_vector.svg)](https://discord.gg/qNyybSSPm5)
[![github](https://cdn.jsdelivr.net/npm/@intergrav/devins-badges@3/assets/cozy/available/github_vector.svg)](https://github.com/BX-Team/hystron)
</div>

## ⚙️ Features
- **User management** — traffic limits, expiry dates, device (HWID) limits
- **Multi-server** — manage any number of Hysteria2 backends
- **Smart subscriptions** — auto-detects client type (Sing-Box, Clash, Xray, plain) and serves the right format; browser gets an HTML dashboard with QR code
- **Traffic monitoring** — polls servers periodically, tracks usage per user (hour / day / week / month / total), auto-kicks users who exceed their limit
- **Device tracking** — devices register on first subscription fetch; auth blocks unregistered devices when the limit is set
- **CLI, TUI and REST API** — manage everything from the terminal or programmatically

## 📥 Quick Install

```bash
curl -fsSL https://raw.githubusercontent.com/BX-Team/hystron/master/install.sh | sudo bash -s install
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
curl -fsSL https://raw.githubusercontent.com/BX-Team/hystron/master/install.sh | sudo bash -s uninstall
```

## ⚖️ License ![Static Badge](https://img.shields.io/badge/license-MIT-lightgreen)

Hystron is licensed under the MIT License. You can find the license [here](LICENSE).
