#!/usr/bin/env bash
# Hystron installation script
# Usage: sudo bash install.sh [--mirror <url>] [install|uninstall|update]
set -euo pipefail

REPO_URL="https://github.com/BX-Team/hystron"
IMAGE_NAME="ghcr.io/bx-team/hystron"
NODE_IMAGE_NAME="ghcr.io/bx-team/hystron-node"
INSTALL_DIR="/opt/hystron"
NODE_INSTALL_DIR="/opt/hystron-node"
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

# ── port selection ────────────────────────────────────────────────────────────
choose_ports() {
    echo ""
    read -rp "Public (auth/subscription) port [9000]: " PUBLIC_PORT
    PUBLIC_PORT="${PUBLIC_PORT:-9000}"
    read -rp "Internal (admin API) port [9001]: " INTERNAL_PORT
    INTERNAL_PORT="${INTERNAL_PORT:-9001}"
}

# ── .env generation ───────────────────────────────────────────────────────────
setup_env() {
    local env_file="${INSTALL_DIR}/.env"
    if [[ -f "$env_file" ]]; then
        warn ".env already exists — skipping generation. Edit ${env_file} if needed."
        return
    fi

    info "Generating .env..."
    cat > "$env_file" <<EOF
HYSTRON_VERSION=${HYSTRON_VERSION:-latest}

PUBLIC_PORT=${PUBLIC_PORT:-9000}
INTERNAL_PORT=${INTERNAL_PORT:-9001}

HYST_DB_PATH=/var/lib/hystron/app.db
EOF
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

# ── cli install ──────────────────────────────────────────────────────────────
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

# ── component selection ───────────────────────────────────────────────────────
choose_component() {
    echo ""
    echo "What would you like to install?"
    echo "  1) Panel  — Hystron management panel (default)"
    echo "  2) Node   — xray-core node (connect to an existing panel)"
    echo ""
    read -rp "Enter choice [1-2] (default: 1): " comp_choice
    comp_choice="${comp_choice:-1}"
    case "$comp_choice" in
        1) INSTALL_COMPONENT="panel" ;;
        2) INSTALL_COMPONENT="node" ;;
        *) warn "Invalid choice, installing panel."; INSTALL_COMPONENT="panel" ;;
    esac
}

# ── node version selection ─────────────────────────────────────────────────────
choose_node_version() {
    echo ""
    echo "Select the hystron-node version to install:"
    echo "  1) latest  (default)"
    echo "  2) Specific version (e.g. 1.2.3)"
    echo ""
    read -rp "Enter choice [1-2] (default: 1): " ver_choice
    ver_choice="${ver_choice:-1}"
    case "$ver_choice" in
        1) HYSTRON_NODE_VERSION="latest" ;;
        2)
            read -rp "Enter version (e.g. 1.2.3): " custom_ver
            HYSTRON_NODE_VERSION="${custom_ver:-latest}"
            ;;
        *) warn "Invalid choice, using latest."; HYSTRON_NODE_VERSION="latest" ;;
    esac
    info "Using image: ${NODE_IMAGE_NAME}:${HYSTRON_NODE_VERSION}"
}

# ── node port selection ────────────────────────────────────────────────────────
choose_node_ports() {
    echo ""
    read -rp "Proxy port (TCP+UDP, exposed to clients) [443]: " PROXY_PORT
    PROXY_PORT="${PROXY_PORT:-443}"
    read -rp "gRPC port (panel → node, keep private!) [10085]: " GRPC_PORT
    GRPC_PORT="${GRPC_PORT:-10085}"
}

# ── node xray config path ─────────────────────────────────────────────────────
choose_node_config() {
    echo ""
    read -rp "Path to your xray config template [/etc/xray/config.json]: " XRAY_CONFIG
    XRAY_CONFIG="${XRAY_CONFIG:-/etc/xray/config.json}"
}

# ── node .env generation ──────────────────────────────────────────────────────
setup_node_env() {
    local env_file="${NODE_INSTALL_DIR}/.env"
    if [[ -f "$env_file" ]]; then
        warn ".env already exists — skipping generation. Edit ${env_file} if needed."
        return
    fi
    info "Generating node .env..."
    cat > "$env_file" <<EOF
HYSTRON_VERSION=${HYSTRON_NODE_VERSION:-latest}
PROXY_PORT=${PROXY_PORT:-443}
GRPC_PORT=${GRPC_PORT:-10085}
XRAY_CONFIG_TEMPLATE=${XRAY_CONFIG:-/etc/xray/config.json}
EOF
    chmod 600 "$env_file"
    info ".env created at ${env_file}"
}

