-include .env
export

.PHONY: install up down partenaire web scenarios epreuve ctl test cov fmt lint typecheck

install:
	uv sync

up:
	docker compose up -d --build

down:
	docker compose down

partenaire:
	uv run python -m external_agent --port 8100

web:
	uv run uvicorn kaldera.web:app --port 8000 --reload

scenarios:
	uv run python -m kaldera.cli eval/scenarios.jsonl $(ARGS)

epreuve:
	uv run python scripts/epreuve.py --repetitions 3 --sortie docs/epreuve-resultats.md

ctl:
	uv run python scripts/partner_ctl.py $(ARGS)

test:
	uv run pytest -v

cov:
	uv run pytest --cov=kaldera --cov-report=term-missing --cov-report=html

fmt:
	uv run ruff format .
	uv run ruff check --fix .

lint:
	uv run ruff check .

typecheck:
	uv run mypy src
