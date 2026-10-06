#!/bin/sh
set -e
echo "Applying database schema (non-destructive: drizzle push refuses data-loss changes without a TTY)..."
pnpm --filter @workspace/db run push
exec node --enable-source-maps artifacts/api-server/dist/index.mjs
