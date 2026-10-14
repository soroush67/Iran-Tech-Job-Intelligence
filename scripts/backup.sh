#!/usr/bin/env bash
# PostgreSQL backup (custom format, compressed) with retention.
#   ./scripts/backup.sh                 # -> backups/jobintel-YYYYmmdd-HHMMSS.dump
#   KEEP=14 ./scripts/backup.sh         # keep the newest 14 dumps (default 14)
# Cron example (daily 03:30):
#   30 3 * * * cd /path/to/Iran_Tech_Job_Intelligence && ./scripts/backup.sh >> backups/backup.log 2>&1
set -euo pipefail
cd "$(dirname "$0")/.."
KEEP="${KEEP:-14}"
mkdir -p backups
ts="$(date +%Y%m%d-%H%M%S)"
name="jobintel-$ts.dump"
# pg_dump runs inside the postgres container and writes to the bind-mounted ./backups
docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -Z 6 -f /backups/'"$name"
# verify the archive is readable before trusting it
docker compose exec -T postgres pg_restore --list "/backups/$name" > /dev/null
size="$(du -h "backups/$name" | cut -f1)"
echo "backup ok: backups/$name ($size)"
# retention
ls -1t backups/jobintel-*.dump 2>/dev/null | tail -n +"$((KEEP + 1))" | while read -r old; do
  rm -f -- "$old" && echo "removed old backup $old"
done
