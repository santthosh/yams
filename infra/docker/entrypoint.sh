#!/bin/sh
set -eu
case "${1:-}" in
  migrate) exec python /app/container_bootstrap.py ;;
  api) exec python -m uvicorn backend.api.main:app --host 0.0.0.0 --port 8000 ;;
  worker) exec python -m backend.jobs.worker ;;
  *) exec "$@" ;;
esac
