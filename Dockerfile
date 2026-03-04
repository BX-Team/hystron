ARG PYTHON_VERSION=3.12
ARG APP_VERSION=dev

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

ARG APP_VERSION=dev

COPY --from=builder /build /code
WORKDIR /code

ENV PATH="/code/.venv/bin:$PATH" \
    HYST_DB_PATH=/var/lib/hystron/app.db \
    APP_VERSION=${APP_VERSION}

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /var/lib/hystron \
    && chmod +x /code/start.sh

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:9000/ 2>/dev/null || curl -f http://localhost:9001/ 2>/dev/null || exit 1

EXPOSE 9000 9001

ENTRYPOINT ["/code/start.sh"]
