.PHONY: install dev test lint types record

install:
	uv sync --frozen
	pnpm install --frozen-lockfile

# Starts the API on :8000 and the web app on :3000; Ctrl-C stops both.
dev:
	@trap 'kill 0' INT TERM EXIT; \
	uv run uvicorn tandem_api.main:app --reload --reload-dir packages --reload-dir services --port 8000 & \
	pnpm --filter web dev & \
	wait

test:
	uv run pytest
	pnpm -r test

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy
	pnpm -r lint
	pnpm -r typecheck

types:
	uv run python scripts/export_schema.py
	./scripts/gen_types.sh

record:
	@echo "TODO: record a run's event log into data/runs/"
