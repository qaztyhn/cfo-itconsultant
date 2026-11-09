#!/usr/bin/env bash
# Explicitly destroy ONLY a dedicated, disposable local cfo-demo-* Compose project.
# No auto-reset during setup or smoke. This removes that project's named volumes.
set -euo pipefail

if [[ "${1:-}" != "--confirm-disposable-data-loss" ||
      "${DEMO_DISPOSABLE:-}" != "1" ||
      "${APP_ENV:-}" != "test" ||
      ! "${COMPOSE_PROJECT_NAME:-}" =~ ^cfo-demo-[a-zA-Z0-9_-]+$ ]]; then
  echo "REFUSED: only an explicitly confirmed disposable cfo-demo-* test project can be reset." >&2
  exit 2
fi
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
docker compose --project-name "$COMPOSE_PROJECT_NAME" down --volumes --remove-orphans
echo "The explicitly selected disposable Compose project was removed. Other projects were not targeted."
echo "Locally exported demo-fixtures.json and reports remain unchanged; inspect and remove manually if appropriate."
