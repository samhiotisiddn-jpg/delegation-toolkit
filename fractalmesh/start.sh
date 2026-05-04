#!/usr/bin/env bash
# FractalMesh — master startup
# Usage: ./start.sh [--full | --api-only | --trade-only]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Load .env
if [ -f ".env" ]; then
    set -a; source .env; set +a
    echo "[ok] .env loaded"
else
    echo "[warn] .env not found — set env vars externally"
fi

PORT="${PORT:-8080}"
MODE="${1:---full}"
mkdir -p logs

# Install python deps if missing
if ! python3 -c "import fastapi" 2>/dev/null; then
    echo "[setup] installing dependencies..."
    pip install -q -r requirements.txt
fi

start_api() {
    echo "[api] starting on :$PORT..."
    uvicorn api.main:app --host 0.0.0.0 --port "$PORT" > logs/api.log 2>&1 &
    echo "[api] pid=$!"
}

start_ngrok() {
    if command -v ngrok &>/dev/null && [ -n "${NGROK_AUTHTOKEN:-}" ]; then
        ngrok authtoken "$NGROK_AUTHTOKEN" --log=false 2>/dev/null || true
        echo "[ngrok] starting tunnel → :$PORT"
        ngrok http "$PORT" --config ngrok.yml --log stdout > logs/ngrok.log 2>&1 &
        echo "[ngrok] pid=$! — tail logs/ngrok.log for public URL"
    else
        echo "[ngrok] skipped (install ngrok or set NGROK_AUTHTOKEN)"
    fi
}

start_trading() {
    echo "[trading] starting arbitrage engine (DRY_RUN=${DRY_RUN:-true})..."
    python3 -m trading.arbitrage > logs/trading.log 2>&1 &
    echo "[trading] pid=$!"
}

case "$MODE" in
    --api-only)
        start_api
        start_ngrok
        ;;
    --trade-only)
        start_trading
        ;;
    --full|*)
        start_api
        start_ngrok
        start_trading
        ;;
esac

sleep 1
echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  FractalMesh v2.0 LIVE                                       ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║  API docs:     http://localhost:$PORT/docs                   ║"
echo "║  Health:       http://localhost:$PORT/health                 ║"
echo "║                                                              ║"
echo "║  ENDPOINTS                                                   ║"
echo "║  GET  /trades                 — arbitrage trade log         ║"
echo "║  GET  /alerts                 — system alert log            ║"
echo "║  POST /alerts                 — create alert                ║"
echo "║  GET  /products               — Stripe products             ║"
echo "║  POST /products/checkout      — Stripe checkout session     ║"
echo "║  POST /webhooks/stripe        — Stripe webhook receiver     ║"
echo "║  POST /webhooks/make          — Make.com webhook receiver   ║"
echo "║  GET  /github/commits         — repo commit feed            ║"
echo "║  GET  /github/releases        — repo release feed           ║"
echo "║  GET  /devto/articles         — DEV.to articles             ║"
echo "║  POST /devto/publish          — publish to DEV.to           ║"
echo "║  POST /devto/publish-trade-summary — auto trade article     ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║  LOGS: logs/api.log  logs/trading.log  logs/ngrok.log       ║"
echo "╚══════════════════════════════════════════════════════════════╝"

wait
