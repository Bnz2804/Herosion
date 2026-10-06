#!/usr/bin/env bash
# One-command local stack: agent service (:8000) + web API (:5000). Needs Postgres (DATABASE_URL) and a model.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] && set -a && . ./.env && set +a
[ -f data/extension.sqlite ] || extension-agent seed
trap 'kill 0' EXIT
extension-agent serve --port 8000 &
( cd web && pnpm install --frozen-lockfile --ignore-scripts && pnpm --filter @workspace/db run push \
  && pnpm --filter @workspace/api-server run build && PORT=${PORT:-5000} node artifacts/api-server/dist/index.mjs ) &
( cd web && PORT=5173 BASE_PATH=/ pnpm --filter @workspace/extension-backlog run dev ) &
wait
