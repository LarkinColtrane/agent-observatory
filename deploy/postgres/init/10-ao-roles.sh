#!/bin/sh
# Agent Observatory PostgreSQL role bootstrap (ADR-0005 §3, AO-P1-004).
#
# Creates or converges (idempotent):
#   ao_migrator  LOGIN, owns the database and schema "public"; used ONLY by
#                Alembic (AO_MIGRATION_DATABASE_URL). DDL role.
#   ao_app       LOGIN NOINHERIT, member of no role; DML only
#                (SELECT/INSERT/UPDATE/DELETE on tables, USAGE/SELECT on
#                sequences) in schema "public"; no CREATE on any schema, no
#                TEMP, owns nothing. Used by the app (AO_DATABASE_URL).
# Tables the migrator creates later in "public" become usable by ao_app through
# ALTER DEFAULT PRIVILEGES FOR ROLE ao_migrator. PUBLIC loses CONNECT/TEMP on
# the maintenance databases (postgres, template1) and EXECUTE on the
# large-object creation functions in the application database.
# The last step stores a completion marker (a comment on the database); the
# compose healthcheck runs `10-ao-roles.sh --check`, which succeeds only if that
# marker and both roles exist.
#
# Password checks (exactly these, nothing more): AO_PG_MIGRATION_PASSWORD,
# AO_PG_APP_PASSWORD and the superuser password (POSTGRES_PASSWORD, else
# PGPASSWORD) must each be set, match ^[A-Za-z0-9_-]{16,}$ (URL-safe, at least
# 16 characters), not contain "change" in any letter case (the placeholders in
# compose.env.example do), and all three must differ. Values are read by psql's
# \getenv (never on a command line), never echoed, and statement logging is
# disabled for this session.
#
# Runs as a PostgreSQL superuser, either
#   - automatically, from /docker-entrypoint-initdb.d in the postgres image
#     (first start of an EMPTY data directory). If that first init fails, the
#     image does not retry it on restart: remove the volume
#     (`docker compose down -v`) and start again. The healthcheck stays
#     unhealthy in that state, so dependants never start.
#   - explicitly, e.g. in CI against a service container:
#       docker exec -i -e AO_PG_APP_PASSWORD -e AO_PG_MIGRATION_PASSWORD \
#         <container> sh -s < deploy/postgres/init/10-ao-roles.sh
#     or with any psql 16 client: PGHOST=... PGUSER=postgres PGPASSWORD=... sh 10-ao-roles.sh
# The file must stay executable (the image sources non-executable *.sh files).
#
# Optional: AO_PG_DATABASE (default "observatory"). The superuser is PGUSER,
# else POSTGRES_USER (set by the image's entrypoint), else "postgres".
set -eu
set +x
LC_ALL=C
export LC_ALL

die() { echo "10-ao-roles.sh: $*" >&2; exit 1; }

AO_PG_DATABASE="${AO_PG_DATABASE:-observatory}"
case "$AO_PG_DATABASE" in
  *[!a-z0-9_]* | "") die "AO_PG_DATABASE must match [a-z0-9_]+" ;;
esac
export AO_PG_DATABASE

PGUSER="${PGUSER:-${POSTGRES_USER:-postgres}}"
export PGUSER

PSQL="psql -X -q -v ON_ERROR_STOP=1 --no-password"
MARKER="ao-bootstrap: complete v1"

if [ "${1:-}" = "--check" ]; then
  # Exit 0 only if the last bootstrap run completed. No passwords needed.
  ok="$($PSQL -tA --dbname=postgres -v marker="$MARKER" <<'SQL'
\getenv ao_db AO_PG_DATABASE
SELECT 1 FROM pg_database d
 WHERE d.datname = :'ao_db'
   AND shobj_description(d.oid, 'pg_database') = :'marker'
   AND EXISTS (SELECT FROM pg_roles WHERE rolname = 'ao_app')
   AND EXISTS (SELECT FROM pg_roles WHERE rolname = 'ao_migrator');
SQL
)" || exit 1
  [ "$ok" = "1" ] || exit 1
  exit 0
fi

check_password() {
  # $1 = variable name, $2 = value. The value is inspected, never printed.
  [ -n "$2" ] || die "$1 is not set"
  case "$2" in
    *[!A-Za-z0-9_-]*) die "$1 must contain only A-Z a-z 0-9 _ -" ;;
    *[Cc][Hh][Aa][Nn][Gg][Ee]*) die "$1 still holds a placeholder (contains 'change')" ;;
  esac
  [ "${#2}" -ge 16 ] || die "$1 must be at least 16 characters"
}

