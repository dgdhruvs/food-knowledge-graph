.PHONY: help install migrate seed test test-unit test-integration lint format crawler api docs

help:
	@echo "Food Knowledge Graph — Available Commands"
	@echo ""
	@echo "  make install        Install all packages in development mode"
	@echo "  make migrate        Run Alembic database migrations"
	@echo "  make seed           Seed base data (countries, ingredients)"
	@echo "  make test           Run all tests"
	@echo "  make test-unit      Run unit tests only"
	@echo "  make test-int       Run integration tests only"
	@echo "  make lint           Run ruff linter + mypy type checker"
	@echo "  make format         Format code with ruff"
	@echo "  make crawler        Start crawler workers"
	@echo "  make api            Start FastAPI development server"
	@echo "  make infra-up       Start all infrastructure (docker compose)"
	@echo "  make infra-down     Stop all infrastructure"

install:
	pip install -e "packages/fkg-common[dev]"
	pip install -e "packages/fkg-crawler[dev]"
	pip install -e "packages/fkg-parser[dev]"
	pip install -e "packages/fkg-normalizer[dev]"
	pip install -e "packages/fkg-agents[dev]"
	pip install -e "packages/fkg-rules[dev]"
	pip install -e "packages/fkg-dedup[dev]"
	pip install -e "packages/fkg-graph[dev]"
	pip install -e "packages/fkg-review[dev]"
	pip install -e "packages/fkg-api[dev]"

migrate:
	alembic upgrade head

seed:
	python scripts/seed_countries.py
	python scripts/seed_ingredients.py

test:
	pytest tests/ -v --tb=short

test-unit:
	pytest tests/unit/ -v --tb=short

test-int:
	pytest tests/integration/ -v --tb=short

lint:
	ruff check packages/ tests/
	mypy packages/

format:
	ruff format packages/ tests/

crawler:
	python -m fkg_crawler.main

api:
	uvicorn fkg_api.main:app --reload --port 8000

infra-up:
	docker compose up -d postgres neo4j redis kafka zookeeper weaviate

infra-down:
	docker compose down

infra-all-up:
	docker compose up -d

neo4j-shell:
	docker compose exec neo4j cypher-shell -u neo4j -p fkgpassword

redis-cli:
	docker compose exec redis redis-cli

psql:
	docker compose exec postgres psql -U fkg fkg
