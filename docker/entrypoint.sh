#!/bin/sh
set -eu

# compose already gates startup on the db healthcheck, so no wait-for loop here.

if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
    echo "==> migrate"
    python manage.py migrate --noinput
fi

if [ "${RUN_COLLECTSTATIC:-1}" = "1" ]; then
    echo "==> collectstatic"
    python manage.py collectstatic --noinput
fi

exec "$@"
