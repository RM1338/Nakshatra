# Nakshatra API Contract

Oct 4, 2026 · @Ronel Abraham Mathew

The HTTP contract between the Nakshatra web client and its local server (v1), plus the outbound contract the server relies on from SerpApi. Where this differs from earlier sketches in the LLD, this document wins.

## 1. Conventions

| Aspect | Rule |
| --- | --- |
| Base URL | `http://127.0.0.1:8000/api/v1`. Every path below is relative to it. The unversioned alias `/api` maps to v1 for the hackathon build |
| Transport | HTTP/1.1, localhost only. No TLS, no auth (single local user, SRS-NF-12) |
| Request body | `application/json; charset=utf-8` |
| Responses | JSON, except the SSE stream (`text/event-stream`) and dossier downloads (`text/markdown`, `application/pdf`) |
| Field naming | `snake_case` |
| Times | Unix seconds as JSON numbers (UTC). Durations in milliseconds carry an `_ms` suffix |
| IDs | `run_id` = `r_` + 10 lowercase hex. Places = Maps `data_id` (`0x…:0x…`). Reviewers appear only as pseudonyms `R1…Rn`, except in dossier exports |
| Nullability | Absent and `null` mean the same thing. Clients must accept unknown extra fields |
| Errors | Always the envelope in §6, with a stable `code` |
| Idempotency | `POST /runs` accepts an `Idempotency-Key` header. A repeat within 10 minutes with the same key returns the original `run_id` and `200` instead of `201` |
| Concurrency | At most one run in an active state at a time. A second create returns `409 E_RUN_ACTIVE` |
| CORS | Allowed only for `http://localhost:5173` in development |
| Versioning | Additive changes stay in v1. Removing or renaming a field, or changing its meaning, needs v2 (§9) |

**Run states** (the `state` field and `phase` events):

- Active: `created`, `resolving`, `sampling`, `expanding`, `refining`, `mining`, `reporting`
- Terminal: `done`, `failed`, `cancelled`

## 2. Endpoint summary

| Method | Path | Purpose | Success | Priority |
| --- | --- | --- | --- | --- |
| POST | `/runs` | Start an investigation | 201 `RunCreated` | P0 |
| GET | `/runs` | List recent runs | 200 `RunSummary[]` | P1 |
| GET | `/runs/{run_id}` | Run status, plus the result once done | 200 `RunStatus` | P0 |
| POST | `/runs/{run_id}/cancel` | Stop an active run, keeping the partial result | 202 `RunStatus` | P1 |
| GET | `/runs/{run_id}/events` | Live progress stream (SSE), with history replay | 200 stream | P0 |
| GET | `/runs/{run_id}/rings/{idx}/evidence` | Who reviewed which ring place, and when | 200 `RingEvidence` | P0 |
| GET | `/runs/{run_id}/dossier` | Evidence export (`?format=md\|pdf`) | 200 file | P1 |
| GET | `/runs/{run_id}/ledger` | Every SerpApi request for the run | 200 `LedgerPage` | P0 |
| GET | `/places/search` | Candidate places for a query near a location | 200 `PlaceCandidate[]` | P1 |
| GET | `/health` | Liveness, DB status, key present, offline mode | 200 `Health` | P0 |

**Credit-spending endpoints:** only `POST /runs` and `GET /places/search` (1 credit) can spend SerpApi credits. All others read only the local database.

## 3. Runs

### 3.1 POST /runs: start an investigation

**Request**

| Field | Type | Required | Rules |
| --- | --- | --- | --- |
| `place` | string | yes | 3–2048 chars. One of: a Google Maps URL containing `0x…:0x…`, a raw `data_id`, or a `place_id` (`ChIJ…`) |
| `budget` | integer | no | 20–200, default 60. A hard ceiling on billed SerpApi credits |
| `offline` | boolean | no | Default `false`. If `true`, the run is served only from cache and makes 0 network calls |

```http
POST /api/v1/runs
Content-Type: application/json
Idempotency-Key: 7f3a2c

{"place": "https://www.google.com/maps/place/.../data=!4m6!3m5!1s0x3ba859af2f971cb5:0x2fc1c8b4bfb8a6e1!8m2...", "budget": 60}
```

**Response 201**

