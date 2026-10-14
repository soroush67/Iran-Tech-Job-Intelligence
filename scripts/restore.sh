#!/usr/bin/env bash
# Restore a dump made by backup.sh into the running stack.
#   ./scripts/restore.sh backups/jobintel-20261014-033000.dump
# The app services are stopped during the restore so nothing writes meanwhile.
set -euo pipefail
cd "$(dirname "$0")/.."
file="${1:?usage: restore.sh backups/<file>.dump}"
[ -f "$file" ] || { echo "no such file: $file" >&2; exit 1; }
case "$file" in backups/*) ;; *) echo "the dump must be inside ./backups (mounted into the postgres container)" >&2; exit 1;; esac
read -r -p "This REPLACES all data in the database with $file. Type 'restore' to continue: " ok
[ "$ok" = "restore" ] || { echo "aborted"; exit 1; }
docker compose stop backend worker scheduler telegram-bot
docker compose exec -T postgres pg_restore --list "/$file" > /dev/null
docker compose exec -T postgres sh -c 'dropdb -U "$POSTGRES_USER" --if-exists "${POSTGRES_DB}_restore_old" &&
  psql -U "$POSTGRES_USER" -d postgres -c "ALTER DATABASE \"$POSTGRES_DB\" RENAME TO \"${POSTGRES_DB}_restore_old\"" &&
  createdb -U "$POSTGRES_USER" "$POSTGRES_DB"'
if docker compose exec -T postgres sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --exit-on-error "/'"$file"'"'; then
  docker compose exec -T postgres sh -c 'dropdb -U "$POSTGRES_USER" "${POSTGRES_DB}_restore_old"'
  echo "restore ok"
else
  echo "restore FAILED - putting the previous database back" >&2
  docker compose exec -T postgres sh -c 'dropdb -U "$POSTGRES_USER" --if-exists "$POSTGRES_DB" &&
    psql -U "$POSTGRES_USER" -d postgres -c "ALTER DATABASE \"${POSTGRES_DB}_restore_old\" RENAME TO \"$POSTGRES_DB\""'
  docker compose up -d backend worker scheduler telegram-bot
  exit 1
fi
docker compose up -d backend worker scheduler telegram-bot   # backend runs migrations on start
