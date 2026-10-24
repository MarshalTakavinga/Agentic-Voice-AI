.PHONY: install test lint fmt security evals captures demo run openapi docker up

install:
	pip install -r requirements.lock && pip install -e ".[dev]"

test:
	pytest --cov=sipdoc --cov-report=term-missing --cov-fail-under=90

lint:
	ruff check . && ruff format --check .

fmt:
	ruff format . && ruff check --fix .

security:
	bandit -r sipdoc -ll && pip-audit -r requirements.lock

captures:
	python scripts/generate_captures.py

evals:
	python scripts/run_evals.py

demo:
	python -m sipdoc analyze captures/nat_one_way_audio.pcap

run:
	uvicorn sipdoc.api.app:app --reload --port 8001

openapi:
	python scripts/export_openapi.py

docker:
	docker build -t sip-call-doctor:local .

up:
	cp -n .env.example .env || true
	docker compose up --build -d
