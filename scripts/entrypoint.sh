#!/bin/sh
set -e

echo "[entrypoint] Applying database migrations..."
alembic upgrade head

echo "[entrypoint] Running idempotent bootstrap..."
python -m scripts.bootstrap

echo "[entrypoint] Starting application..."
exec "$@"
