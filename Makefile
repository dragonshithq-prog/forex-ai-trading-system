# =============================================================================
# Forex AI Trading Platform — Makefile
# =============================================================================
# Usage:
#   make build        Build Docker images
#   make up           Start all services (docker-compose)
#   make down         Stop all services
#   make test         Run backend tests
#   make lint         Run linters (ruff, mypy)
#   make format       Format code (ruff format)
#   make deploy       Deploy to environment
#   make backup       Backup PostgreSQL database
#   make seed         Seed database with initial data
#   make clean        Clean build artifacts
#   make help         Show this help message
# =============================================================================

.PHONY: help build up down test lint format deploy backup seed clean precommit

SHELL := /bin/bash
.DEFAULT_GOAL := help

# ── Variables ─────────────────────────────────────────────────────────────────
ENVIRONMENT ?= development
IMAGE_TAG   ?= latest
REGISTRY    ?= ghcr.io
REPO_NAME   ?= org/forex-trading

# ── Colors ────────────────────────────────────────────────────────────────────
COLOR_RESET   = \033[0m
COLOR_CYAN    = \033[0;36m
COLOR_GREEN   = \033[0;32m
COLOR_YELLOW  = \033[1;33m

## ── Help ──────────────────────────────────────────────────────────────────────
help: ## Show this help message
	@echo "$(COLOR_CYAN)Forex AI Trading Platform — Makefile$(COLOR_RESET)"
	@echo ""
	@echo "$(COLOR_YELLOW)Usage:$(COLOR_RESET)"
	@echo "  make <target> [ENVIRONMENT=staging] [IMAGE_TAG=v1.2.3]"
	@echo ""
	@echo "$(COLOR_YELLOW)Targets:$(COLOR_RESET)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "$(COLOR_GREEN)  %-15s$(COLOR_RESET) %s\n", $$1, $$2}'

# ── Docker ─────────────────────────────────────────────────────────────────────

build: ## Build Docker images (backend + frontend)
	@echo "$(COLOR_CYAN)Building Docker images...$(COLOR_RESET)"
	docker build -f docker/Dockerfile.backend \
		-t $(REGISTRY)/$(REPO_NAME)/backend:$(IMAGE_TAG) \
		--build-arg BUILD_DATE=$(shell date -u +%Y-%m-%dT%H:%M:%SZ) \
		--build-arg GIT_SHA=$(shell git rev-parse --short HEAD 2>/dev/null || echo "local") \
		.
	docker build -f docker/Dockerfile.frontend \
		-t $(REGISTRY)/$(REPO_NAME)/frontend:$(IMAGE_TAG) \
		--build-arg BUILD_DATE=$(shell date -u +%Y-%m-%dT%H:%M:%SZ) \
		--build-arg GIT_SHA=$(shell git rev-parse --short HEAD 2>/dev/null || echo "local") \
		.
	@echo "$(COLOR_GREEN)Build complete.$(COLOR_RESET)"

build-backend: ## Build only the backend Docker image
	docker build -f docker/Dockerfile.backend \
		-t $(REGISTRY)/$(REPO_NAME)/backend:$(IMAGE_TAG) \
		--build-arg BUILD_DATE=$(shell date -u +%Y-%m-%dT%H:%M:%SZ) \
		--build-arg GIT_SHA=$(shell git rev-parse --short HEAD 2>/dev/null || echo "local") \
		.

build-frontend: ## Build only the frontend Docker image
	docker build -f docker/Dockerfile.frontend \
		-t $(REGISTRY)/$(REPO_NAME)/frontend:$(IMAGE_TAG) \
		--build-arg BUILD_DATE=$(shell date -u +%Y-%m-%dT%H:%M:%SZ) \
		--build-arg GIT_SHA=$(shell git rev-parse --short HEAD 2>/dev/null || echo "local") \
		.

up: ## Start all Docker services
	@echo "$(COLOR_CYAN)Starting services...$(COLOR_RESET)"
	docker compose -f docker/docker-compose.yml --env-file .env up -d
	@echo "$(COLOR_GREEN)Services started.$(COLOR_RESET)"

down: ## Stop all Docker services
	@echo "$(COLOR_CYAN}Stopping services...$(COLOR_RESET)"
	docker compose -f docker/docker-compose.yml down
	@echo "$(COLOR_GREEN)Services stopped.$(COLOR_RESET)"

logs: ## View service logs
	docker compose -f docker/docker-compose.yml logs -f

ps: ## List running services
	docker compose -f docker/docker-compose.yml ps

restart: ## Restart all services
	docker compose -f docker/docker-compose.yml restart

# ── Testing ────────────────────────────────────────────────────────────────────

test: ## Run all backend tests (unit + integration + security)
	@echo "$(COLOR_CYAN)Running backend tests...$(COLOR_RESET)"
	cd backend && python -m pytest tests/ \
		-v \
		--tb=short \
		--strict-markers \
		--cov=forex_trading \
		--cov-branch \
		--cov-report=term-missing \
		--cov-fail-under=80 \
		-x
	@echo "$(COLOR_GREEN)Tests completed.$(COLOR_RESET)"

test-unit: ## Run only unit tests
	@echo "$(COLOR_CYAN)Running unit tests...$(COLOR_RESET)"
	cd backend && python -m pytest tests/unit/ -v --tb=short -m unit

test-integration: ## Run only integration tests
	@echo "$(COLOR_CYAN)Running integration tests...$(COLOR_RESET)"
	cd backend && python -m pytest tests/ -v --tb=short -m integration

test-security: ## Run only security tests
	@echo "$(COLOR_CYAN}Running security tests...$(COLOR_RESET)"
	cd backend && python -m pytest tests/security/ -v --tb=short

test-load: ## Run load/performance tests
	@echo "$(COLOR_CYAN)Running load tests...$(COLOR_RESET)"
	cd backend && python -m pytest tests/load/ -v --tb=short

test-e2e: ## Run end-to-end tests
	@echo "$(COLOR_CYAN)Running e2e tests...$(COLOR_RESET)"
	cd backend && python -m pytest tests/e2e/ -v --tb=short

# ── Linting & Formatting ──────────────────────────────────────────────────────

lint: ## Run all linters (ruff + mypy)
	@echo "$(COLOR_CYAN)Running linters...$(COLOR_RESET)"
	cd backend && ruff check src/
	cd backend && ruff format --check src/
	cd backend && mypy src/ --strict
	@echo "$(COLOR_GREEN)Linting complete.$(COLOR_RESET)"

lint-fix: ## Fix auto-fixable lint issues
	cd backend && ruff check src/ --fix

format: ## Format code with ruff
	@echo "$(COLOR_CYAN)Formatting code...$(COLOR_RESET)"
	cd backend && ruff format src/
	@echo "$(COLOR_GREEN)Formatting complete.$(COLOR_RESET)"

# ── Git Hooks ──────────────────────────────────────────────────────────────────

precommit: ## Run pre-commit hooks on all files
	@echo "$(COLOR_CYAN)Running pre-commit hooks...$(COLOR_RESET)"
	pre-commit run --all-files
	@echo "$(COLOR_GREEN)Pre-commit checks complete.$(COLOR_RESET)"

precommit-install: ## Install pre-commit hooks
	pre-commit install
	pre-commit install --hook-type commit-msg

# ── Database ──────────────────────────────────────────────────────────────────

backup: ## Backup PostgreSQL database
	@echo "$(COLOR_CYAN)Backing up database...$(COLOR_RESET)"
	./scripts/backup-db.sh ./backups/postgres
	@echo "$(COLOR_GREEN)Backup complete.$(COLOR_RESET)"

seed: ## Seed database with initial data
	@echo "$(COLOR_CYAN)Seeding database...$(COLOR_RESET)"
	./scripts/seed-data.sh --environment=$(ENVIRONMENT)
	@echo "$(COLOR_GREEN)Seeding complete.$(COLOR_RESET)"

migrate: ## Run database migrations
	@echo "$(COLOR_CYAN)Running migrations...$(COLOR_RESET)"
	cd backend && alembic upgrade head
	@echo "$(COLOR_GREEN)Migrations complete.$(COLOR_RESET)"

migrate-new: ## Create a new migration
	cd backend && alembic revision --autogenerate -m "$(name)"

# ── Deployment ─────────────────────────────────────────────────────────────────

deploy: ## Deploy to environment (ENVIRONMENT=staging IMAGE_TAG=sha-abc123)
	@echo "$(COLOR_CYAN)Deploying $(IMAGE_TAG) to $(ENVIRONMENT)...$(COLOR_RESET)"
	./scripts/deploy.sh $(ENVIRONMENT) $(IMAGE_TAG)
	@echo "$(COLOR_GREEN)Deployment complete.$(COLOR_RESET)"

rollback: ## Rollback deployment (ENVIRONMENT=staging [REVISION=2])
	@echo "$(COLOR_CYAN)Rolling back $(ENVIRONMENT)...$(COLOR_RESET)"
	./scripts/rollback.sh $(ENVIRONMENT) $(REVISION)
	@echo "$(COLOR_GREEN)Rollback complete.$(COLOR_RESET)"

# ── Cleanup ────────────────────────────────────────────────────────────────────

clean: ## Clean all build artifacts
	@echo "$(COLOR_CYAN)Cleaning artifacts...$(COLOR_RESET)"
	rm -rf backend/dist/
	rm -rf backend/build/
	rm -rf backend/*.egg-info/
	rm -rf backend/.coverage*
	rm -rf backend/coverage.xml
	rm -rf backend/htmlcov/
	rm -rf backend/.pytest_cache/
	rm -rf backend/.mypy_cache/
	rm -rf backend/__pycache__/
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name "*.pyo" -delete 2>/dev/null || true
	@echo "$(COLOR_GREEN)Clean complete.$(COLOR_RESET)"

clean-docker: ## Clean Docker resources (volumes, unused images)
	docker compose -f docker/docker-compose.yml down -v 2>/dev/null || true
	docker system prune -af --volumes 2>/dev/null || true
	@echo "$(COLOR_GREEN)Docker cleanup complete.$(COLOR_RESET)"

# ── Development ────────────────────────────────────────────────────────────────

install: ## Install development dependencies
	@echo "$(COLOR_CYAN)Installing dependencies...$(COLOR_RESET)"
	cd backend && pip install -e ".[dev]"
	@echo "$(COLOR_GREEN)Installation complete.$(COLOR_RESET)"

dev: ## Run development server with hot-reload
	cd backend && python -m uvicorn forex_trading.main:app \
		--host 0.0.0.0 \
		--port 8000 \
		--reload \
		--log-level info

shell: ## Open a Python shell with the app context
	cd backend && python -c "from forex_trading.main import app; from forex_trading.config import get_settings; settings = get_settings(); print('App loaded. Settings available as `settings`')" && python
