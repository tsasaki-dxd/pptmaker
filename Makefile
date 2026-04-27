.PHONY: help install install-api install-render install-infra install-web lint test test-unit test-integration synth diff deploy-pipeline build-render render-image samples clean

help:
	@echo "SlideForge Makefile"
	@echo ""
	@echo "Setup:"
	@echo "  make install         Install everything (api + render + infra + web)"
	@echo "  make install-api"
	@echo "  make install-render"
	@echo "  make install-infra"
	@echo "  make install-web"
	@echo ""
	@echo "Quality:"
	@echo "  make lint            Ruff + mypy"
	@echo "  make test            All tests"
	@echo "  make test-unit"
	@echo "  make test-integration"
	@echo ""
	@echo "Infra:"
	@echo "  make synth           cdk synth"
	@echo "  make diff            cdk diff"
	@echo "  make deploy-pipeline Deploy SlideForgePipelineStack (initial bootstrap)"
	@echo ""
	@echo "Render:"
	@echo "  make build-render    Build Lambda Container image"

install: install-api install-render install-infra install-web

install-api:
	cd app/api && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt

install-render:
	cd app/render && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt

install-infra:
	cd infra && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt

install-web:
	cd app/web && npm install

lint:
	ruff check app tests evals
	mypy app

test: test-unit test-integration

test-unit:
	pytest tests/unit -v

test-integration:
	pytest tests/integration -v

synth:
	cd infra && npx cdk synth --all

diff:
	cd infra && npx cdk diff --all

deploy-pipeline:
	cd infra && npx cdk deploy SlideForgePipelineStack --require-approval broadening

build-render:
	docker build -t slideforge/render:local app/render

samples:
	# Regenerate the /samples gallery PNGs and manifest.json under
	# app/web/public/samples/. Requires LibreOffice (soffice) and
	# poppler-utils (pdftoppm) on PATH.
	python -m scripts.generate_samples

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name .ruff_cache -exec rm -rf {} +
	find . -type d -name cdk.out -exec rm -rf {} +
	find . -type d -name .next -exec rm -rf {} +
