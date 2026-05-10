.PHONY: help dev test smoke lint typecheck migrate clean

help:
	@echo "Targets:"
	@echo "  make dev         bring up local docker stack (postgres + api + web)"
	@echo "  make test        pytest + vitest                              [M0.5+]"
	@echo "  make smoke       end-to-end smoke test (postgres + api + pytest)  [M0.7+]"
	@echo "  make lint        ruff + eslint                                [M0.5+]"
	@echo "  make typecheck   mypy --strict + tsc --noEmit                 [M0.5+]"
	@echo "  make migrate     alembic upgrade head                         [M0.2+]"
	@echo "  make clean       remove containers, volumes, build artifacts"

dev:
	docker compose up

test:
	cd apps/api && uv run pytest -q
	cd packages/engine && uv run pytest -q
	cd apps/web && pnpm test

smoke:
	bash scripts/run_smoke.sh

lint:
	cd apps/api && uv run ruff check .
	cd packages/engine && uv run ruff check .
	cd apps/web && pnpm lint

typecheck:
	cd apps/api && uv run mypy --strict app
	cd packages/engine && uv run mypy --strict engine
	cd apps/web && pnpm typecheck
	cd packages/shared-types && pnpm typecheck

migrate:
	cd apps/api && uv run alembic upgrade head

clean:
	docker compose down -v
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name node_modules -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .next -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .turbo -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name dist -exec rm -rf {} + 2>/dev/null || true