# ── fetch node compose file ───────────────────────────────────────────────────
fetch_node_compose() {
    mkdir -p "$NODE_INSTALL_DIR"
    info "Downloading docker-compose.node.yml to ${NODE_INSTALL_DIR}..."
    curl -fsSL "${REPO_URL}/raw/refs/heads/master/docker-compose.node.yml" \
        -o "${NODE_INSTALL_DIR}/docker-compose.node.yml"
    info "docker-compose.node.yml downloaded."
}

# ── install node ──────────────────────────────────────────────────────────────
do_install_node() {
    require_root
    install_docker
    detect_compose
    [[ -z "$COMPOSE_CMD" ]] && error "Docker Compose not found. Please install Docker with Compose support."

    choose_node_version
    choose_node_ports
    choose_node_config
    fetch_node_compose
    setup_node_env

    local xray_dir
    xray_dir="$(dirname "$XRAY_CONFIG")"
    if [[ ! -f "$XRAY_CONFIG" ]]; then
        warn "Config template not found at ${XRAY_CONFIG}. Create it before starting the node."
        info "Creating directory ${xray_dir}..."
        mkdir -p "$xray_dir"
    fi

    info "Pulling image ${NODE_IMAGE_NAME}:${HYSTRON_NODE_VERSION}..."
    docker pull "${NODE_IMAGE_NAME}:${HYSTRON_NODE_VERSION}"

    info "Starting xray node..."
    $COMPOSE_CMD -f "${NODE_INSTALL_DIR}/docker-compose.node.yml" \
        --env-file "${NODE_INSTALL_DIR}/.env" up -d

    echo "${HYSTRON_NODE_VERSION}" > "${NODE_INSTALL_DIR}/.hystron_version"

    local server_ip
    server_ip=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{print $7; exit}') \
        || server_ip=$(hostname -I 2>/dev/null | awk '{print $1}') \
        || server_ip="localhost"

    echo ""
    info "=== Node installation complete ==="
    info "  Proxy port (clients) → ${server_ip}:${PROXY_PORT:-443}"
    info "  gRPC port  (panel)   → 127.0.0.1:${GRPC_PORT:-10085}"
    info "  Config template      → ${XRAY_CONFIG}"
    info "  Install dir          → ${NODE_INSTALL_DIR}"
    echo ""
    warn "  Do NOT expose the gRPC port (${GRPC_PORT:-10085}) to the public internet."
    info "  Set grpc_address = ${server_ip}:${GRPC_PORT:-10085} in your Hystron panel."
    info "  Logs: docker logs -f xray-node"
}

# ── install ───────────────────────────────────────────────────────────────────
do_install() {
    require_root
    install_docker
    detect_compose
    [[ -z "$COMPOSE_CMD" ]] && error "Docker Compose not found. Please install Docker with Compose support."

    fetch_compose
    choose_version
    choose_ports
    setup_env

    info "Preparing data directory ${DATA_DIR}..."
    mkdir -p "${DATA_DIR}/templates"

    info "Pulling image ${IMAGE_NAME}:${HYSTRON_VERSION}..."
    docker pull "${IMAGE_NAME}:${HYSTRON_VERSION}"

    info "Starting Hystron..."
    $COMPOSE_CMD -f "${INSTALL_DIR}/docker-compose.yml" --env-file "${INSTALL_DIR}/.env" up -d

    echo "${HYSTRON_VERSION}" > "${INSTALL_DIR}/.hystron_version"

    install_cli

    local server_ip
    server_ip=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{print $7; exit}') \
        || server_ip=$(hostname -I 2>/dev/null | awk '{print $1}') \
        || server_ip="localhost"

    echo ""
    info "=== Installation complete ==="
    info "  Public  (auth/sub) → http://${server_ip}:${PUBLIC_PORT:-9000}"
    info "  Internal (API)     → http://127.0.0.1:${INTERNAL_PORT:-9001}"
    info "  Data dir           → ${DATA_DIR}"
    info "  Templates override → ${DATA_DIR}/templates"
    echo ""
    info "  Manage: hystron --help"
    info "  Logs:   docker logs -f hystron"
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

    if [[ -d "${INSTALL_DIR}/cli" ]]; then
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
    install)
        choose_component
        if [[ "$INSTALL_COMPONENT" == "node" ]]; then
            do_install_node
        else
            do_install
        fi
        ;;
    uninstall) do_uninstall ;;
    update)    do_update ;;
    *)         usage ;;
esac
