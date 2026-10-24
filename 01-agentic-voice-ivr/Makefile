.PHONY: install run test lint fmt security evals simulate openapi data docker up down

install:
	pip install -r requirements.lock && pip install -e ".[dev]"

run:
	uvicorn app.main:app --reload --port 8000

test:
	pytest --cov=app --cov-report=term-missing --cov-fail-under=90

lint:
	ruff check . && ruff format --check .

fmt:
	ruff format . && ruff check --fix .

security:
	bandit -r app -ll && pip-audit -r requirements.lock

evals:
	python scripts/run_evals.py

simulate:
	python scripts/simulate_call.py

openapi:
	python scripts/export_openapi.py

data:
	python scripts/generate_synthetic_data.py

docker:
	docker build -t agentic-voice-ivr:local .

up:
	cp -n .env.example .env || true
	docker compose up --build -d

down:
	docker compose down
