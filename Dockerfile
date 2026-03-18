ARG PYTHON_VERSION=3.12
ARG XRAY_VERSION=26.2.6

FROM ghcr.io/astral-sh/uv:python${PYTHON_VERSION}-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    libc6-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

ADD . /build
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev


FROM python:${PYTHON_VERSION}-slim-bookworm

ARG XRAY_VERSION

COPY --from=builder /build /code
WORKDIR /code

ENV PATH="/code/.venv/bin:$PATH" \
    HYST_DB_PATH=/var/lib/hystron/app.db \
    HYSTRON_MODE=control \
    XRAY_TEMPLATE_PATH=/var/lib/hystron/xray-template.json \
    XRAY_CONFIG_PATH=/var/lib/hystron/xray.json

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*

RUN ARCH=$(uname -m) && \
    case "$ARCH" in \
        x86_64)  XRAY_ARCH="64" ;; \
        aarch64) XRAY_ARCH="arm64-v8a" ;; \
        armv7l)  XRAY_ARCH="arm32-v7a" ;; \
        *)       XRAY_ARCH="64" ;; \
    esac && \
    curl -fsSL "https://github.com/XTLS/Xray-core/releases/download/v${XRAY_VERSION}/Xray-linux-${XRAY_ARCH}.zip" \
        -o /tmp/xray.zip && \
    unzip /tmp/xray.zip xray -d /usr/local/bin && \
    chmod +x /usr/local/bin/xray && \
    rm /tmp/xray.zip

RUN mkdir -p /var/lib/hystron/templates \
    && chmod +x /code/start.sh \
    && ln -s /code/.venv/bin/hystron /usr/local/bin/hystron

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD /bin/sh -c \
        'if [ "${HYSTRON_MODE}" = "node" ]; then pgrep xray > /dev/null; \
         else curl -f http://localhost:9000/health; fi || exit 1'

ENTRYPOINT ["/code/start.sh"]
