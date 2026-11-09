#!/usr/bin/env bash
# Prepare an explicitly disposable Swedish synthetic demo from existing seeds.
# Does not reset data, enable external jobs, claim D7 compliance or approve plans.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [[ "${APP_ENV:-}" != "test" || "${DEMO_DISPOSABLE:-}" != "1" ||
      "${APP_NOW:-}" != "2026-11-04T10:05:00+01:00" ]]; then
  echo "BLOCKED: export APP_ENV=test, DEMO_DISPOSABLE=1 and approved APP_NOW." >&2
  exit 2
fi
if [[ ! "${COMPOSE_PROJECT_NAME:-}" =~ ^cfo-demo-[a-zA-Z0-9_-]+$ ]]; then
  echo "BLOCKED: set a dedicated COMPOSE_PROJECT_NAME beginning cfo-demo-." >&2
  exit 2
fi
for key in POSTGRES_PASSWORD JWT_SECRET SOURCE_SE_API_KEY SOURCE_SE_DATABASE_URL DATABASE_URL SEED_DEMO_PASSWORD INTERNAL_TICK_KEY; do
  if [[ -z "${!key:-}" ]]; then
    echo "BLOCKED: missing environment variable $key (no secret values printed)." >&2
    exit 2
  fi
done
command -v docker >/dev/null || { echo "BLOCKED: Docker Compose is required." >&2; exit 2; }
docker compose config --quiet
docker compose up -d --build postgres
# Existing named volumes might not have the Source database; idempotent.
docker compose exec -T postgres sh /docker-entrypoint-initdb.d/10-source-db.sh
docker compose up -d --build source-se mailpit cfo-api cfo-web
docker compose exec -T source-se python -m app.init_db
docker compose exec -T cfo-api alembic upgrade head

# The approved generator returns 2 because it deliberately cannot declare
# D7/golden/E2E success. That return code does not undo the seeded references.
set +e
docker compose exec -T cfo-api python -m app.seed.generate_data --manifest /tmp/cfo-demo-fixtures.json
seed_status=$?
set -e
if [[ "$seed_status" -ne 2 ]]; then
  echo "BLOCKED: reference generator did not return its documented partial-demo status (2)." >&2
  exit 2
fi

tmpfile="$(mktemp "$ROOT/.demo-manifest.XXXXXXXX")"
trap 'rm -f "$tmpfile"' EXIT
docker compose cp cfo-api:/tmp/cfo-demo-fixtures.json "$tmpfile" >/dev/null
if [[ -e "$ROOT/demo-fixtures.json" ]]; then
  cmp -s "$tmpfile" "$ROOT/demo-fixtures.json" || {
    echo "BLOCKED: local manifest conflicts; refusing to overwrite." >&2
    exit 2
  }
else
  install -m 600 "$tmpfile" "$ROOT/demo-fixtures.json"
fi
docker compose cp "$ROOT/demo-fixtures.json" source-se:/tmp/cfo-demo-fixtures.json >/dev/null
docker compose exec -T source-se python -m app.seed_demo --manifest /tmp/cfo-demo-fixtures.json
# The M0 market seed deliberately leaves Source URL unset; bind only this
# approved local adapter, refusing any preexisting incompatible configuration.
docker compose exec -T -e DEMO_DISPOSABLE=1 cfo-api python -m app.demo_configure

# Reference reads only. No automatic order routing; missing stock scope
# cannot be sidestepped by injecting a CFO stock balance.
for entity in customers products inbound fleet; do
  docker compose exec -T -e DEMO_DISPOSABLE=1 cfo-api python -m app.demo_ingest "$entity" || {
    echo "BLOCKED: $entity reference sync incomplete; inspect its scoped sync-run." >&2
    exit 2
  }
done

echo "Synthetic seed and reference imports completed. This is NOT an approved planning/driver E2E PASS."
echo "Run: python3 tools/demo_smoke.py --report demo-smoke-results.json"
echo "Only on this disposable environment, to test missing routing: python3 tools/demo_smoke.py --exercise-sync"
echo "Do not infer regulated D7 evidence from the synthetic driver history."