```json
{
  "run_id": "r_8c1e0f4a2b",
  "state": "created",
  "seed_data_id": "0x3ba859af2f971cb5:0x2fc1c8b4bfb8a6e1",
  "budget": 60,
  "offline": false,
  "links": {
    "self": "/api/v1/runs/r_8c1e0f4a2b",
    "events": "/api/v1/runs/r_8c1e0f4a2b/events",
    "ledger": "/api/v1/runs/r_8c1e0f4a2b/ledger"
  }
}
```

| Status | When | Code |
| --- | --- | --- |
| 201 | Run created and started asynchronously |  |
| 200 | Idempotent repeat; returns the original run |  |
| 400 | Unparseable place | `E_BAD_PLACE` |
| 409 | Another run is active | `E_RUN_ACTIVE` |
| 422 | Budget out of range, or a schema violation | `E_BUDGET`, `E_VALIDATION` |
| 503 | No API key and `offline=false` | `E_AUTH` |

Seed-level failures discovered after creation are delivered as an `error` event and a `failed` state, not as a create response. Examples are fewer than 20 reviews (`E_TOO_FEW_REVIEWS`) and an invalid key (`E_AUTH`). This keeps creation fast and the run auditable.

### 3.2 GET /runs/{run\_id}: status and result

The `result` field is `null` until `state = done`. A `cancelled` or `failed` run returns `partial` instead, when anything was mined.

```json
{
  "run_id": "r_8c1e0f4a2b",
  "state": "done",
  "started_at": 1791130000.1,
  "ended_at": 1791130142.7,
  "credits": {"budget": 60, "used": 57, "cached": 9},
  "error": null,
  "result": {
    "seed": {"data_id": "0x3ba8…:0x2fc1…", "title": "Example Fertility Centre", "rating": 4.8, "d_p": 412},
    "coverage": {"reviewers_sampled": 176, "reviewers_expanded": 38, "places": 3120, "edges": 5480, "low_coverage": false},
    "rings": [
      {
        "idx": 0,
        "members": ["R1", "R2", "R4", "R7", "R9", "R11", "R12", "R15", "R18", "R21", "R26"],
        "places": [{"data_id": "0x3ba8…:0x91…", "title": "Example Tiles", "d_p": 31}],
        "density": 2.41,
        "expected_overlap": 0.04,
        "observed_overlap": 7.3,
        "pval": 3.1e-7,
        "lockstep_ratio": 0.78,
        "reported": true,
        "explanation": "11 accounts share 9 places that are unrelated to this business. ..."
      }
    ],
    "rating": {"displayed": 4.8, "adjusted": 3.9, "ci": [3.6, 4.2], "sample_mean": 4.86, "n_sampled": 176},
    "no_coordination_message": null,
    "narrative": null,
    "config_hash": "a91f03c2…"
  },
  "partial": null
}
```

The values above are illustrative.

| Status | Code |
| --- | --- |
| 200 |  |
| 404 | `E_NOT_FOUND` |

### 3.3 POST /runs/{run\_id}/cancel

The server stops the crawl at the next call boundary. An in-flight SerpApi request is allowed to finish and is billed. The server then mines whatever has been collected, and moves the run to `cancelled` with `partial` populated and `coverage.low_coverage = true`.

| Status | When | Code |
| --- | --- | --- |
| 202 | Accepted; returns the current `RunStatus` |  |
| 404 | Unknown run | `E_NOT_FOUND` |
| 409 | Run already in a terminal state | `E_RUN_TERMINAL` |

### 3.4 GET /runs: list

- **Query:** `limit` (1–50, default 20), `before` (a `started_at` cursor).
- **Returns:** an array of `{run_id, state, seed_title, started_at, credits_used, rings_reported}`, newest first.

## 4. Event stream protocol (SSE)

`GET /runs/{run_id}/events` streams a run's progress as Server-Sent Events. Every event is persisted before it is sent, so any client can replay a run, finished or not, from the start.

### 4.1 Wire format

```text
id: 42
event: credit
data: {"used":23,"budget":60,"cached":4}

```

- `id` is the per-run `seq`: 1-based, gapless and strictly increasing.
- `event` is one of the types in 4.3.
- `data` is a single line of JSON.
- A heartbeat comment line `: hb` is sent every 10 s of silence.
- The server sets `Cache-Control: no-cache` and `X-Accel-Buffering: no`.

### 4.2 Replay and resume

