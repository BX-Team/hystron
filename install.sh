#!/usr/bin/env bash
# Hystron installation script
# Usage: sudo bash install.sh [--mirror <url>] [install|uninstall|update]
set -euo pipefail

REPO_URL="https://github.com/BX-Team/hystron"
IMAGE_NAME="ghcr.io/bx-team/hystron"
INSTALL_DIR="/opt/hystron"
DATA_DIR="/var/lib/hystron"

# PyPI mirror — override via --mirror flag or PYPI_MIRROR env var.
# Example: --mirror https://mirrors.aliyun.com/pypi/simple/
PYPI_MIRROR="${PYPI_MIRROR:-}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[hystron]${NC} $*"; }
warn()  { echo -e "${YELLOW}[hystron]${NC} $*"; }
error() { echo -e "${RED}[hystron]${NC} $*" >&2; exit 1; }

# ── root check ────────────────────────────────────────────────────────────────
require_root() {
    if [[ $EUID -ne 0 ]]; then
        error "This script must be run as root (sudo $0)."
    fi
}

# ── docker compose command detection ─────────────────────────────────────────
detect_compose() {
    if command -v docker &>/dev/null && docker compose version &>/dev/null 2>&1; then
        COMPOSE_CMD="docker compose"
    elif command -v docker-compose &>/dev/null; then
        COMPOSE_CMD="docker-compose"
    else
        COMPOSE_CMD=""
    fi
}

# ── docker install ────────────────────────────────────────────────────────────
install_docker() {
    if command -v docker &>/dev/null; then
        info "Docker already installed: $(docker --version)"
        return
    fi
    info "Installing Docker..."
    curl -fsSL https://get.docker.com | sh
    systemctl enable --now docker
    info "Docker installed: $(docker --version)"
}

# ── mode selection ────────────────────────────────────────────────────────────
choose_mode() {
    echo ""
    echo "Select installation mode:"
    echo "  1) control  — full panel (TUI/CLI, user management, subscriptions)"
    echo "  2) node     — xray-core agent (connects to a Control server)"
    echo ""
    read -rp "Mode [1-2] (default: 1): " mode_choice
    case "${mode_choice:-1}" in
        1) HYSTRON_MODE="control" ;;
        2) HYSTRON_MODE="node" ;;
        *) warn "Invalid choice, using control mode."; HYSTRON_MODE="control" ;;
    esac
    info "Mode: ${HYSTRON_MODE}"
}

# ── node config ───────────────────────────────────────────────────────────────
choose_node_config() {
    echo ""
    info "Node mode: this server will connect to a Control server and run xray-core."
    echo ""
    read -rp "Control URL (e.g. http://ctrl.example.com:9002): " HYSTRON_CONTROL_URL
    [[ -z "${HYSTRON_CONTROL_URL:-}" ]] && error "Control URL is required for node mode."
    read -rp "Node token (from Control: hystron nodes create <address>): " HYSTRON_NODE_TOKEN
    [[ -z "${HYSTRON_NODE_TOKEN:-}" ]] && error "Node token is required for node mode."
}

# ── version selection ─────────────────────────────────────────────────────────
choose_version() {
    echo ""
    echo "Select the Hystron version to install:"
    echo "  1) latest  (default)"
    echo "  2) Specific version (e.g. 1.2.3)"
    echo ""
    read -rp "Enter choice [1-2] (default: 1): " ver_choice
    ver_choice="${ver_choice:-1}"

    case "$ver_choice" in
        1) HYSTRON_VERSION="latest" ;;
        2)
            read -rp "Enter version (e.g. 1.2.3): " custom_ver
            HYSTRON_VERSION="${custom_ver:-latest}"
            ;;
        *) warn "Invalid choice, using latest."; HYSTRON_VERSION="latest" ;;
    esac
    info "Using image: ${IMAGE_NAME}:${HYSTRON_VERSION}"
}

# ── port selection (control only) ─────────────────────────────────────────────
choose_ports() {
    echo ""
    read -rp "Public (auth/subscription) port [9000]: " PUBLIC_PORT
    PUBLIC_PORT="${PUBLIC_PORT:-9000}"
    read -rp "Internal (admin API) port [9001]: " INTERNAL_PORT
    INTERNAL_PORT="${INTERNAL_PORT:-9001}"
    read -rp "Node API port [9002]: " NODE_API_PORT
    NODE_API_PORT="${NODE_API_PORT:-9002}"
}