check_password AO_PG_MIGRATION_PASSWORD "${AO_PG_MIGRATION_PASSWORD:-}"
check_password AO_PG_APP_PASSWORD "${AO_PG_APP_PASSWORD:-}"
if [ -n "${POSTGRES_PASSWORD:-}" ]; then
  check_password POSTGRES_PASSWORD "$POSTGRES_PASSWORD"
  super_pw_name=POSTGRES_PASSWORD
  super_pw="$POSTGRES_PASSWORD"
else
  check_password "POSTGRES_PASSWORD (or PGPASSWORD)" "${PGPASSWORD:-}"
  super_pw_name=PGPASSWORD
  super_pw="$PGPASSWORD"
fi
[ "$AO_PG_MIGRATION_PASSWORD" != "$AO_PG_APP_PASSWORD" ] \
  || die "AO_PG_APP_PASSWORD and AO_PG_MIGRATION_PASSWORD must differ"
[ "$super_pw" != "$AO_PG_APP_PASSWORD" ] && [ "$super_pw" != "$AO_PG_MIGRATION_PASSWORD" ] \
  || die "$super_pw_name must differ from the role passwords"
unset super_pw

# --- cluster level: roles, memberships, databases (maintenance DB) ---
$PSQL --dbname=postgres <<'SQL'
SET log_statement = 'none';
SET log_min_error_statement = 'panic';
SET log_min_duration_statement = -1;
\getenv ao_db AO_PG_DATABASE
\getenv mig_pw AO_PG_MIGRATION_PASSWORD
\getenv app_pw AO_PG_APP_PASSWORD

-- Re-runs: clear the completion marker first, so a failure below leaves it unset.
SELECT format('COMMENT ON DATABASE %I IS NULL', :'ao_db')
  WHERE EXISTS (SELECT FROM pg_database WHERE datname = :'ao_db') \gexec

SELECT 'CREATE ROLE ao_migrator' WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'ao_migrator') \gexec
SELECT 'CREATE ROLE ao_app' WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'ao_app') \gexec
ALTER ROLE ao_migrator WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS INHERIT;
ALTER ROLE ao_app WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT;
ALTER ROLE ao_migrator WITH PASSWORD :'mig_pw';
ALTER ROLE ao_app WITH PASSWORD :'app_pw';
\unset mig_pw
\unset app_pw

-- ao_app is a member of no role (so it can never SET ROLE to the migrator).
SELECT format('REVOKE %I FROM ao_app', g.rolname)
  FROM pg_auth_members m
  JOIN pg_roles g ON g.oid = m.roleid
  JOIN pg_roles r ON r.oid = m.member
 WHERE r.rolname = 'ao_app' \gexec

SELECT format('CREATE DATABASE %I OWNER ao_migrator', :'ao_db')
  WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = :'ao_db') \gexec
SELECT format('ALTER DATABASE %I OWNER TO ao_migrator', :'ao_db') \gexec
SELECT format('REVOKE ALL ON DATABASE %I FROM PUBLIC', :'ao_db') \gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO ao_app', :'ao_db') \gexec

-- Maintenance databases: superusers only.
REVOKE CONNECT, TEMPORARY ON DATABASE postgres FROM PUBLIC;
REVOKE CONNECT, TEMPORARY ON DATABASE template1 FROM PUBLIC;
SQL

# --- database level: schema privileges, default privileges, marker ---
$PSQL --dbname="$AO_PG_DATABASE" -v marker="$MARKER" <<'SQL'
SET log_statement = 'none';
SET log_min_error_statement = 'panic';
\getenv ao_db AO_PG_DATABASE
ALTER SCHEMA public OWNER TO ao_migrator;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON SCHEMA public FROM ao_app;
GRANT USAGE ON SCHEMA public TO ao_app;

-- Large objects live outside schemas; only superusers may create them.
REVOKE EXECUTE ON FUNCTION lo_creat(integer), lo_create(oid), lo_from_bytea(oid, bytea),
  lo_import(text), lo_import(text, oid) FROM PUBLIC;

-- Objects the migrator creates in "public" from now on: DML only for the app.
ALTER DEFAULT PRIVILEGES FOR ROLE ao_migrator IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ao_app;
ALTER DEFAULT PRIVILEGES FOR ROLE ao_migrator IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO ao_app;
-- Existing objects in "public" (none on a fresh database; makes re-runs converge).
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ao_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ao_app;

-- Completion marker: written last, checked by `10-ao-roles.sh --check`.
SELECT format('COMMENT ON DATABASE %I IS %L', :'ao_db', :'marker') \gexec
SQL

echo "10-ao-roles.sh: roles ao_migrator (DDL) and ao_app (DML) ready on database $AO_PG_DATABASE" >&2