| Request | Server behaviour |
| --- | --- |
| No `Last-Event-ID` | Sends every event from `seq` 1, then live events |
| `Last-Event-ID: n` header (browsers send it automatically on reconnect) or `?after=n` | Sends events with `seq > n`, then live events |
| Run already terminal | Sends the full history, then closes after `done`, `error` or `cancelled` |
| Unknown run | `404` JSON error, not a stream |

**Guarantees:**

- No duplicate event is delivered within one connection.
- Events arrive in `seq` order.
- The last event of a terminal run is exactly one of `done`, `error` or `cancelled`.

### 4.3 Event types

| `event` | `data` | Emitted when |
| --- | --- | --- |
| `phase` | `{phase: State, ts: number}` | Every state transition |
| `credit` | `{used: int, budget: int, cached: int}` | After every SerpApi request (billed or cached) |
| `node` | `{id: string, kind: "user"\|"place", label?: string, d_p?: int, role: "seed"\|"seed_reviewer"\|"expanded"\|"discovered"\|"refined"}` | First time a node enters the run |
| `edge` | `{u: string, p: string, rating: number, t_lo: number\|null, t_hi: number\|null, exact: bool}` | A new edge or a precision upgrade. Unknown bounds are `null` |
| `ring_update` | `{ring_idx: int, members: string[], places: string[], density: number}` | After re-peeling, when the best ring changes |
| `warning` | `{code: string, message: string}` | Non-fatal issues: a skipped contributor, a truncated profile, schema drift |
| `done` | `{run_id: string}` | Result is ready at `GET /runs/{id}` |
| `cancelled` | `{run_id: string}` | Cancel completed; `partial` is ready |
| `error` | `{code: string, message: string}` | Fatal; the run is `failed` |

**Identifiers on the stream.** `node.id` for a user is a stream pseudonym `S` + n, assigned in first-seen order. For a place, `node.id` is the `data_id`. Only place nodes carry `label`. Raw contributor IDs never appear on the stream.

The final result uses display pseudonyms `R` + n, in s0 order. Each result ring also carries `stream_members` (the `S` ids), so the client can highlight the ring on the graph it already drew without re-keying.

**Volume.** Expect 3,000 to 10,000 events per 60-credit run. Clients should batch rendering (LLD §8.4).

### 4.4 Client example

```ts
const es = new EventSource(`/api/v1/runs/${runId}/events`);
for (const t of ['phase','credit','node','edge','ring_update','warning','done','cancelled','error']) {
  es.addEventListener(t, (e: MessageEvent) => {
    handle(t, JSON.parse(e.data));
    if (t === 'done' || t === 'cancelled' || t === 'error') es.close();
  });
}
```

## 5. Dossier, evidence, ledger, place search, health

### 5.1 GET /runs/{run\_id}/rings/{idx}/evidence

This feeds the shared-place drawer in the UI. It returns `404 E_NOT_FOUND` for an unknown run or ring index, and `409 E_RUN_NOT_DONE` before mining finishes.

```json
{
  "run_id": "r_8c1e0f4a2b",
  "idx": 0,
  "places": [
    {
      "data_id": "0x3ba8…:0x91…",
      "title": "Example Tiles",
      "d_p": 31,
      "lockstep": true,
      "reviews": [
        {"member": "R1", "rating": 5, "t_lo": 1781000000, "t_hi": 1781000000, "exact": true},
        {"member": "R4", "rating": 5, "t_lo": 1780700000, "t_hi": 1783300000, "exact": false}
      ]
    }
  ]
}
```

### 5.2 GET /runs/{run\_id}/dossier?format=md|pdf

- Returns `200` with `Content-Type: text/markdown` or `application/pdf`, and `Content-Disposition: attachment; filename="nakshatra-<run_id>.<ext>"`.
- It is the only endpoint that returns raw contributor IDs. It is intended for reporting to Google or a regulator.
- Error responses:
  - `409 E_RUN_NOT_DONE` if the run has not finished
  - `415 E_FORMAT` if the format is not supported
  - `501 E_PDF_UNAVAILABLE` if WeasyPrint is not installed

### 5.3 GET /runs/{run\_id}/ledger

- **Query:** `limit` (1–500, default 200), `after` (a ledger `id`).

```json
{
  "run_id": "r_8c1e0f4a2b",
  "totals": {"billed": 57, "cached": 9, "failed": 1, "by_pool": {"sample": 12, "expand": 38, "refine": 7}},
  "items": [
    {"id": 101, "engine": "google_maps_contributor_reviews", "pool": "expand", "cached": false, "billed": true,
     "ok": true, "latency_ms": 2140, "ts": 1791130021.4, "search_id": "68f1…"}
  ],
  "next": null
}
```

