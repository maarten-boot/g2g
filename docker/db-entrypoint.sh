#!/usr/bin/env bash
# Wraps the postgres image entrypoint: refuse to start after a failed dump restore (docker/db-restore.sh).
# Otherwise the restart would skip the init scripts and run with an empty or half restored database,
# and the web container would migrate that.
set -euo pipefail

if [ -e "${PGDATA:-/var/lib/postgresql/data}/g2g-restore-failed" ]; then
    echo "g2g: the database dump restore failed on the first start (see the earlier db log)." >&2
    echo "g2g: fix the dump in DB_DUMP_DIR, then remove the volume and start again:" >&2
    echo "g2g:   docker compose down -v && docker compose up -d" >&2
    exit 1
fi

exec docker-entrypoint.sh "$@"
