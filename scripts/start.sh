#!/bin/sh
# Entrypoint de produção (Render): aplica as migrações e sobe a API.
set -e

alembic upgrade head

exec gunicorn app.main:app \
    --workers "${WEB_CONCURRENCY:-1}" \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind "0.0.0.0:${PORT:-8000}" \
    --forwarded-allow-ips "*" \
    --timeout 120 \
    --max-requests 1000 \
    --max-requests-jitter 100 \
    --access-logfile - \
    --error-logfile - \
    --log-level info
