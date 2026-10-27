.PHONY: install install-ivr test lint fmt security validate ivr ivr-live load compare compose

IVR := ../01-agentic-voice-ivr
export VAE_API_KEY ?= change-me-local-only
export IVR_LOG_LEVEL ?= WARNING

install:
	pip install -r requirements.lock && pip install -e ".[dev]"

# Needed for the integration tests and the `ivr` target.
install-ivr:
	pip install -r $(IVR)/requirements.lock && pip install -e $(IVR)

test:
	pytest --cov=vae --cov-report=term-missing --cov-fail-under=90

lint:
	ruff check . && ruff format --check .

fmt:
	ruff format . && ruff check --fix .

security:
	bandit -r vae -ll && pip-audit -r requirements.lock

validate:
	vae validate suites/ivr

# Full suite (scenarios + noise variants), in-process, a fresh IVR per call.
ivr:
	vae run suites/ivr --app "app.main:create_app()" --app-path $(IVR) --isolate --gate \
	  --out reports/ivr-results.json --report reports/ivr-report.md

# Against a running IVR (make -C $(IVR) run), over HTTP.
ivr-live:
	vae run suites/ivr --base-url http://localhost:8000 --profiles '' --gate --report reports/ivr-live-report.md

load:
	vae load suites/ivr --base-url http://localhost:8000 --calls 500 --concurrency 50 --gate \
	  --report reports/ivr-load-report.md

# Fails if the current IVR regressed against the committed baseline.
compare: ivr
	vae compare baselines/ivr.json reports/ivr-results.json --ignore-latency

compose:
	docker compose up --build --abort-on-container-exit --exit-code-from evals
