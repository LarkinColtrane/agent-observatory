# Developer entry points (ADR-0005 §1). CI runs the same commands
# (.github/workflows/governance.yml); keep the two in step.
# Requires: uv, Python 3.12, Node 22 + npm, Docker with Compose v2.

PYTHON ?= python3.12
BACKEND := backend
FRONTEND := frontend
UV_RUN := cd $(BACKEND) && .venv/bin

.PHONY: help setup check governance backend-check frontend-check test test-integration up down

help:
	@echo "setup             install backend (uv.lock) and frontend (package-lock.json) deps"
	@echo "check             governance + backend + frontend static checks and unit tests"
	@echo "test-integration  backend integration tests (needs AO_TEST_* URLs; see compose.env.example)"
	@echo "up / down         start / stop the local stack (needs compose.env)"

setup:
	cd $(BACKEND) && uv sync --locked --python $(PYTHON)
	cd $(FRONTEND) && npm ci

governance:
	$(PYTHON) -I scripts/check-governance.py
	$(PYTHON) -I scripts/check-artifacts.py
	$(PYTHON) -I -m unittest discover -s tests/governance -t . -q

backend-check:
	$(UV_RUN)/ruff check .
	$(UV_RUN)/ruff format --check .
	$(UV_RUN)/mypy
	$(UV_RUN)/lint-imports
	$(UV_RUN)/pytest tests/unit -q
	$(UV_RUN)/bandit -q -r src

frontend-check:
	cd $(FRONTEND) && npm run lint && npm run typecheck && npm run format:check && npm test -- --run

check: governance backend-check frontend-check

test: backend-check

test-integration:
	cd $(BACKEND) && AO_REQUIRE_INTEGRATION=1 .venv/bin/pytest -m integration -q

up:
	docker compose --env-file compose.env up -d --build --wait

down:
	docker compose --env-file compose.env down -v
