<div align="center">

# Hystron
Simple CLI, TUI and API management panel for [Hysteria2](https://v2.hysteria.network) proxy servers

[![Chat on Discord](https://cdn.jsdelivr.net/npm/@intergrav/devins-badges@3/assets/cozy/social/discord-plural_vector.svg)](https://discord.gg/qNyybSSPm5)
[![github](https://cdn.jsdelivr.net/npm/@intergrav/devins-badges@3/assets/cozy/available/github_vector.svg)](https://github.com/BX-Team/hystron)
</div>

## ⚙️ Features
- We are thinking what to put here.

## 📥 Quick Install

The install script handles everything: installs Docker and other things that I don't think you'll be interested in.

```bash
curl -fsSL https://raw.githubusercontent.com/BX-Team/hystron/refs/heads/master/install.sh -o /tmp/hystron.sh \
  && sudo bash /tmp/hystron.sh install
```

Follow the interactive prompts. Once the installation is complete, you will see this message:

```
  === Installation complete ===
  Public  (auth/sub) → http://YOUR_SERVER:9000
  Internal (API)     → http://127.0.0.1:9001
  Data dir           → /var/lib/hystron
  Templates override → /var/lib/hystron/templates

  Manage: hystron --help
  Logs:   docker logs -f hystron
```

You can edit Hystron via CLI commands or using TUI. Choose whatever you like!

To update later:

```bash
hystron update
```

To uninstall:

```bash
curl -fsSL https://raw.githubusercontent.com/BX-Team/hystron/refs/heads/master/install.sh -o /tmp/hystron.sh \
  && sudo bash /tmp/hystron.sh uninstall
```

## ⚖️ License ![Static Badge](https://img.shields.io/badge/license-MIT-lightgreen)

Hystron is licensed under the MIT License. You can find the license [here](LICENSE).
