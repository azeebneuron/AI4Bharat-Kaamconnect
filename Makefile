.PHONY: install install-dev lint test test-unit test-property synth deploy

install:
	uv pip install -e .

install-dev:
	uv pip install -e ".[dev,cdk]"

venv:
	uv venv --python 3.12
	@echo "Run: source .venv/bin/activate"

lint:
	ruff check src/ tests/
	ruff format --check src/ tests/

format:
	ruff check --fix src/ tests/
	ruff format src/ tests/

test:
	pytest tests/ -v

test-unit:
	pytest tests/unit/ -v

test-property:
	pytest tests/property/ -v -m property

synth:
	cd infra && cdk synth

deploy:
	cd infra && cdk deploy --all --require-approval never

diff:
	cd infra && cdk diff

seed:
	python scripts/seed_jobs.py
