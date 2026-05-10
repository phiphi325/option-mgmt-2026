.PHONY: help dev test lint typecheck migrate clean

help:
	@echo "Targets:"
	@echo "  make dev         bring up local docker stack (postgres + api + web)"
	@echo "  make test        pytest + vitest                              [M0.5+]"
	@echo "  make lint        ruff + eslint                                [M0.5+]"
	@echo "  make typecheck   mypy --strict + tsc --noEmit                 [M0.5+]"
	@echo "  make migrate     alembic upgrade head                         [M0.2+]"
	@echo "  make clean       remove containers, volumes, build artifacts"

dev:
	docker compose up

test:
	@echo "[M0.1] tests not yet wired; available from M0.5"
	@# uv run pytest packages/engine apps/api -q
	@# pnpm -r --if-present test

lint:
	@echo "[M0.1] lint not yet wired; available from M0.5"
	@# uv run ruff check .
	@# pnpm -r --if-present lint

typecheck:
	@echo "[M0.1] typecheck not yet wired; available from M0.5"
	@# uv run mypy --strict packages/engine
	@# pnpm -r --if-present typecheck

migrate:
	@echo "[M0.1] migrations not yet wired; available from M0.2"
	@# cd apps/api && uv run alembic upgrade head

clean:
	docker compose down -v
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name node_modules -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .next -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .turbo -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name dist -exec rm -rf {} + 2>/dev/null || true