The `params_hash` is deliberately not exposed. `search_id` is enough to look a call up in SerpApi's Search Archive.

### 5.4 GET /places/search (P1)

- **Query:** `q` (required, 2–200 chars), plus either `ll=@lat,lng,zoomz` or `near` (free text, appended to `q`).
- **Cost:** 1 SerpApi credit unless the result is cached. It is billed outside any run budget and is recorded in the ledger under the `sentinel run r_0000000000, which the server creates at start-up with state done`.

```json
[
  {"data_id": "0x3ba8…:0x2fc1…", "title": "Example Packers and Movers", "type": "Moving company",
   "rating": 4.9, "d_p": 640, "address": "Gandhipuram, Coimbatore", "eligible": true}
]
```

`eligible` is `false` when `d_p < 20`, and the UI disables those entries.

### 5.5 GET /health

```json
{"status": "ok", "version": "1.0.0", "schema_version": 2, "db": "ok", "api_key_present": true,
 "offline_forced": false, "active_run": null}
```

The endpoint always returns `200`. A degraded component shows `"db": "error"` or `"api_key_present": false`, so the UI can explain what is wrong instead of the request failing.

## 6. Error catalogue

Every non-2xx JSON response uses one envelope:

```json
{
  "error": {
    "code": "E_BUDGET",
    "message": "budget must be between 20 and 200",
    "details": {"field": "budget", "min": 20, "max": 200},
    "run_id": null
  }
}
```

The same `code` and `message` pair appears in `error` and `warning` SSE events. Clients branch on `code` only. `message` is for humans and may change.

| Code | HTTP | Where it surfaces | Meaning | Credits spent |
| --- | --- | --- | --- | --- |
| `E_VALIDATION` | 422 | Any request | Body or query fails the schema | 0 |
| `E_BAD_PLACE` | 400 | POST /runs | No `data_id` or `place_id` found in the input | 0 |
| `E_BUDGET` | 422 | POST /runs | Budget outside 20–200 | 0 |
| `E_RUN_ACTIVE` | 409 | POST /runs | Another run is active | 0 |
| `E_RUN_TERMINAL` | 409 | cancel | Run already finished | 0 |
| `E_RUN_NOT_DONE` | 409 | evidence, dossier | Result not ready | 0 |
| `E_NOT_FOUND` | 404 | Any `{run_id}` path | Unknown run or ring | 0 |
| `E_FORMAT` | 415 | dossier | Unsupported format | 0 |
| `E_PDF_UNAVAILABLE` | 501 | dossier | PDF renderer missing | 0 |
| `E_AUTH` | 503 at create; SSE `error` later | POST /runs, stream | Key missing or rejected by SerpApi | 0–1 |
| `E_TOO_FEW_REVIEWS` | SSE `error` | stream | Seed has fewer than 20 reviews | 1 |
| `E_QUOTA` | SSE `error` | stream | SerpApi plan exhausted | As used |
| `E_UPSTREAM` | SSE `warning` (skipped call) or `error` (a required step) | stream | SerpApi failure after 3 retries | As used |
| `E_CACHE_MISS` | SSE `error` | stream (offline) | A request was absent from the cache | 0 |
| `E_SCHEMA_DRIFT` | SSE `warning` | stream | An expected field is missing; the value is treated as unknown | 0 |
| `E_TRUNCATED` | SSE `warning` | stream | A contributor hit the 200-review cap | 0 |
| `E_INTERNAL` | 500 / SSE `error` | Anywhere | Unexpected server fault; logged with `run_id` | As used |

## 7. OpenAPI 3.1 specification

The spec is committed as `docs/openapi.yaml`. FastAPI also generates a spec at `/api/v1/openapi.json`. CI diffs the two and fails on any breaking divergence, so the code cannot drift from this contract.

