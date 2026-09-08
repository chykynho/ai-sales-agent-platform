#!/bin/sh
set -e

is_enabled() {
  case "${1:-}" in
    1|true|TRUE|yes|YES|on|ON) return 0 ;;
    *) return 1 ;;
  esac
}

if is_enabled "${RUN_MIGRATIONS:-false}"; then
  echo "[entrypoint] Applying database migrations..."
  alembic upgrade head
else
  echo "[entrypoint] Database migrations skipped (RUN_MIGRATIONS=false)."
fi

if is_enabled "${RUN_BOOTSTRAP:-false}"; then
  echo "[entrypoint] Running idempotent bootstrap..."
  python -m scripts.bootstrap
else
  echo "[entrypoint] Bootstrap skipped (RUN_BOOTSTRAP=false)."
fi

echo "[entrypoint] Starting application..."
exec "$@"
