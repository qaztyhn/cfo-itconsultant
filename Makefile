# Lệnh chung (08 mục 8). Owner: Dev 2.
.PHONY: up down migrate seed test lint config source-db source-init source-test migrate-docker seed-docker

DOCKER ?= docker
PYTHON ?= python
SOURCE_PYTHON ?= python
COMPOSE = $(DOCKER) compose

up:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

migrate:
	$(PYTHON) tools/check_m0_dependencies.py migrations
	cd backend && alembic upgrade head

seed:
	$(PYTHON) tools/check_m0_dependencies.py seed
	cd backend && $(PYTHON) -m app.seed.generate_data

test:
	cd backend && pytest

lint:
	cd backend && ruff check . && black --check . && mypy app/engine && lint-imports

# Existing local targets above remain available with the backend venv activated.
# Container alternatives use the same application commands, including their failures.
config:
	$(COMPOSE) config --quiet

source-db:
	$(COMPOSE) exec -T postgres sh /docker-entrypoint-initdb.d/10-source-db.sh

source-init:
	$(COMPOSE) run --rm --no-deps source-se python -m app.init_db

source-test:
	cd source_system && $(SOURCE_PYTHON) -m pytest tests/unit tests/integration

migrate-docker:
	$(PYTHON) tools/check_m0_dependencies.py migrations
	$(COMPOSE) run --rm --no-deps cfo-api alembic upgrade head

seed-docker:
	$(PYTHON) tools/check_m0_dependencies.py seed
	$(COMPOSE) run --rm --no-deps cfo-api python -m app.seed.generate_data

.PHONY: seed-m0 seed-m0-docker
seed-m0:
	cd backend && $(PYTHON) -m app.seed.m0_accounts

seed-m0-docker:
	$(COMPOSE) run --rm --no-deps cfo-api python -m app.seed.m0_accounts

# Reference data only; full scenario seed remains the separate `seed` target.
.PHONY: seed-reference seed-reference-docker
seed-reference:
	cd backend && $(PYTHON) -m app.seed.reference_demo

seed-reference-docker:
	$(COMPOSE) run --rm --no-deps cfo-api python -m app.seed.reference_demo

.PHONY: source-seed-reference source-seed-reference-docker
source-seed-reference:
	cd source_system && $(SOURCE_PYTHON) -m app.seed_reference

source-seed-reference-docker:
	$(COMPOSE) run --rm --no-deps source-se python -m app.seed_reference
