#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME="hystron"
IMAGE_NAME="hystron"
DATA_DIR="/var/lib/hystron"
PUBLIC_PORT="${PUBLIC_PORT:-9000}"
INTERNAL_PORT="${INTERNAL_PORT:-9001}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()    { echo -e "${GREEN}[hystron]${NC} $*"; }
warn()    { echo -e "${YELLOW}[hystron]${NC} $*"; }
error()   { echo -e "${RED}[hystron]${NC} $*" >&2; exit 1; }

# ── root check ────────────────────────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
    error "Please run as root (sudo $0)"
fi

# ── install docker ────────────────────────────────────────────────────────────
install_docker() {
    if command -v docker &>/dev/null; then
        info "Docker already installed: $(docker --version)"
        return
    fi
    info "Installing Docker..."
    if command -v apt-get &>/dev/null; then
        apt-get update -qq
        apt-get install -y -qq ca-certificates curl gnupg lsb-release
        install -m 0755 -d /etc/apt/keyrings
        curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
            | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
        chmod a+r /etc/apt/keyrings/docker.gpg
        echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
            > /etc/apt/sources.list.d/docker.list
        apt-get update -qq
        apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    elif command -v yum &>/dev/null || command -v dnf &>/dev/null; then
        PKG=$(command -v dnf &>/dev/null && echo dnf || echo yum)
        $PKG install -y yum-utils
        yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
        $PKG install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    else
        info "Using Docker convenience install script..."
        curl -fsSL https://get.docker.com | sh
    fi
    systemctl enable --now docker
    info "Docker installed: $(docker --version)"
}

# ── build image ───────────────────────────────────────────────────────────────
build_image() {
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    info "Building image '${IMAGE_NAME}' from ${SCRIPT_DIR}..."
    docker build -t "${IMAGE_NAME}:latest" "${SCRIPT_DIR}"
    info "Image built successfully."
}

# ── prepare data dir ──────────────────────────────────────────────────────────
prepare_data_dir() {
    mkdir -p "${DATA_DIR}"
    info "Data directory: ${DATA_DIR}"
}

# ── stop old container ────────────────────────────────────────────────────────
stop_existing() {
    if docker inspect "${CONTAINER_NAME}" &>/dev/null; then
        warn "Stopping and removing existing container '${CONTAINER_NAME}'..."
        docker stop "${CONTAINER_NAME}" &>/dev/null || true
        docker rm   "${CONTAINER_NAME}" &>/dev/null || true
    fi
}

# ── run container ─────────────────────────────────────────────────────────────
run_container() {
    info "Starting container '${CONTAINER_NAME}'..."
    docker run -d \
        --name "${CONTAINER_NAME}" \
        --restart unless-stopped \
        -p "${PUBLIC_PORT}:9000" \
        -p "${INTERNAL_PORT}:9001" \
        -v "${DATA_DIR}:/var/lib/hystron" \
        "${IMAGE_NAME}:latest"
    info "Container started. Public port: ${PUBLIC_PORT}, Internal port: ${INTERNAL_PORT}"
}

# ── install cli wrapper ───────────────────────────────────────────────────────
install_cli() {
    cat > /usr/local/bin/hystron <<'WRAPPER'
#!/usr/bin/env bash
exec docker exec -i hystron hystron "$@"
WRAPPER
    chmod +x /usr/local/bin/hystron
    info "CLI installed at /usr/local/bin/hystron"
}

# ── main ──────────────────────────────────────────────────────────────────────
main() {
    info "=== Hystron Installer ==="

    install_docker
    prepare_data_dir
    build_image
    stop_existing
    run_container
    install_cli

    echo
    info "=== Installation complete ==="
    info "  Public  (auth/sub) → http://0.0.0.0:${PUBLIC_PORT}"
    info "  Internal (API)     → http://127.0.0.1:${INTERNAL_PORT}"
    info "  Data dir           → ${DATA_DIR}"
    echo
    info "  Manage with:  hystron --help"
    info "  View logs:    docker logs -f ${CONTAINER_NAME}"
}

main "$@"
