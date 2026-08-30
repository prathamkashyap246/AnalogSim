help:
	@echo "Available commands:"
	@echo "  make setup        - Install dependencies"
	@echo "  make dev          - Start development servers"
	@echo "  make test         - Run all tests"
	@echo "  make lint         - Run linters"
	@echo "  make format       - Format code"
	@echo "  make build        - Build Docker images"
	@echo "  make clean        - Clean up build artifacts"

setup:
	@echo "Setting up development environment..."
	cp .env.example .env
	docker-compose build
	docker-compose run api pip install -r requirements.txt
	docker-compose run web npm install

dev:
	docker-compose up -d postgres minio
	docker-compose up api web

test:
	@echo "Running tests..."
	docker-compose run api pytest tests/ -v
	docker-compose run web npm run test

lint:
	@echo "Running linters..."
	docker-compose run api flake8 app/
	docker-compose run web npm run lint

format:
	@echo "Formatting code..."
	docker-compose run api black app/ tests/
	docker-compose run api isort app/ tests/
	docker-compose run web npm run format

build:
	docker-compose build

clean:
	docker-compose down -v
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf node_modules .next dist

.PHONY: help setup dev test lint format build clean
