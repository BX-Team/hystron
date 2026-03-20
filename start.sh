#!/usr/bin/env bash
set -euo pipefail

python -m alembic upgrade head
exec python main.py