# ── .env generation ───────────────────────────────────────────────────────────
setup_env() {
    local env_file="${INSTALL_DIR}/.env"
    if [[ -f "$env_file" ]]; then
        warn ".env already exists — skipping generation. Edit ${env_file} if needed."
        return
    fi

    info "Generating .env..."

    if [[ "${HYSTRON_MODE}" == "control" ]]; then
        cat > "$env_file" <<EOF
HYSTRON_VERSION=${HYSTRON_VERSION:-latest}
HYSTRON_MODE=control

PUBLIC_PORT=${PUBLIC_PORT:-9000}
INTERNAL_PORT=${INTERNAL_PORT:-9001}
NODE_API_PORT=${NODE_API_PORT:-9002}

HYST_DB_PATH=/var/lib/hystron/app.db
EOF
    else
        cat > "$env_file" <<EOF
HYSTRON_VERSION=${HYSTRON_VERSION:-latest}
HYSTRON_MODE=node

HYSTRON_CONTROL_URL=${HYSTRON_CONTROL_URL:-}
HYSTRON_NODE_TOKEN=${HYSTRON_NODE_TOKEN:-}

# Path to your hand-crafted xray-core config template (with "clients": [])
XRAY_TEMPLATE_PATH=/var/lib/hystron/xray-template.json
# Path where the panel writes the final config (with clients filled in)
XRAY_CONFIG_PATH=/var/lib/hystron/xray.json
EOF
    fi

    chmod 600 "$env_file"
    info ".env created at ${env_file}"
}

# ── fetch compose file ────────────────────────────────────────────────────────
fetch_compose() {
    mkdir -p "$INSTALL_DIR"
    info "Downloading docker-compose.yml to ${INSTALL_DIR}..."
    curl -fsSL "${REPO_URL}/raw/refs/heads/master/docker-compose.yml" \
        -o "${INSTALL_DIR}/docker-compose.yml"
    info "docker-compose.yml downloaded."
}

# ── cli install (control only) ────────────────────────────────────────────────
install_cli() {
    local cli_venv="${INSTALL_DIR}/.cli-venv"
    local cli_dir="${INSTALL_DIR}/cli"

    if ! command -v python3 &>/dev/null; then
        warn "python3 not found — skipping host CLI install. Use 'docker exec -i hystron hystron' instead."
        return
    fi
    local pyver
    pyver=$(python3 -c 'import sys; print(sys.version_info >= (3, 12))')
    if [[ "$pyver" != "True" ]]; then
        warn "Python 3.12+ is required for the host CLI. Skipping."
        return
    fi

    info "Downloading CLI module..."
    mkdir -p "${cli_dir}"
    for f in __init__.py __main__.py main.py; do
        curl -fsSL "${REPO_URL}/raw/refs/heads/master/cli/${f}" -o "${cli_dir}/${f}"
    done

    info "Creating CLI virtual environment at ${cli_venv}..."
    python3 -m venv "${cli_venv}"

    local pip_args=()
    if [[ -n "${PYPI_MIRROR:-}" ]]; then
        local mirror_host
        mirror_host=$(python3 -c "from urllib.parse import urlparse; print(urlparse('${PYPI_MIRROR}').netloc)")
        pip_args+=(--index-url "${PYPI_MIRROR}" --trusted-host "${mirror_host}")
        info "Using PyPI mirror: ${PYPI_MIRROR}"
    fi

    "${cli_venv}/bin/pip" install --quiet --upgrade pip "${pip_args[@]}"
    "${cli_venv}/bin/pip" install --quiet "${pip_args[@]}" httpx typer rich

    cat > /usr/local/bin/hystron <<WRAPPER
#!/usr/bin/env bash
# Hystron CLI — talks to the container via HTTP (no docker exec overhead)
export PYTHONPATH="${INSTALL_DIR}"
export HYSTRON_API="\${HYSTRON_API:-http://127.0.0.1:${INTERNAL_PORT:-9001}}"
exec "${cli_venv}/bin/python" -m cli "\$@"
WRAPPER
    chmod +x /usr/local/bin/hystron
    info "CLI installed at /usr/local/bin/hystron"
}

remove_cli() {
    rm -f /usr/local/bin/hystron
    rm -rf "${INSTALL_DIR}/.cli-venv" "${INSTALL_DIR}/cli"
    info "CLI removed."
}

