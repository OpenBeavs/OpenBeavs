.PHONY: install dev-front dev-hub build lint lint-frontend lint-backend \
        format test test-frontend test-backend clean help

# ── Setup ─────────────────────────────────────────────────────────────────────
install:
	@echo "→ Installing frontend dependencies..."
	cd front && npm install
	@echo "→ Installing backend hub dependencies..."
	cd back && pip install -r requirements.txt
	@echo "✅ Done. Run 'make dev-front' and 'make dev-hub' in separate terminals."

# ── Development ───────────────────────────────────────────────────────────────
dev-front:
	cd front && npm run dev

dev-hub:
	cd back && uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# ── Build ─────────────────────────────────────────────────────────────────────
build:
	cd front && npm run build:copy

# ── Lint ──────────────────────────────────────────────────────────────────────
lint: lint-frontend lint-backend

lint-frontend:
	@echo "→ Linting frontend (ESLint)..."
	cd front && npx eslint .
	@echo "→ Type checking (svelte-check)..."
	cd front && npm run lint:types

lint-backend:
	@echo "→ Linting backend hub (Ruff)..."
	cd back && ruff check .

format:
	@echo "→ Formatting frontend..."
	cd front && npm run format
	@echo "→ Formatting backend hub..."
	cd back && ruff format .

# ── Test ──────────────────────────────────────────────────────────────────────
test: test-frontend test-backend

test-frontend:
	@echo "→ Running frontend tests (Vitest)..."
	cd front && npm run test:frontend

test-backend:
	@echo "→ Running backend hub tests (pytest)..."
	cd back && pytest tests/ -v

# ── Clean ─────────────────────────────────────────────────────────────────────
clean:
	rm -rf front/node_modules front/.svelte-kit back/__pycache__ back/.pytest_cache

# ── Help ──────────────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "OpenBeavs — Developer Commands"
	@echo "────────────────────────────────────────"
	@echo "  make install        Install all dependencies (frontend + backend hub)"
	@echo "  make dev-front      Start the SvelteKit frontend dev server"
	@echo "  make dev-hub        Start the A2A hub with hot-reload (port 8000)"
	@echo "  make build          Build frontend and copy to backend static dir"
	@echo "  make lint           Run ESLint + svelte-check + Ruff"
	@echo "  make format         Auto-format frontend (Prettier) + backend (Ruff)"
	@echo "  make test           Run all tests"
	@echo "  make test-frontend  Run Vitest unit tests only"
	@echo "  make test-backend   Run pytest hub tests only"
	@echo "  make clean          Remove build artifacts and caches"
	@echo ""
