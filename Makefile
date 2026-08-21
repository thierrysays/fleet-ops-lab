.PHONY: test demo lint types qa clean

test:
	python -m pytest

demo:
	python -m fleet_ops.cli demo --out ./run/rollout.json

lint:
	ruff check src tests

types:
	mypy

qa: lint types
	python -m pytest --cov=fleet_ops --cov-report=term-missing --cov-fail-under=90

clean:
	rm -rf run .pytest_cache .mypy_cache .coverage
	find . -name __pycache__ -type d -exec rm -rf {} +
