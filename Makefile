.PHONY: help install db-migrate serve scan lint format typecheck test clean

help:
	@echo "TPT — Top Picker Terminal"
	@echo ""
	@echo "Commands:"
	@echo "  install      Install Python dependencies with uv"
	@echo "  db-migrate   Run Alembic migrations (creates/updates tpt.db)"
	@echo "  serve        Start FastAPI backend (API + worker)"
	@echo "  scan         Run an on-demand scan (CLI)"
	@echo "  lint         Run ruff linter"
	@echo "  format       Auto-format with ruff"
	@echo "  typecheck    Run mypy"
	@echo "  test         Run pytest"
	@echo "  clean        Remove __pycache__, .pytest_cache, etc."

install:
	uv pip install -e ".[dev]"

db-migrate:
	uv run alembic upgrade head

serve:
	uv run uvicorn tpt.api.main:app --host 127.0.0.1 --port 8000 --reload

scan:
	uv run tpt scan

lint:
	uv run ruff check backend/ tests/

format:
	uv run ruff format backend/ tests/

typecheck:
	uv run mypy backend/tpt/

test:
	uv run pytest tests/ -v

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null; \
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null; \
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null; \
	echo "Cleaned."
