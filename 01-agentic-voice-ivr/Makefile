.PHONY: install run test lint fmt security evals injection load simulate openapi data docker up scale down

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

injection:
	python scripts/run_injection_evals.py

# Needs two replicas running against one Redis (make scale).
load:
	python scripts/load_test.py --targets http://localhost:8000,http://localhost:8001 --calls 500 --concurrency 50

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

scale:
	cp -n .env.example .env || true
	docker compose --profile scale up --build -d

down:
	docker compose down
