ARG PYTHON_VERSION=3.12
ARG APP_VERSION=dev

FROM ghcr.io/astral-sh/uv:python${PYTHON_VERSION}-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /build

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

ADD . /build
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev


FROM python:${PYTHON_VERSION}-slim-bookworm

COPY --from=builder /build /code
WORKDIR /code

ARG APP_VERSION=dev
ENV PATH="/code/.venv/bin:$PATH" \
    HYST_DB_PATH=/var/lib/hystron/app.db \
    APP_VERSION=${APP_VERSION}

RUN mkdir -p /var/lib/hystron

COPY start.sh /code/start.sh
RUN chmod +x /code/start.sh

EXPOSE 9000 9001

ENTRYPOINT ["/code/start.sh"]