```yaml
openapi: 3.1.0
info:
  title: Nakshatra API
  version: 1.0.0
  description: Local API for coordinated-review ring detection over Google Maps data retrieved via SerpApi.
servers:
  - url: http://127.0.0.1:8000/api/v1
paths:
  /runs:
    post:
      operationId: createRun
      parameters:
        - {name: Idempotency-Key, in: header, required: false, schema: {type: string, maxLength: 64}}
      requestBody:
        required: true
        content:
          application/json:
            schema: {$ref: '#/components/schemas/RunCreate'}
      responses:
        '201': {description: Created, content: {application/json: {schema: {$ref: '#/components/schemas/RunCreated'}}}}
        '200': {description: Idempotent repeat, content: {application/json: {schema: {$ref: '#/components/schemas/RunCreated'}}}}
        '400': {$ref: '#/components/responses/Error'}
        '409': {$ref: '#/components/responses/Error'}
        '422': {$ref: '#/components/responses/Error'}
        '503': {$ref: '#/components/responses/Error'}
    get:
      operationId: listRuns
      parameters:
        - {name: limit, in: query, schema: {type: integer, minimum: 1, maximum: 50, default: 20}}
        - {name: before, in: query, schema: {type: number}}
      responses:
        '200':
          description: Runs, newest first
          content:
            application/json:
              schema: {type: array, items: {$ref: '#/components/schemas/RunSummary'}}
  /runs/{run_id}:
    parameters: [{$ref: '#/components/parameters/RunId'}]
    get:
      operationId: getRun
      responses:
        '200': {description: Status, content: {application/json: {schema: {$ref: '#/components/schemas/RunStatus'}}}}
        '404': {$ref: '#/components/responses/Error'}
  /runs/{run_id}/cancel:
    parameters: [{$ref: '#/components/parameters/RunId'}]
    post:
      operationId: cancelRun
      responses:
        '202': {description: Accepted, content: {application/json: {schema: {$ref: '#/components/schemas/RunStatus'}}}}
        '404': {$ref: '#/components/responses/Error'}
        '409': {$ref: '#/components/responses/Error'}
  /runs/{run_id}/events:
    parameters:
      - {$ref: '#/components/parameters/RunId'}
      - {name: after, in: query, schema: {type: integer, minimum: 0}}
      - {name: Last-Event-ID, in: header, schema: {type: integer, minimum: 0}}
    get:
      operationId: streamEvents
      responses:
        '200':
          description: Server-Sent Events; see section 4 for event types and payloads
          content: {text/event-stream: {schema: {type: string}}}
        '404': {$ref: '#/components/responses/Error'}
  /runs/{run_id}/rings/{idx}/evidence:
    parameters:
      - {$ref: '#/components/parameters/RunId'}
      - {name: idx, in: path, required: true, schema: {type: integer, minimum: 0}}
    get:
      operationId: getRingEvidence
      responses:
        '200': {description: Evidence, content: {application/json: {schema: {$ref: '#/components/schemas/RingEvidence'}}}}
        '404': {$ref: '#/components/responses/Error'}
        '409': {$ref: '#/components/responses/Error'}
  /runs/{run_id}/dossier:
    parameters:
      - {$ref: '#/components/parameters/RunId'}
      - {name: format, in: query, schema: {type: string, enum: [md, pdf], default: md}}
    get:
      operationId: getDossier
      responses:
        '200':
          description: Dossier file
          content:
            text/markdown: {schema: {type: string}}
            application/pdf: {schema: {type: string, format: binary}}
        '409': {$ref: '#/components/responses/Error'}
        '415': {$ref: '#/components/responses/Error'}
        '501': {$ref: '#/components/responses/Error'}
  /runs/{run_id}/ledger:
    parameters:
      - {$ref: '#/components/parameters/RunId'}
      - {name: limit, in: query, schema: {type: integer, minimum: 1, maximum: 500, default: 200}}
      - {name: after, in: query, schema: {type: integer}}
    get:
      operationId: getLedger
      responses:
        '200': {description: Ledger page, content: {application/json: {schema: {$ref: '#/components/schemas/LedgerPage'}}}}
        '404': {$ref: '#/components/responses/Error'}
  /places/search:
    get:
      operationId: searchPlaces
      parameters:
        - {name: q, in: query, required: true, schema: {type: string, minLength: 2, maxLength: 200}}
        - {name: ll, in: query, schema: {type: string, pattern: '^@-?\d+(\.\d+)?,-?\d+(\.\d+)?,\d+(\.\d+)?z$'}}
        - {name: near, in: query, schema: {type: string, maxLength: 200}}
      responses:
        '200':
          description: Candidates
          content: {application/json: {schema: {type: array, items: {$ref: '#/components/schemas/PlaceCandidate'}}}}
        '422': {$ref: '#/components/responses/Error'}
  /health:
    get:
      operationId: health
      responses:
        '200': {description: Health, content: {application/json: {schema: {$ref: '#/components/schemas/Health'}}}}
components:
  parameters:
    RunId: {name: run_id, in: path, required: true, schema: {type: string, pattern: '^r_[0-9a-f]{10}$'}}
  responses:
    Error:
      description: Error envelope
      content: {application/json: {schema: {$ref: '#/components/schemas/ErrorEnvelope'}}}
  schemas:
    State:
      type: string
      enum: [created, resolving, sampling, expanding, refining, mining, reporting, done, failed, cancelled]
    RunCreate:
      type: object
      required: [place]
      additionalProperties: false
      properties:
        place: {type: string, minLength: 3, maxLength: 2048}
        budget: {type: integer, minimum: 20, maximum: 200, default: 60}
        offline: {type: boolean, default: false}
    RunCreated:
      type: object
      required: [run_id, state, budget, offline, links]
      properties:
        run_id: {type: string}
        state: {$ref: '#/components/schemas/State'}
        seed_data_id: {type: [string, 'null']}
        budget: {type: integer}
        offline: {type: boolean}
        links:
          type: object
          properties: {self: {type: string}, events: {type: string}, ledger: {type: string}}
    RunSummary:
      type: object
      required: [run_id, state, started_at, credits_used]
      properties:
        run_id: {type: string}
        state: {$ref: '#/components/schemas/State'}
        seed_title: {type: [string, 'null']}
        started_at: {type: number}
        credits_used: {type: integer}
        rings_reported: {type: integer}
    Credits:
      type: object
      required: [budget, used, cached]
      properties: {budget: {type: integer}, used: {type: integer}, cached: {type: integer}}
    RunStatus:
      type: object
      required: [run_id, state, started_at, credits]
      properties:
        run_id: {type: string}
        state: {$ref: '#/components/schemas/State'}
        started_at: {type: number}
        ended_at: {type: [number, 'null']}
        credits: {$ref: '#/components/schemas/Credits'}
        error: {oneOf: [{$ref: '#/components/schemas/ErrorBody'}, {type: 'null'}]}
        result: {oneOf: [{$ref: '#/components/schemas/Result'}, {type: 'null'}]}
        partial: {oneOf: [{$ref: '#/components/schemas/Result'}, {type: 'null'}]}
    Result:
      type: object
      required: [seed, coverage, rings, rating, config_hash]
      properties:
        seed:
          type: object
          properties:
            data_id: {type: string}
            title: {type: string}
            rating: {type: [number, 'null']}
            d_p: {type: [integer, 'null']}
        coverage:
          type: object
          properties:
            reviewers_sampled: {type: integer}
            reviewers_expanded: {type: integer}
            places: {type: integer}
            edges: {type: integer}
            low_coverage: {type: boolean}
        rings: {type: array, items: {$ref: '#/components/schemas/Ring'}}
        rating: {$ref: '#/components/schemas/Rating'}
        no_coordination_message: {type: [string, 'null']}
        narrative: {type: [string, 'null']}
        config_hash: {type: string}
    Ring:
      type: object
      required: [idx, members, stream_members, places, density, expected_overlap, observed_overlap, pval, reported, explanation]
      properties:
        idx: {type: integer}
        members: {type: array, items: {type: string, pattern: '^R[0-9]+$'}}
        stream_members: {type: array, items: {type: string, pattern: '^S[0-9]+$'}}
        places:
          type: array
          items:
            type: object
            required: [data_id, title]
            properties: {data_id: {type: string}, title: {type: string}, d_p: {type: [integer, 'null']}}
        density: {type: number}
        expected_overlap: {type: number}
        observed_overlap: {type: number}
        pval: {type: number, minimum: 0, maximum: 1}
        lockstep_ratio: {type: [number, 'null'], minimum: 0, maximum: 1}
        reported: {type: boolean}
        explanation: {type: string}
    Rating:
      type: object
      required: [displayed, adjusted, ci, n_sampled]
      properties:
        displayed: {type: [number, 'null']}
        adjusted: {type: [number, 'null']}
        ci: {type: array, minItems: 2, maxItems: 2, items: {type: [number, 'null']}}
        sample_mean: {type: [number, 'null']}
        n_sampled: {type: integer}
    RingEvidence:
      type: object
      required: [run_id, idx, places]
      properties:
        run_id: {type: string}
        idx: {type: integer}
        places:
          type: array
          items:
            type: object
            properties:
              data_id: {type: string}
              title: {type: string}
              d_p: {type: [integer, 'null']}
              lockstep: {type: boolean}
              reviews:
                type: array
                items:
                  type: object
                  properties:
                    member: {type: string}
                    rating: {type: number}
                    t_lo: {type: [number, 'null']}
                    t_hi: {type: [number, 'null']}
                    exact: {type: boolean}
    LedgerPage:
      type: object
      required: [run_id, totals, items]
      properties:
        run_id: {type: string}
        totals:
          type: object
          properties:
            billed: {type: integer}
            cached: {type: integer}
            failed: {type: integer}
            by_pool: {type: object, additionalProperties: {type: integer}}
        items:
          type: array
          items:
            type: object
            properties:
              id: {type: integer}
              engine: {type: string}
              pool: {type: [string, 'null']}
              cached: {type: boolean}
              billed: {type: boolean}
              ok: {type: boolean}
              latency_ms: {type: integer}
              ts: {type: number}
              search_id: {type: [string, 'null']}
        next: {type: [integer, 'null']}
    PlaceCandidate:
      type: object
      required: [data_id, title, eligible]
      properties:
        data_id: {type: string}
        title: {type: string}
        type: {type: [string, 'null']}
        rating: {type: [number, 'null']}
        d_p: {type: [integer, 'null']}
        address: {type: [string, 'null']}
        eligible: {type: boolean}
    Health:
      type: object
      required: [status, version, schema_version, db, api_key_present, offline_forced]
      properties:
        status: {type: string, enum: [ok, degraded]}
        version: {type: string}
        schema_version: {type: integer}
        db: {type: string, enum: [ok, error]}
        api_key_present: {type: boolean}
        offline_forced: {type: boolean}
        active_run: {type: [string, 'null']}
    ErrorBody:
      type: object
      required: [code, message]
      properties:
        code: {type: string}
        message: {type: string}
        details: {type: object}
        run_id: {type: [string, 'null']}
    ErrorEnvelope:
      type: object
      required: [error]
      properties:
        error: {$ref: '#/components/schemas/ErrorBody'}
```

