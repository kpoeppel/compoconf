.PHONY: clean install test lint format docs coverage

clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info
	rm -rf .pytest_cache
	rm -rf .coverage
	rm -rf docs/build
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

install:
	pip install -e ".[dev,test,docs]"

test:
	pytest

coverage:
	pytest --cov=compoconf --cov-report=term-missing

lint:
	flake8 src tests
	mypy src tests

format:
	black src tests
	isort src tests

docs:
	cd docs && make html

docs-serve:
	python -m http.server -d docs/build/html 8000

all: clean install format lint test docs
