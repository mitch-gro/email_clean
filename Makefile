.PHONY: run format install

install:
	@if [ ! -d ".venv" ]; then poetry config virtualenvs.in-project true && poetry install; \
	else poetry install; fi

run: install
	poetry run python main.py

format: install
	poetry run black .
