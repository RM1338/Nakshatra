.PHONY: install test lint check synth eval dev demo web

dev:                ## API on :8000 (reload) + Vite on http://localhost:5173 (proxies /api)
	cd web && npm install --silent
	trap 'kill 0' EXIT; uv run uvicorn nakshatra.api.main:app --reload --host 127.0.0.1 --port 8000 & \
	  (cd web && npx vite --host 127.0.0.1)

web:                ## Build the SPA into web/dist
	cd web && npm install --silent && npm run build

demo: web           ## One process on http://127.0.0.1:8000 serving the built SPA
	uv run uvicorn nakshatra.api.main:app --host 127.0.0.1 --port 8000

install:            ## Python + web deps
	uv sync
	cd web && npm install --silent

test:               ## Unit, contract and end-to-end tests (never call SerpApi)
	uv run ruff check nakshatra tests eval
	uv run pytest -q

lint:
	uv run ruff check nakshatra tests eval

check:              ## Data Model §5.3 integrity check on $NAKSHATRA_DB
	uv run python -m nakshatra.store.check

synth:              ## Crawl the synthetic SerpApi into $NAKSHATRA_DB (key-less development data)
	uv run python -m tests.synth_world --db $${NAKSHATRA_DB:-data/nakshatra.db}

eval:               ## Injection, controls, null calibration, credit efficiency -> eval/plots/ (0 credits)
	PYTHONPATH=. uv run python -m eval.run_all
