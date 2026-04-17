.PHONY: help install test lint format check run dashboard backtest docker clean reset

help:
	@echo "Available targets:"
	@echo "  install    - Install all dependencies"
	@echo "  test       - Run pytest"
	@echo "  lint       - Run ruff + mypy"
	@echo "  format     - Auto-format code"
	@echo "  check      - Check system dependencies"
	@echo "  run        - Run one pipeline cycle"
	@echo "  dashboard  - Start web dashboard at :8000"
	@echo "  backtest   - Run 1-year backtest"
	@echo "  docker     - Build and start with docker-compose"
	@echo "  clean      - Remove cache and build artifacts"
	@echo "  reset      - Reset paper account to \$$100k"

install:
	pip install -r requirements.txt
	pip install pytest pytest-asyncio pytest-cov ruff mypy pre-commit

test:
	pytest tests/ -v --cov=agents --cov=core

lint:
	ruff check .
	mypy agents core config --ignore-missing-imports || true

format:
	ruff format .
	ruff check . --fix

check:
	python main.py check

run:
	python main.py run

dashboard:
	python main.py dashboard

backtest:
	python main.py backtest --period 1y

docker:
	docker-compose up -d

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name .ruff_cache -exec rm -rf {} +
	find . -type d -name .mypy_cache -exec rm -rf {} +

reset:
	python main.py reset
