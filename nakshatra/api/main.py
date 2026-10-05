"""Local HTTP API (API Contract v1): /api/v1 routes, SSE with replay, one error envelope.

    uvicorn nakshatra.api.main:app --host 127.0.0.1 --port 8000
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.exceptions import HTTPException

from nakshatra import __version__
from nakshatra.errors import NakshatraError
from nakshatra.orchestrator.events import TERMINAL_EVENTS
from nakshatra.orchestrator.run import Run, parse_place, status_of
from nakshatra.settings import Config, Env, load_config
from nakshatra.store.db import SCHEMA_VERSION, Store

log = logging.getLogger("nakshatra.api")

SENTINEL = "r_0000000000"  # ledger owner for place search (API §5.4)
ACTIVE = ("created", "resolving", "sampling", "expanding", "refining", "mining", "reporting")
HEARTBEAT_S = 10.0
IDEMPOTENCY_S = 600.0
STATUS = {"E_VALIDATION": 422, "E_BAD_PLACE": 400, "E_BUDGET": 422, "E_RUN_ACTIVE": 409, "E_RUN_TERMINAL": 409,
          "E_RUN_NOT_DONE": 409, "E_NOT_FOUND": 404, "E_FORMAT": 415, "E_PDF_UNAVAILABLE": 501, "E_AUTH": 503,
          "E_INTERNAL": 500}
WEB_DIST = Path(__file__).parents[2] / "web" / "dist"


class RunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    place: str = Field(min_length=3, max_length=2048)
    budget: int | None = None  # range checked by hand so it maps to E_BUDGET, not E_VALIDATION
    offline: bool = False


def envelope(code: str, message: str, details: dict | None = None, run_id: str | None = None) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message, "details": details or {}, "run_id": run_id}},
                        status_code=STATUS.get(code, 500))


class State:
    def __init__(self, store: Store, cfg: Config, env: Env, run_kwargs: Callable[[], dict] | None):
        self.store, self.cfg, self.env = store, cfg, env
        self.run_kwargs = run_kwargs or dict
        self.runs: dict[str, Run] = {}
        self.tasks: set[asyncio.Task] = set()
        self.idem: dict[str, tuple[str, float]] = {}

    def active_run(self) -> str | None:
        return next((rid for rid, r in self.runs.items() if r.state in ACTIVE), None)


def create_app(store: Store | None = None, cfg: Config | None = None, env: Env | None = None,
               run_kwargs: Callable[[], dict] | None = None) -> FastAPI:
    env = env or Env()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        st = State(store or Store(env.nakshatra_db), cfg or load_config(), env, run_kwargs)
        s = st.store
        if not s.run_get(SENTINEL):
            s.run_create(SENTINEL, "sentinel: place search", 200, False, st.cfg.canonical_json(), st.cfg.hash(), 0.0)
            s.run_update(SENTINEL, state="done")
        # A run left active by a crash cannot continue; it can be replayed offline (ARCH §8.3).
        for (rid,) in s.conn.execute(f"SELECT run_id FROM runs WHERE state IN ({','.join('?' * len(ACTIVE))})",
                                     ACTIVE).fetchall():
            seq = s.conn.execute("SELECT COALESCE(MAX(seq),0) FROM events WHERE run_id=?", (rid,)).fetchone()[0]
            with s.tx():
                s.run_update(rid, state="failed", ended_at=time.time(), error_code="E_INTERNAL")
                s.event_append(rid, seq + 1, "phase", {"phase": "failed", "ts": time.time()})
                s.event_append(rid, seq + 2, "error", {"code": "E_INTERNAL", "message": "server restarted mid-run"})
        app.state.s = st
        yield
        for t in st.tasks:
            t.cancel()

    app = FastAPI(title="Nakshatra API", version=__version__, lifespan=lifespan,
                  openapi_url="/api/v1/openapi.json", docs_url="/api/v1/docs")

    @app.exception_handler(NakshatraError)
    async def _nk(_: Request, e: NakshatraError) -> JSONResponse:
        return envelope(e.code, e.message)

    @app.exception_handler(RequestValidationError)
    async def _val(_: Request, e: RequestValidationError) -> JSONResponse:
        return envelope("E_VALIDATION", "request does not match the schema",
                        {"errors": [{"loc": list(x["loc"]), "msg": x["msg"]} for x in e.errors()]})

    @app.exception_handler(HTTPException)
    async def _http(_: Request, e: HTTPException) -> JSONResponse:
        return envelope("E_NOT_FOUND" if e.status_code == 404 else "E_VALIDATION", str(e.detail))

    @app.exception_handler(Exception)
    async def _any(_: Request, e: Exception) -> JSONResponse:
        log.exception("unhandled")
        return envelope("E_INTERNAL", type(e).__name__)

    r = APIRouter()

    def S(request: Request) -> State:
        return request.app.state.s

    def row_or_404(st: State, run_id: str):
        row = st.store.run_get(run_id)
        if row is None or run_id == SENTINEL:
            raise NakshatraError("E_NOT_FOUND", f"no run {run_id}")
        return row

    @r.post("/runs", status_code=201)
    async def create_run(body: RunCreate, request: Request,
                         idempotency_key: str | None = Header(None, max_length=64)) -> JSONResponse:
        st = S(request)
        now = time.time()
        if idempotency_key and (hit := st.idem.get(idempotency_key)) and now - hit[1] < IDEMPOTENCY_S:
            return JSONResponse(created(st, hit[0]), status_code=200)
        budget = st.cfg.budget.default if body.budget is None else body.budget
        if not st.cfg.budget.min <= budget <= st.cfg.budget.max:
            return envelope("E_BUDGET", f"budget must be between {st.cfg.budget.min} and {st.cfg.budget.max}",
                            {"field": "budget", "min": st.cfg.budget.min, "max": st.cfg.budget.max})
        parse_place(body.place)  # E_BAD_PLACE before anything is written
        if (active := st.active_run()) is not None:
            return envelope("E_RUN_ACTIVE", "An investigation is already running.", run_id=active)
        offline = body.offline or st.env.nakshatra_offline
        if not offline and not st.env.serpapi_api_key:
            return envelope("E_AUTH", "No SerpApi key found. Replay cached runs offline, or add a key to .env.")
        run = Run(st.store, st.cfg, body.place, budget, offline, st.env.serpapi_api_key, **st.run_kwargs())
        st.runs[run.id] = run
        task = asyncio.create_task(run.execute())
        st.tasks.add(task)
        task.add_done_callback(st.tasks.discard)
        if idempotency_key:
            st.idem[idempotency_key] = (run.id, now)
        return JSONResponse(created(st, run.id), status_code=201)

    def created(st: State, run_id: str) -> dict:
        row = st.store.run_get(run_id)
        base = f"/api/v1/runs/{run_id}"
        return {"run_id": run_id, "state": row["state"], "seed_data_id": row["seed_data_id"], "budget": row["budget"],
                "offline": bool(row["offline"]),
                "links": {"self": base, "events": f"{base}/events", "ledger": f"{base}/ledger"}}

    @r.get("/runs")
    async def list_runs(request: Request, limit: int = Query(20, ge=1, le=50), before: float | None = None) -> list:
        return [{"run_id": x["run_id"], "state": x["state"], "seed_title": x["seed_title"],
                 "seed_data_id": x["seed_data_id"],
                 "started_at": x["started_at"], "credits_used": x["used"], "rings_reported": x["rings_reported"]}
                for x in S(request).store.runs_list(limit, before)]

    @r.get("/runs/{run_id}")
    async def get_run(run_id: str, request: Request) -> dict:
        st = S(request)
        return status_of(st.store, row_or_404(st, run_id))

    @r.get("/runs/{run_id}/events")
    async def events(run_id: str, request: Request, after: int | None = Query(None, ge=0),
                     last_event_id: int | None = Header(None)) -> StreamingResponse:
        st = S(request)
        row_or_404(st, run_id)
        start = last_event_id if last_event_id is not None else (after or 0)
        run = st.runs.get(run_id)
        q = run.bus.subscribe() if run and not run.bus.closed else None  # subscribe before replay: no gap

        async def gen() -> AsyncIterator[str]:
            last = start
            try:
                for row in st.store.events_since(run_id, start):
                    last = row["seq"]
                    yield f"id: {row['seq']}\nevent: {row['type']}\ndata: {row['payload_json']}\n\n"
                    if row["type"] in TERMINAL_EVENTS:
                        return
                if q is None:
                    return
                while True:
                    try:
                        seq, etype, payload = await asyncio.wait_for(q.get(), timeout=HEARTBEAT_S)
                    except TimeoutError:
                        yield ": hb\n\n"
                        continue
                    if seq <= last:
                        continue
                    last = seq
                    yield f"id: {seq}\nevent: {etype}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n"
                    if etype in TERMINAL_EVENTS:
                        return
            finally:
                if q is not None:
                    run.bus.unsubscribe(q)

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @r.get("/runs/{run_id}/rings/{idx}/evidence")
    async def evidence(run_id: str, idx: int, request: Request) -> dict:
        st = S(request)
        row = row_or_404(st, run_id)
        if row["state"] != "done":
            raise NakshatraError("E_RUN_NOT_DONE", "the result is not ready")
        rings = (st.store.result_get(run_id) or {}).get("rings", [])
        ring = next((x for x in rings if x["idx"] == idx), None)
        if ring is None:
            raise NakshatraError("E_NOT_FOUND", f"run {run_id} has no ring {idx}")
        return {"run_id": run_id, "idx": idx, "places": ring.get("evidence", [])}

    @r.get("/runs/{run_id}/ledger")
    async def ledger(run_id: str, request: Request, limit: int = Query(200, ge=1, le=500),
                     after: int = Query(0, ge=0)) -> dict:
        st = S(request)
        row_or_404(st, run_id)
        rows = st.store.ledger(run_id, after, limit + 1)
        items = [{"id": x["id"], "engine": x["engine"], "pool": x["pool"], "cached": bool(x["cached"]),
                  "billed": bool(x["billed"]), "ok": bool(x["ok"]), "latency_ms": x["latency_ms"], "ts": x["ts"],
                  "search_id": x["search_id"]} for x in rows[:limit]]
        return {"run_id": run_id, "totals": st.store.ledger_totals(run_id), "items": items,
                "next": items[-1]["id"] if len(rows) > limit else None}

    @r.get("/health")
    async def health(request: Request) -> dict:
        st = S(request)
        try:
            st.store.conn.execute("SELECT 1").fetchone()
            db = "ok"
        except Exception:  # noqa: BLE001
            db = "error"
        return {"status": "ok" if db == "ok" else "degraded", "version": __version__, "schema_version": SCHEMA_VERSION,
                "db": db, "api_key_present": bool(st.env.serpapi_api_key),
                "offline_forced": st.env.nakshatra_offline, "active_run": st.active_run()}

    app.include_router(r, prefix="/api/v1")
    app.include_router(r, prefix="/api", include_in_schema=False)  # hackathon alias (API §1)

    if WEB_DIST.is_dir():  # demo mode: serve the built SPA, with client-side routes falling back to index.html
        app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        async def spa(path: str) -> Any:
            if path == "api" or path.startswith("api/"):
                raise NakshatraError("E_NOT_FOUND", f"no endpoint /{path}")
            f = (WEB_DIST / path).resolve()
            inside = f.is_relative_to(WEB_DIST.resolve())
            return FileResponse(f if path and inside and f.is_file() else WEB_DIST / "index.html")

    return app


app = create_app()
