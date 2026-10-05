#!/usr/bin/env bash
# Run Nakshatra locally: backend (FastAPI, :8000) + frontend (Vite, :5173), then open the browser.
#
#   ./run.sh            live mode: uses SERPAPI_API_KEY from .env (each investigation spends SerpApi credits)
#   ./run.sh --replay   demo mode: shipped data/demo.db, no key, offline, 0 credits
#
# Ctrl-C stops both servers.
set -euo pipefail
cd "$(dirname "$0")"

API_PORT=8000
WEB_PORT=5173
MODE=live
[[ "${1:-}" == "--replay" ]] && MODE=replay
[[ "${1:-}" == "-h" || "${1:-}" == "--help" ]] && { sed -n '2,7p' "$0" | sed 's/^# \{0,1\}//'; exit 0; }

say() { printf '\033[1m%s\033[0m\n' "$*"; }
die() { printf '\033[31m%s\033[0m\n' "$*" >&2; exit 1; }

# ---- prerequisites ----
command -v uv >/dev/null || die "uv is not installed: https://docs.astral.sh/uv/getting-started/installation/"
command -v npm >/dev/null || die "Node.js (npm) is not installed: https://nodejs.org (version 20 or newer)"
command -v curl >/dev/null || die "curl is needed to check that the servers are up"
for port in "$API_PORT" "$WEB_PORT"; do
  if curl -s -o /dev/null "http://127.0.0.1:$port"; then
    die "Port $port is already in use. Stop whatever is running there (maybe an earlier ./run.sh) and try again."
  fi
done

# ---- dependencies (fast no-ops after the first run) ----
say "Installing dependencies (first run takes a minute)..."
uv sync --extra pdf --quiet
(cd web && npm install --silent --no-audit --no-fund)

# ---- mode ----
if [[ "$MODE" == "replay" ]]; then
  [[ -f data/demo.db ]] || die "data/demo.db is missing."
  cp data/demo.db data/replay.db  # keep the shipped file unchanged
  export SERPAPI_API_KEY="" NAKSHATRA_OFFLINE=1 NAKSHATRA_DB=data/replay.db
  say "Replay mode: shipped demo data, offline, 0 credits."
else
  if [[ ! -f .env ]] || ! grep -qE '^SERPAPI_API_KEY=.+' .env; then
    say "No SERPAPI_API_KEY in .env: the app will only replay cached runs. (cp .env.example .env, then add your key)"
  else
    say "Live mode: investigations spend SerpApi credits (default budget 60)."
  fi
fi

# ---- start both, stop both on exit ----
PIDS=()
cleanup() {
  trap - EXIT INT TERM
  say "Stopping..."
  for pid in "${PIDS[@]}"; do kill "$pid" 2>/dev/null || true; done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

uv run uvicorn nakshatra.api.main:app --host 127.0.0.1 --port "$API_PORT" --log-level warning &
PIDS+=($!)
(cd web && exec npx vite --host 127.0.0.1 --port "$WEB_PORT" --strictPort --logLevel warn) &
PIDS+=($!)

wait_for() {  # url, name
  for _ in $(seq 1 60); do
    curl -s -o /dev/null "$1" && return 0
    for pid in "${PIDS[@]}"; do kill -0 "$pid" 2>/dev/null || die "$2 failed to start (see the output above)."; done
    sleep 0.5
  done
  die "$2 did not start within 30 s."
}
wait_for "http://127.0.0.1:$API_PORT/api/v1/health" "The backend"
wait_for "http://127.0.0.1:$WEB_PORT/" "The frontend"

URL="http://127.0.0.1:$WEB_PORT/"
say "Nakshatra is running: $URL   (API: http://127.0.0.1:$API_PORT/api/v1/docs)   Ctrl-C to stop."
if command -v xdg-open >/dev/null; then xdg-open "$URL" >/dev/null 2>&1 || true
elif command -v open >/dev/null; then open "$URL" || true
else say "Open $URL in your browser."
fi

wait -n "${PIDS[@]}"  # if either server exits, stop the other
