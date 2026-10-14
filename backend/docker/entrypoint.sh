#!/bin/bash
# One image, several roles: api | worker | scheduler | bot | certs | migrate
set -e
role="${1:-api}"
case "$role" in
  api)
    alembic upgrade head
    python -m app.bootstrap
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*' \
         --workers "${API_WORKERS:-2}" --no-server-header
    ;;
  worker)
    # Two processes: a long crawl must never delay notifications or AI analysis.
    # If either exits, the container exits and Docker restarts it.
    rq worker --url "$REDIS_URL" --name "collect-$(hostname)" collect &
    rq worker --url "$REDIS_URL" --name "fast-$(hostname)" --with-scheduler notify analyze &
    wait -n
    exit 1
    ;;
  scheduler)
    exec python -m app.scheduler
    ;;
  bot)
    exec python -m app.bot.main
    ;;
  certs)
    exec python -m app.certs
    ;;
  migrate)
    alembic upgrade head && python -m app.bootstrap
    ;;
  *)
    exec "$@"
    ;;
esac
