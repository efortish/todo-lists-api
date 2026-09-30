# Todo Lists API: every workflow in one place. Run `make` to list the targets.
# `make all` goes from a fresh clone to a running, tested stack.

-include .env
export

COMPOSE_DEV := docker compose -f docker-compose.yml -f docker-compose.dev.yml
# The dev container runs as you, so files it writes in the bind mount stay yours.
export HOST_UID := $(shell id -u)
export HOST_GID := $(shell id -g)

VENV     := .venv
PY       := $(VENV)/bin/python
BIN      := $(VENV)/bin
COMPOSE  := docker compose
API_PORT ?= 8000
API_URL  := http://localhost:$(API_PORT)
# Password of the demo accounts created by `make seed`. Override: make seed SEED_PASSWORD=...
SEED_PASSWORD ?= Password123!

.DEFAULT_GOAL := help
.PHONY: help all env install format lint test coverage-html audit check e2e \
        build up down restart logs ps migrate seed psql shell dev dev-logs test-docker \
        run db-up clean nuke

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

all: env install check up ## Everything: .env with fresh secrets, venv, lint, tests, running stack
	@echo ""
	@echo "All set. API docs: $(API_URL)/docs"

# --- Local environment ----------------------------------------------------------------------

env: ## Create .env from .env.example with random secrets (keeps an existing one)
	@test -f .env || { python3 -c "import secrets; \
	pg = secrets.token_urlsafe(24); s = open('.env.example').read(); \
	s = s.replace('POSTGRES_PASSWORD=generate', 'POSTGRES_PASSWORD=' + pg); \
	s = s.replace(':generate@', ':' + pg + '@'); \
	s = s.replace('JWT_SECRET=generate', 'JWT_SECRET=' + secrets.token_urlsafe(48)); \
	open('.env', 'w').write(s)" && chmod 600 .env && echo "Created .env with random secrets"; }

$(VENV)/.installed: pyproject.toml
	python3 -m venv $(VENV)
	$(PY) -m pip install -q --upgrade pip
	$(PY) -m pip install -q -e ".[dev]"
	@touch $@

install: $(VENV)/.installed ## Create the virtualenv and install app + dev dependencies

# --- Quality --------------------------------------------------------------------------------

format: install ## Format code with isort and black
	$(BIN)/isort .
	$(BIN)/black .

lint: install ## Run flake8, ruff and the black/isort checks
	$(BIN)/flake8 .
	$(BIN)/ruff check .
	$(BIN)/black --check .
	$(BIN)/isort --check-only .

test: install ## Run unit + integration tests with coverage (fails under 75%)
	$(BIN)/pytest

coverage-html: install ## Run the tests and write an HTML coverage report to htmlcov/
	$(BIN)/pytest --cov-report=html
	@echo "Open htmlcov/index.html"

audit: install ## Scan installed dependencies for known vulnerabilities (needs network)
	$(BIN)/pip-audit --skip-editable

check: lint test ## Lint and test (what CI would run)

e2e: install ## Hit every endpoint of the running stack over HTTP (make up or make dev first)
	E2E_BASE_URL=$(API_URL) $(BIN)/pytest tests/e2e --no-cov -v

# --- Docker ---------------------------------------------------------------------------------

build: env ## Build the API image
	$(COMPOSE) build

up: env ## Start the production-like stack (PostgreSQL + API), wait until healthy
	$(COMPOSE) up -d --build --wait
	@echo "API: $(API_URL)  |  Swagger: $(API_URL)/docs  |  ReDoc: $(API_URL)/redoc"

down: ## Stop the stack (data is kept)
	$(COMPOSE) down

restart: down up ## Restart the stack

logs: ## Follow API logs (fake emails show up here)
	$(COMPOSE) logs -f api

ps: ## Show the status of the containers
	$(COMPOSE) ps

migrate: ## Apply migrations inside the running API container
	$(COMPOSE) exec api alembic upgrade head

seed: ## Load demo users, lists and tasks into the running stack (safe to repeat)
	$(COMPOSE) exec -e SEED_PASSWORD='$(SEED_PASSWORD)' api python -m app.seed

psql: ## Open a psql shell on the database
	$(COMPOSE) exec db psql -U $${POSTGRES_USER:-todo} -d $${POSTGRES_DB:-todo}

shell: ## Open a shell inside the API container
	$(COMPOSE) exec api sh

# --- Development in Docker (hot reload) ----------------------------------------------------

dev: env ## Start the stack in dev mode: code is mounted and the API reloads on every change
	$(COMPOSE_DEV) up -d --build --wait
	@echo "Dev API with hot reload: $(API_URL)/docs  (make dev-logs to watch reloads)"

dev-logs: ## Follow the dev API logs (reloads and fake emails show up here)
	$(COMPOSE_DEV) logs -f api

test-docker: env ## Run lint and the test suite inside the dev container
	$(COMPOSE_DEV) build api
	$(COMPOSE_DEV) run --rm --no-deps --entrypoint sh api -c \
		"flake8 . && ruff check . && black --check . && isort --check-only . && pytest"

# --- Run on the host (hot reload) -----------------------------------------------------------

db-up: env ## Start only PostgreSQL
	$(COMPOSE) up -d --wait db

run: install db-up ## Run the API locally with auto-reload against the dockerised database
	$(BIN)/alembic upgrade head
	$(BIN)/uvicorn app.main:create_app --factory --reload --port $(API_PORT)

# --- Cleanup --------------------------------------------------------------------------------

clean: ## Remove caches and coverage artefacts
	rm -rf .pytest_cache .ruff_cache htmlcov .coverage *.egg-info
	find . -type d -name __pycache__ -not -path "./$(VENV)/*" -exec rm -rf {} +

nuke: clean ## Remove containers, the database volume and the virtualenv
	$(COMPOSE) down -v --remove-orphans
	rm -rf $(VENV)
