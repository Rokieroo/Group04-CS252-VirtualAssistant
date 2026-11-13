-- Least-privilege roles for one PostgreSQL 16 database (issue #18).
--
--   pathly_owner  owns the schema and runs `alembic upgrade head` (DDL).
--   pathly_app    is what the API and the worker log in as: read and write rows,
--                 never create, alter or drop tables.
--
-- Run once as a superuser (or the managed-DB admin), passing passwords as psql
-- variables so they never land in a file or in shell history of the server:
--
--   psql "$ADMIN_URL" -v ON_ERROR_STOP=1 \
--        -v db_name=pathly -v owner_password="$OWNER_PW" -v app_password="$APP_PW" \
--        -f db/postgres/roles.sql
--
-- Re-running is safe: roles are created only when missing and passwords updated.

SELECT format('CREATE ROLE pathly_owner LOGIN PASSWORD %L', :'owner_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pathly_owner') \gexec
SELECT format('CREATE ROLE pathly_app LOGIN PASSWORD %L', :'app_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pathly_app') \gexec

ALTER ROLE pathly_owner WITH LOGIN PASSWORD :'owner_password' NOSUPERUSER NOCREATEDB NOCREATEROLE;
ALTER ROLE pathly_app   WITH LOGIN PASSWORD :'app_password'   NOSUPERUSER NOCREATEDB NOCREATEROLE;
-- One idle-in-transaction session must not hold row locks forever.
ALTER ROLE pathly_app SET idle_in_transaction_session_timeout = '60s';
ALTER ROLE pathly_app SET statement_timeout = '30s';

SELECT format('CREATE DATABASE %I OWNER pathly_owner ENCODING ''UTF8'' TEMPLATE template0', :'db_name')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'db_name') \gexec

\connect :db_name

-- Nobody but the owner creates objects in public; the app only uses it.
REVOKE ALL ON DATABASE :"db_name" FROM PUBLIC;
GRANT CONNECT, TEMPORARY ON DATABASE :"db_name" TO pathly_app;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
ALTER SCHEMA public OWNER TO pathly_owner;
GRANT USAGE ON SCHEMA public TO pathly_app;

-- Tables that already exist (re-run after migrations) ...
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO pathly_app;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO pathly_app;
-- ... and every table a later migration creates as pathly_owner.
ALTER DEFAULT PRIVILEGES FOR ROLE pathly_owner IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO pathly_app;
ALTER DEFAULT PRIVILEGES FOR ROLE pathly_owner IN SCHEMA public
    GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO pathly_app;
