PY=python
PIP=pip

.PHONY: init fmt lint test check

init:
	$(PIP) install -r requirements.txt
	pre-commit install

fmt:
	black .
	isort .

lint:
	ruff check .

test:
	pytest -q

check: fmt lint test

