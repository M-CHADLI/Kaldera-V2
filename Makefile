-include .env
export

.PHONY: install up down partenaire scenarios ctl test fmt lint typecheck

install:
	uv sync

up:
	docker compose up -d --build

down:
	docker compose down

partenaire:
	uv run python -m external_agent --port 8100

scenarios:
	uv run python -m kaldera.cli eval/scenarios.jsonl $(ARGS)

ctl:
	uv run python scripts/partner_ctl.py $(ARGS)

test:
	uv run pytest -v

fmt:
	uv run ruff format .
	uv run ruff check --fix .

lint:
	uv run ruff check .

typecheck:
	uv run mypy src
