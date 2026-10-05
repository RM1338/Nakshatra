.PHONY: install test lint check synth eval dev

dev:                ## API on http://127.0.0.1:8000 with reload (the web UI joins in T26)
	uv run uvicorn nakshatra.api.main:app --reload --host 127.0.0.1 --port 8000

install:            ## Python deps (uv)
	uv sync

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
