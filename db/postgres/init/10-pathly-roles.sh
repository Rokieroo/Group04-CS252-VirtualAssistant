#!/bin/sh
# Runs once, when the postgres container starts on an empty volume
# (/docker-entrypoint-initdb.d). Creates the owner and app roles from roles.sql.
set -eu
: "${PATHLY_DB:?set PATHLY_DB}"
: "${PATHLY_OWNER_PASSWORD:?set PATHLY_OWNER_PASSWORD}"
: "${PATHLY_APP_PASSWORD:?set PATHLY_APP_PASSWORD}"
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  -v db_name="$PATHLY_DB" \
  -v owner_password="$PATHLY_OWNER_PASSWORD" \
  -v app_password="$PATHLY_APP_PASSWORD" \
  -f /pathly/roles.sql
