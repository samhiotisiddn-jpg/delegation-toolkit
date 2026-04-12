#!/usr/bin/env bash
# FractalMesh — master startup script
# Usage: ./start.sh [--api-only | --trade-only | --full]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Load .env if present
if [ -f ".env" ]; then
    set -a; source .env; set +a
    echo "[ok] .env loaded"
else
    echo "[warn] no .env found — expecting environment variables to be set externally"
fi

PORT="${PORT:-8080}"
MODE="${1:---full}"

# Install dependencies if needed
if ! python3 -c "import fastapi" 2>/dev/null; then
    echo "[setup] installing python dependencies..."
    pip install -q -r requirements.txt
fi

start_api() {
    echo "[api] starting FastAPI on port $PORT..."
    uvicorn api.main:app --host 0.0.0.0 --port "$PORT" --reload &
    API_PID=$!
    echo "[api] pid=$API_PID"
}

start_ngrok() {
    if command -v ngrok &>/dev/null && [ -n "${NGROK_AUTHTOKEN:-}" ]; then
        echo "[ngrok] starting tunnel → port $PORT..."
        ngrok start --config ngrok.yml --all > logs/ngrok.log 2>&1 &
        NGROK_PID=$!
        echo "[ngrok] pid=$NGROK_PID"
        sleep 2
        TUNNEL_URL=$(curl -s http://localhost:4040/api/tunnels 2>/dev/null \
            | python3 -c "import sys,json; t=json.load(sys.stdin)['tunnels']; print(t[0]['public_url'] if t else '')" 2>/dev/null || echo "unavailable")
        echo "[ngrok] public url: $TUNNEL_URL"
    else
        echo "[ngrok] skipped (not installed or NGROK_AUTHTOKEN not set)"
    fi
}

start_trading() {
    echo "[trading] starting arbitrage engine (DRY_RUN=${DRY_RUN:-true})..."
    python3 -m trading.arbitrage > logs/trading.log 2>&1 &
    TRADE_PID=$!
    echo "[trading] pid=$TRADE_PID"
}

mkdir -p logs

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

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  FractalMesh LIVE                                    ║"
echo "║  API:      http://localhost:$PORT                    ║"
echo "║  Docs:     http://localhost:$PORT/docs               ║"
echo "║  Health:   http://localhost:$PORT/health             ║"
echo "╚══════════════════════════════════════════════════════╝"

wait
