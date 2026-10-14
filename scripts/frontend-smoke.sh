#!/usr/bin/env bash
# Runs frontend/tests/smoke.mjs in the official Playwright image against the running stack.
set -euo pipefail
cd "$(dirname "$0")/.."
env_get() { grep -E "^$1=" .env | head -1 | cut -d= -f2- | sed -e "s/^\"//" -e "s/\"$//"; }
ADMIN_EMAIL="$(env_get ADMIN_EMAIL)"; ADMIN_PASSWORD="$(env_get ADMIN_PASSWORD)"; HTTPS_PORT="$(env_get HTTPS_PORT)"
export ADMIN_EMAIL ADMIN_PASSWORD
PORT="${HTTPS_PORT:-8443}"
docker run --rm --network host -v "$PWD/frontend/tests:/tests:ro" -w /work \
  -e BASE_URL="https://localhost:$PORT" -e ADMIN_EMAIL -e ADMIN_PASSWORD \
  mcr.microsoft.com/playwright:v1.52.0-noble \
  sh -c 'npm init -y >/dev/null && npm i --silent playwright@1.52.0 >/dev/null 2>&1 && cp /tests/smoke.mjs . && node smoke.mjs'
