#!/usr/bin/env bash
# One-command relaunch of the LIVE testable stack:
#
#   uvicorn  (backend, localhost:8000)
#       │
#   cloudflared quick tunnel ──> https://<random>.trycloudflare.com  ← phone hits this for /artworks etc.
#
#   next dev (mobile, localhost:3000, reads NEXT_PUBLIC_BACKEND_BASE_URL = backend tunnel URL)
#       │
#   cloudflared quick tunnel ──> https://<random>.trycloudflare.com  ← user opens this on their phone
#
# Why two tunnels and not Vercel: avoids a cloud account / interactive auth.
# Cloudflare quick tunnels are free, give HTTPS (required for iOS mic/camera
# permission on non-localhost), and support WebSocket upgrades for /voice/ws.
#
# Quirks:
# - Quick tunnel URLs change on every restart. Both URLs are printed below
#   when ready; the mobile URL is the only one you need on the phone.
# - The mobile dev server bakes NEXT_PUBLIC_BACKEND_BASE_URL into the JS at
#   start time, so it MUST be relaunched whenever the backend tunnel URL
#   changes. This script handles that for you.
# - Ctrl-C tears all four processes down cleanly.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="${TMPDIR:-/tmp}/asu-museum-dev"
mkdir -p "$LOG_DIR"

# Trim any stale processes that might own our ports — better to fail fast
# than to silently bind to something else.
free_port() {
  local port=$1
  local pids
  pids=$(lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null || true)
  if [ -n "$pids" ]; then
    echo "  freeing port $port (killing PIDs: $pids)"
    echo "$pids" | xargs -r kill -9 2>/dev/null || true
    sleep 1
  fi
}

cleanup() {
  echo
  echo "Tearing down…"
  for pid in ${BACKEND_PID:-} ${BACKEND_TUNNEL_PID:-} ${MOBILE_PID:-} ${MOBILE_TUNNEL_PID:-}; do
    [ -n "$pid" ] && kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
  echo "Done."
}
trap cleanup EXIT INT TERM

echo "Logs: $LOG_DIR"
free_port 8000
free_port 3000

# 1. Backend ─────────────────────────────────────────────────────────────
echo "Starting backend (uvicorn)…"
(
  cd "$ROOT/Backend"
  source venv/bin/activate
  exec uvicorn main:app --port 8000 --log-level info
) > "$LOG_DIR/backend.log" 2>&1 &
BACKEND_PID=$!

# Wait for /health to respond.
for i in $(seq 1 60); do
  if curl -fsS http://localhost:8000/health >/dev/null 2>&1; then
    echo "  backend up"
    break
  fi
  sleep 0.5
done

# 2. Backend tunnel ──────────────────────────────────────────────────────
echo "Opening backend tunnel…"
cloudflared tunnel --url http://localhost:8000 --no-autoupdate \
  > "$LOG_DIR/cloudflared-backend.log" 2>&1 &
BACKEND_TUNNEL_PID=$!

BACKEND_URL=""
for i in $(seq 1 30); do
  BACKEND_URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' \
    "$LOG_DIR/cloudflared-backend.log" 2>/dev/null | head -1 || true)
  [ -n "$BACKEND_URL" ] && break
  sleep 0.5
done
if [ -z "$BACKEND_URL" ]; then
  echo "ERROR: backend tunnel didn't print a URL. tail:"
  tail -20 "$LOG_DIR/cloudflared-backend.log"
  exit 1
fi
# Wait until the tunnel URL is actually reachable (DNS + first connection
# can lag a few seconds after the URL line is printed).
for i in $(seq 1 30); do
  if curl -fsS --max-time 5 "$BACKEND_URL/health" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
echo "  backend tunnel: $BACKEND_URL"

# 3. Mobile dev (with backend tunnel URL baked in) ───────────────────────
echo "Starting mobile dev (next dev)…"
(
  cd "$ROOT/MobileApp"
  export NEXT_PUBLIC_BACKEND_BASE_URL="$BACKEND_URL"
  exec npm run dev
) > "$LOG_DIR/mobile.log" 2>&1 &
MOBILE_PID=$!

for i in $(seq 1 60); do
  if curl -fsS http://localhost:3000 -o /dev/null 2>&1; then
    echo "  mobile up"
    break
  fi
  sleep 0.5
done

# 4. Mobile tunnel ───────────────────────────────────────────────────────
echo "Opening mobile tunnel…"
cloudflared tunnel --url http://localhost:3000 --no-autoupdate \
  > "$LOG_DIR/cloudflared-mobile.log" 2>&1 &
MOBILE_TUNNEL_PID=$!

MOBILE_URL=""
for i in $(seq 1 30); do
  MOBILE_URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' \
    "$LOG_DIR/cloudflared-mobile.log" 2>/dev/null | head -1 || true)
  [ -n "$MOBILE_URL" ] && break
  sleep 0.5
done
if [ -z "$MOBILE_URL" ]; then
  echo "ERROR: mobile tunnel didn't print a URL."
  exit 1
fi
echo "  mobile tunnel:  $MOBILE_URL"

cat <<EOF

────────────────────────────────────────────────────────────────────────
  📱 Open this on your phone:
       $MOBILE_URL

  Backend (for curl debugging):
       $BACKEND_URL

  Logs streaming to: $LOG_DIR/
       backend.log   mobile.log   cloudflared-backend.log   cloudflared-mobile.log

  Press Ctrl-C to stop everything.
────────────────────────────────────────────────────────────────────────
EOF

# Block on any subprocess; if any dies, exit and let the trap clean up.
wait -n "$BACKEND_PID" "$BACKEND_TUNNEL_PID" "$MOBILE_PID" "$MOBILE_TUNNEL_PID" 2>/dev/null
echo "A subprocess exited; shutting down the rest."
