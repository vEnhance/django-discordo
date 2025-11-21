.PHONY: install install-test test build clean

install:
	uv pip install -e .

install-test:
	uv pip install -e ".[test]"

test:
	uv run python -m unittest django_discordo.tests

build:
	uv build

clean:
	rm -rf dist/ build/ *.egg-info src/*.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
