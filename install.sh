#!/usr/bin/env bash
# Hystron installation script
# Usage: sudo bash install.sh [install|uninstall|update]
set -euo pipefail

REPO_URL="https://github.com/BX-Team/hystron"
IMAGE_NAME="ghcr.io/bx-team/hystron"
INSTALL_DIR="/opt/hystron"
DATA_DIR="/var/lib/hystron"

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

# ── cli wrapper ───────────────────────────────────────────────────────────────
install_cli() {
    cat > /usr/local/bin/hystron <<'WRAPPER'
#!/usr/bin/env bash
exec docker exec -i hystron hystron "$@"
WRAPPER
    chmod +x /usr/local/bin/hystron
    info "CLI installed at /usr/local/bin/hystron"
}

remove_cli() {
    rm -f /usr/local/bin/hystron
    info "CLI removed."
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

    info "Hystron updated to ${saved_version}."
}

# ── entrypoint ────────────────────────────────────────────────────────────────
usage() {
    echo "Usage: $0 {install|uninstall|update}"
    exit 1
}

case "${1:-install}" in
    install)   do_install ;;
    uninstall) do_uninstall ;;
    update)    do_update ;;
    *)         usage ;;
esac
