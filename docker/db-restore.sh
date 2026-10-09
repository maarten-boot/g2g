#!/usr/bin/env bash
# Restore a database dump into a NEW database (postgres runs /docker-entrypoint-initdb.d only when
# the pgdata volume is empty). The web container applies the pending migrations when it starts.
#
# Put exactly one dump in the dump directory (compose: DB_DUMP_DIR, default docker/dump), named *.dump,
# *.sql or *.sql.gz; the format is recognised from the content, not the name:
#   custom format, preferred:  pg_dump -Fc -d <db> -f g2g.dump
#   plain SQL, made with:      pg_dump --clean --if-exists --no-owner --no-privileges -d <db> -f g2g.sql
#   (gzipped plain SQL works too)
# No dump: the database starts empty and migrate creates the schema.
#
# On a failed restore the data directory is already initialised, so postgres would skip this script on
# the next start and run with an empty database. We leave a marker that docker/db-entrypoint.sh refuses
# to start with, until the volume is removed (docker compose down -v).

RESTORE_FAILED_MARKER="$PGDATA/g2g-restore-failed"

# a plain SQL dump is run as is: refuse the options that cannot work on a new database, with the fix
check_plain_sql() {
    local f=$1
    shift
    local -a cat_dump=("$@")
    local ok=0

    if "${cat_dump[@]}" | grep -qE '^DROP ' && ! "${cat_dump[@]}" | grep -qE '^DROP .* IF EXISTS '; then
        echo "db-restore: $f was made with --clean but without --if-exists: its DROPs fail on a new database" >&2
        ok=1
    fi

    local role
    for role in $("${cat_dump[@]}" | grep -oE ' OWNER TO [^;]+;' | sed -E 's/ OWNER TO "?([^";]+)"?;/\1/' | sort -u); do
        if [ -z "$(psql --no-psqlrc -At --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
            -c "SELECT 1 FROM pg_roles WHERE rolname = '$role'")" ]; then
            echo "db-restore: $f sets owner $role, a role that does not exist here" >&2
            ok=1
        fi
    done

    if [ $ok -ne 0 ]; then
        echo "db-restore: dump again with: pg_dump -Fc ... (preferred), or" >&2
        echo "db-restore:   pg_dump --clean --if-exists --no-owner --no-privileges ..." >&2
    fi
    return $ok
}

restore_dump() {
    local dir=/dump
    local -a files
    shopt -s nullglob
    files=("$dir"/*.dump "$dir"/*.sql "$dir"/*.sql.gz)
    shopt -u nullglob

    if [ ${#files[@]} -eq 0 ]; then
        echo "db-restore: no dump in $dir, starting with an empty database"
        return 0
    fi
    if [ ${#files[@]} -gt 1 ]; then
        echo "db-restore: more than one dump in $dir, keep only one: ${files[*]}" >&2
        return 1
    fi

    local f=${files[0]}
    local psql=(psql -v ON_ERROR_STOP=1 --no-psqlrc --quiet --username "$POSTGRES_USER" --dbname "$POSTGRES_DB")
    local -a cat_dump=(cat "$f")
    if gzip -t "$f" 2>/dev/null; then
        cat_dump=(gunzip -c "$f")
    fi

    if [ "$("${cat_dump[@]}" | head -c 5)" = "PGDMP" ]; then
        echo "db-restore: restoring $f (custom format) into $POSTGRES_DB"
        # owners/grants of the source database do not exist here
        (set -o pipefail && "${cat_dump[@]}" | pg_restore --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
            --no-owner --no-privileges --clean --if-exists --exit-on-error) || return 1
    else
        echo "db-restore: restoring $f (plain SQL) into $POSTGRES_DB"
        check_plain_sql "$f" "${cat_dump[@]}" || return 1
        (set -o pipefail && "${cat_dump[@]}" | "${psql[@]}") || return 1
    fi
    echo "db-restore: done; the web container applies the pending migrations when it starts"
}

if ! restore_dump; then
    touch "$RESTORE_FAILED_MARKER"
    echo "db-restore: FAILED; the database will not start until the volume is removed (docker compose down -v)" >&2
    false # fail the postgres init
fi
