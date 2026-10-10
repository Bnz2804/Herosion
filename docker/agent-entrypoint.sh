#!/bin/sh
set -e
chown -R app /data                      # named volumes start root-owned
if [ "${FORCE_RESEED:-false}" = "true" ] && [ -f "$EXTENSION_AGENT_DB" ]; then
  echo "FORCE_RESEED=true: replacing the database with fresh SYNTHETIC data (remove this variable afterwards)."
  rm -f "$EXTENSION_AGENT_DB" "$EXTENSION_AGENT_DB-wal" "$EXTENSION_AGENT_DB-shm"
fi
if [ ! -f "$EXTENSION_AGENT_DB" ]; then
  if [ "${SEED_SYNTHETIC:-true}" = "true" ]; then
    echo "No database found: seeding SYNTHETIC demo data."
    gosu app extension-agent seed
  else
    echo "No database at $EXTENSION_AGENT_DB and SEED_SYNTHETIC=false. Import data first (extension-agent import-plots ...)." >&2
    exit 1
  fi
fi
exec gosu app uvicorn africa_extension_agent.service:app --host 0.0.0.0 --port 8000