## 8. Outbound contract with SerpApi

Nakshatra depends on exactly three SerpApi engines. The fields it relies on are listed below; anything else in the responses is ignored. The field names come from SerpApi's documentation, and fields marked "verify" must be confirmed in the playground on day 1.

**Endpoint:** `GET https://serpapi.com/search`. Every call carries `engine`, `api_key` (from the environment only) and `hl=en`.

### 8.1 `google_maps`: seed resolution and category baseline

| Use | Params | Fields relied on | If missing |
| --- | --- | --- | --- |
| Seed | `type=place` + place identifier (`place_id`, or `data` built from `data_id`; verify) | `place_results.data_id`, `title`, `type`, `rating`, `reviews`, `gps_coordinates` | No `data_id` → `E_BAD_PLACE`; no `reviews` → treat as < 20 |
| Baseline | `type=search`, `q=<type>`, `ll=@lat,lng,14z` | `local_results[].data_id`, `rating`, `reviews` | Empty → μ\_cat = 4.0 and a `warning` |

### 8.2 `google_maps_reviews`: seed sample and hot-place refinement

| Params | Fields relied on | Notes |
| --- | --- | --- |
| `data_id`, `sort_by` ∈ {`newestFirst`, `ratingHigh`}, `next_page_token`, `num=20` on pages after the first | `reviews[].review_id`, `rating`, `iso_date`, `iso_date_of_last_edit`, `user.contributor_id`, `user.reviews`, `user.photos`, `user.local_guide`, `snippet`; `place_info.reviews`; `serpapi_pagination.next_page_token` | The first page returns 8 results and does not accept `num`. Reviews without `contributor_id` (non-Google sources) are skipped ([docs](https://serpapi.com/google-maps-reviews-api)) |

### 8.3 `google_maps_contributor_reviews`: reviewer expansion

| Params | Fields relied on | Notes |
| --- | --- | --- |
| `contributor_id`, `num=200` | `contributor.level`, `points`, `local_guide`, `contributions.reviews`; `reviews[].review_id`, `rating`, `date` (relative string), `snippet`, `place_info.data_id`, `title`, `type`, `gps_coordinates`; `place_info.reviews` (verify, SRS OI-1) | Capped at 200 results per contributor. Dates are relative only ([docs](https://serpapi.com/google-maps-contributor-reviews-api)) |

### 8.4 Behaviour Nakshatra assumes

| Assumption | Consequence if false | Detection |
| --- | --- | --- |
| `search_metadata.status == "Success"` on success | A failed call would be cached by mistake | Response check; failed responses are never cached |
| Identical requests within 1 hour are served from SerpApi's cache at no charge | Billed counts in the ledger are over-estimates, which is the safe direction | Compare against the SerpApi dashboard after a run |
| 401 means a bad key; 429 means rate-limited | Retries could be misapplied | Status-code tests with `respx` |
| `json_restrictor` trims fields as documented | Larger cache rows; correctness unaffected | Size check in CI |

### 8.5 Change policy

- Every parser reads with `.get()` and default values. A missing required field raises `E_SCHEMA_DRIFT` as a warning, not as an exception.
- Fixture files in `tests/fixtures/serpapi/` are real cached responses for each engine. When a SerpApi release changes a shape, refresh the fixtures and rebuild the graph from the cache. No new credits are needed.

## 9. Compatibility rules and curl walkthrough

### 9.1 Compatibility

| Change | Allowed in v1? |
| --- | --- |
| Add an optional request field with a default | Yes |
| Add a response field or a new SSE event type | Yes. Clients ignore unknown fields and events |
| Add an error code | Yes. Clients treat unknown codes as generic failures |
| Add an enum value to `State` | No. It needs v2, because clients switch on state |
| Rename or remove a field, change a type or unit, change pseudonym semantics | No. It needs v2 |
| Tighten validation (a narrower budget range) | No. It needs v2 |

**Differences from the earlier documents.** This contract supersedes the following:

- the LLD's `HTTPException({"code": …})` error bodies, now the §6 envelope;
- the `?fmt=` dossier parameter, now `?format=`;
- the LLD's raw contributor IDs on the SSE stream, now `S`-pseudonyms;
- unprefixed `/api` paths, now `/api/v1` with `/api` as an alias.

Update `api/routes.py`, `report/` and `useRunStream.ts` to match.

### 9.2 Walkthrough

```bash
# 0. Health
curl -s http://127.0.0.1:8000/api/v1/health | jq

# 1. Start a run (budget 60)
RUN=$(curl -s -X POST http://127.0.0.1:8000/api/v1/runs \
  -H 'Content-Type: application/json' -H 'Idempotency-Key: demo-1' \
  -d '{"place":"0x3ba859af2f971cb5:0x2fc1c8b4bfb8a6e1","budget":60}' | jq -r .run_id)

# 2. Watch progress (Ctrl-C any time; reconnect resumes with ?after=<last id>)
curl -sN http://127.0.0.1:8000/api/v1/runs/$RUN/events

# 3. Result
curl -s http://127.0.0.1:8000/api/v1/runs/$RUN | jq '.state, .credits, .result.rating, .result.rings[0].explanation'

# 4. Evidence for the first ring
curl -s http://127.0.0.1:8000/api/v1/runs/$RUN/rings/0/evidence | jq '.places[0]'

# 5. Credit audit
curl -s http://127.0.0.1:8000/api/v1/runs/$RUN/ledger | jq .totals

# 6. Export
curl -s -o dossier.md "http://127.0.0.1:8000/api/v1/runs/$RUN/dossier?format=md"

# 7. Offline replay of the same place (0 credits)
curl -s -X POST http://127.0.0.1:8000/api/v1/runs -H 'Content-Type: application/json' \
  -d '{"place":"0x3ba859af2f971cb5:0x2fc1c8b4bfb8a6e1","budget":60,"offline":true}'
```

### 9.3 Contract tests

| Test | Asserts |
| --- | --- |
| `test_contract_openapi.py` | Generated spec ⊇ `docs/openapi.yaml`; no breaking diffs (`oasdiff`) |
| `test_contract_errors.py` | Every non-2xx response matches `ErrorEnvelope`; codes are in the §6 catalogue |
| `test_contract_sse.py` | `seq` gapless; replay with `Last-Event-ID` resumes exactly; terminal event last; no raw contributor IDs in any payload |
| `test_contract_idempotency.py` | Same key gives the same `run_id` with 200; a different key while a run is active gives 409 |
| `test_contract_offline.py` | An offline run makes 0 outbound HTTP calls (`respx` asserts none) |
