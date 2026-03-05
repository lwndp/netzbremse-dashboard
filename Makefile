.PHONY: format lint test

format:
	uv run black app/ tests/
	uv run isort app/ tests/

lint:
	uv run ruff check app/ tests/
	uv run black --check app/ tests/

test:
	uv run pytest tests/ -v
