#!/bin/sh
# Add the source database without changing CFO data. Also safe on an existing volume.
set -eu
psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --set=ON_ERROR_STOP=1 \
  --set=source_db="$SOURCE_DB_NAME" <<'SQL'
SELECT format('CREATE DATABASE %I', :'source_db')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'source_db')
\gexec
SQL
