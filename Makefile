# Lệnh chung (08 mục 8). Owner: Dev 2.
.PHONY: up down migrate seed test lint

up:
	docker compose up -d

down:
	docker compose down

migrate:
	cd backend && alembic upgrade head

seed:
	cd backend && python -m app.seed.generate_data

test:
	cd backend && pytest

lint:
	cd backend && ruff check . && black --check . && mypy app/engine && lint-imports
