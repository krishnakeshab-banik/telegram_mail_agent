.PHONY: install lint typecheck test run check migrate docker

install:
	python -m pip install -r requirements.txt

lint:
	python -m ruff check app tests scripts
	python -m ruff format --check app tests scripts

format:
	python -m ruff format app tests scripts
	python -m ruff check --fix app tests scripts

typecheck:
	python -m mypy app

test:
	python -m pytest

check: lint typecheck test
	python -m app.main --check

migrate:
	python -m alembic upgrade head

run:
	python -m app.main

docker:
	docker compose up --build
