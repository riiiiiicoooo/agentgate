.PHONY: help install dev test lint format clean docker-up docker-down db-migrate

help:
	@echo "AgentGate Development Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make install          Install all dependencies"
	@echo "  make docker-up         Start local development stack (Docker Compose)"
	@echo "  make docker-down       Stop local development stack"
	@echo ""
	@echo "Development:"
	@echo "  make dev              Start all services in development mode"
	@echo "  make dev-api          Start only API server"
	@echo "  make dev-dashboard    Start only dashboard"
	@echo "  make dev-cli          Run CLI in development mode"
	@echo ""
	@echo "Database:"
	@echo "  make db-migrate       Run database migrations"
	@echo "  make db-seed          Seed database with test data"
	@echo "  make db-reset         Reset database (drop and recreate)"
	@echo "  make db-shell         Open PostgreSQL shell"
	@echo ""
	@echo "Testing:"
	@echo "  make test             Run all tests"
	@echo "  make test-api         Run API tests only"
	@echo "  make test-sdk         Run SDK tests"
	@echo "  make test-coverage    Run tests with coverage report"
	@echo ""
	@echo "Code Quality:"
	@echo "  make lint             Run linters (flake8, eslint, mypy)"
	@echo "  make format           Format code (black, prettier)"
	@echo "  make type-check       Type check all TypeScript"
	@echo ""
	@echo "Documentation:"
	@echo "  make docs             Generate documentation"
	@echo "  make docs-serve       Serve documentation locally"
	@echo ""
	@echo "Deployment:"
	@echo "  make build-docker     Build Docker image"
	@echo "  make k8s-deploy       Deploy to Kubernetes"
	@echo "  make k8s-logs         Show Kubernetes pod logs"
	@echo ""

install:
	@echo "Installing Python dependencies..."
	pip install -r requirements.txt
	@echo "Installing Node.js dependencies..."
	npm install
	@echo "✓ Installation complete"

dev: docker-up
	@echo "Starting development environment..."
	npm run dev

dev-api:
	@echo "Starting API server..."
	cd api && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

dev-dashboard:
	@echo "Starting dashboard..."
	cd dashboard && npm run dev

dev-cli:
	@echo "CLI installed. Run: agentgate --help"
	pip install -e cli/

docker-up:
	@echo "Starting Docker Compose stack..."
	docker-compose up -d
	@echo "Waiting for services to be healthy..."
	sleep 5
	docker-compose ps
	@echo "✓ Services started"
	@echo "  API: http://localhost:8000"
	@echo "  Dashboard: http://localhost:3000"
	@echo "  Jaeger: http://localhost:16686"
	@echo "  PostgreSQL: localhost:5432"
	@echo "  Redis: localhost:6379"

docker-down:
	@echo "Stopping Docker Compose stack..."
	docker-compose down
	@echo "✓ Services stopped"

docker-logs:
	docker-compose logs -f

db-migrate:
	@echo "Running database migrations..."
	cd api && alembic upgrade head
	@echo "✓ Migrations complete"

db-seed:
	@echo "Seeding database with test data..."
	cd api && python -m app.db.seed
	@echo "✓ Database seeded"

db-reset: docker-up
	@echo "Resetting database..."
	docker-compose exec -T postgres psql -U postgres -c "DROP DATABASE IF EXISTS agentgate;"
	docker-compose exec -T postgres psql -U postgres -c "CREATE DATABASE agentgate;"
	make db-migrate
	make db-seed
	@echo "✓ Database reset complete"

db-shell:
	@echo "Connecting to PostgreSQL..."
	docker-compose exec postgres psql -U postgres -d agentgate

test:
	@echo "Running all tests..."
	pytest -v --cov=api --cov-report=html
	npm run test --workspaces
	@echo "✓ Tests complete (coverage report: htmlcov/index.html)"

test-api:
	@echo "Running API tests..."
	pytest api/tests -v --cov=api/app

test-sdk:
	@echo "Running SDK tests..."
	npm run test --workspaces

test-coverage:
	@echo "Running tests with coverage..."
	pytest --cov=api --cov-report=html --cov-report=term-missing
	@echo "✓ Coverage report: htmlcov/index.html"

lint:
	@echo "Running linters..."
	@echo "  Python (flake8)..."
	flake8 api --max-line-length=100
	@echo "  Python (mypy)..."
	mypy api/app --ignore-missing-imports
	@echo "  JavaScript (eslint)..."
	npm run lint --workspaces
	@echo "✓ Linting complete"

format:
	@echo "Formatting code..."
	@echo "  Python (black)..."
	black api --line-length=100
	@echo "  Python (isort)..."
	isort api --profile black
	@echo "  JavaScript (prettier)..."
	npm run format
	@echo "✓ Formatting complete"

type-check:
	@echo "Type checking..."
	mypy api/app --ignore-missing-imports
	npm run type-check --workspaces
	@echo "✓ Type checking complete"

docs:
	@echo "Building documentation..."
	mkdocs build
	@echo "✓ Documentation built (docs/_build/index.html)"

docs-serve:
	@echo "Serving documentation..."
	mkdocs serve

build-docker:
	@echo "Building Docker image..."
	docker build -t agentgate:latest -f api/Dockerfile .
	@echo "✓ Docker image built"

k8s-deploy:
	@echo "Deploying to Kubernetes..."
	helm install agentgate ./infrastructure/helm-charts/agentgate \
		--namespace agentgate --create-namespace
	@echo "✓ Deployment complete"
	@echo "Check status: kubectl get pods -n agentgate"

k8s-logs:
	@echo "Streaming Kubernetes logs..."
	kubectl logs -n agentgate -l app=agentgate-api -f

k8s-delete:
	@echo "Deleting Kubernetes deployment..."
	helm uninstall agentgate -n agentgate
	@echo "✓ Deployment deleted"

clean:
	@echo "Cleaning up..."
	rm -rf htmlcov/
	rm -rf .coverage
	rm -rf dist/
	rm -rf build/
	rm -rf *.egg-info/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	npm run clean --workspaces 2>/dev/null || true
	@echo "✓ Cleanup complete"

.DEFAULT_GOAL := help