# ── install ───────────────────────────────────────────────────────────────────
do_install() {
    require_root
    install_docker
    detect_compose
    [[ -z "$COMPOSE_CMD" ]] && error "Docker Compose not found. Please install Docker with Compose support."

    choose_mode
    fetch_compose
    choose_version

    if [[ "${HYSTRON_MODE}" == "control" ]]; then
        choose_ports
    else
        choose_node_config
    fi

    setup_env

    info "Preparing data directory ${DATA_DIR}..."
    mkdir -p "${DATA_DIR}/templates" "${DATA_DIR}/tls"

    info "Pulling image ${IMAGE_NAME}:${HYSTRON_VERSION}..."
    docker pull "${IMAGE_NAME}:${HYSTRON_VERSION}"

    info "Starting Hystron (${HYSTRON_MODE} mode)..."
    $COMPOSE_CMD -f "${INSTALL_DIR}/docker-compose.yml" --env-file "${INSTALL_DIR}/.env" up -d

    echo "${HYSTRON_VERSION}" > "${INSTALL_DIR}/.hystron_version"
    echo "${HYSTRON_MODE}" > "${INSTALL_DIR}/.hystron_mode"

    if [[ "${HYSTRON_MODE}" == "control" ]]; then
        install_cli

        local server_ip
        server_ip=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{print $7; exit}') \
            || server_ip=$(hostname -I 2>/dev/null | awk '{print $1}') \
            || server_ip="localhost"

        echo ""
        info "=== Control installation complete ==="
        info "  Public  (auth/sub) → http://${server_ip}:${PUBLIC_PORT:-9000}"
        info "  Internal (API)     → http://127.0.0.1:${INTERNAL_PORT:-9001}"
        info "  Node API           → http://${server_ip}:${NODE_API_PORT:-9002}"
        info "  Data dir           → ${DATA_DIR}"
        echo ""
        info "  Next: create a node with:  hystron nodes create <address>"
        info "  Manage: hystron --help"
        info "  Logs:   docker logs -f hystron"
    else
        echo ""
        info "=== Node installation complete ==="
        info "  Control URL  → ${HYSTRON_CONTROL_URL}"
        info "  Data dir     → ${DATA_DIR}"
        echo ""
        warn "  Next step: create your xray-core config template at:"
        warn "    ${DATA_DIR}/xray-template.json"
        echo ""
        info "  The template is a normal xray-core config. Set 'clients: []' in"
        info "  every inbound — the panel will fill it automatically."
        info "  All other settings (TLS, Reality, ports, routing) you control."
        echo ""
        info "  After creating the template, restart:"
        info "    docker restart hystron"
        echo ""
        info "  Logs: docker logs -f hystron"
    fi
}

# ── uninstall ─────────────────────────────────────────────────────────────────
do_uninstall() {
    require_root
    detect_compose
    warn "Stopping and removing Hystron..."
    if [[ -n "$COMPOSE_CMD" && -f "${INSTALL_DIR}/docker-compose.yml" ]]; then
        $COMPOSE_CMD -f "${INSTALL_DIR}/docker-compose.yml" down -v 2>/dev/null || true
    else
        docker stop hystron 2>/dev/null || true
        docker rm   hystron 2>/dev/null || true
    fi
    rm -rf "$INSTALL_DIR"
    remove_cli
    info "Hystron uninstalled. Data in ${DATA_DIR} was preserved."
}

# ── update ────────────────────────────────────────────────────────────────────
do_update() {
    require_root
    detect_compose
    [[ -z "$COMPOSE_CMD" ]] && error "Docker Compose not found."
    [[ ! -d "$INSTALL_DIR" ]] && error "Hystron is not installed at ${INSTALL_DIR}."

    fetch_compose

    local saved_version="latest"
    [[ -f "${INSTALL_DIR}/.hystron_version" ]] && saved_version=$(cat "${INSTALL_DIR}/.hystron_version")

    info "Pulling image ${IMAGE_NAME}:${saved_version}..."
    docker pull "${IMAGE_NAME}:${saved_version}"

    $COMPOSE_CMD -f "${INSTALL_DIR}/docker-compose.yml" --env-file "${INSTALL_DIR}/.env" up -d

    local saved_mode="control"
    [[ -f "${INSTALL_DIR}/.hystron_mode" ]] && saved_mode=$(cat "${INSTALL_DIR}/.hystron_mode")

    if [[ "$saved_mode" == "control" && -d "${INSTALL_DIR}/cli" ]]; then
        info "Updating CLI module..."
        local cli_dir="${INSTALL_DIR}/cli"
        for f in __init__.py __main__.py main.py; do
            curl -fsSL "${REPO_URL}/raw/refs/heads/master/cli/${f}" -o "${cli_dir}/${f}"
        done
    fi

    info "Hystron updated to ${saved_version}."
}

# ── entrypoint ────────────────────────────────────────────────────────────────
usage() {
    echo "Usage: $0 [--mirror <pypi-mirror-url>] {install|uninstall|update}"
    echo ""
    echo "Options:"
    echo "  --mirror <url>   PyPI mirror to use for pip (e.g. https://mirrors.aliyun.com/pypi/simple/)"
    echo "                   Can also be set via the PYPI_MIRROR environment variable."
    exit 1
}

# Parse flags before the subcommand
while [[ $# -gt 0 ]]; do
    case "$1" in
        --mirror)
            [[ -z "${2:-}" ]] && error "--mirror requires a URL argument."
            PYPI_MIRROR="$2"
            shift 2
            ;;
        --mirror=*)
            PYPI_MIRROR="${1#--mirror=}"
            shift
            ;;
        install|uninstall|update)
            break
            ;;
        -h|--help)
            usage
            ;;
        *)
            error "Unknown argument: $1. Run $0 --help for usage."
            ;;
    esac
done

case "${1:-install}" in
    install)   do_install ;;
    uninstall) do_uninstall ;;
    update)    do_update ;;
    *)         usage ;;
esac
