#!/usr/bin/env bash
# FractalMesh v3 — master startup
# Usage: ./start.sh [--full | --api-only | --rss-only]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -f ".env" ]; then
    set -a; source .env; set +a
    echo "[ok] .env loaded"
else
    echo "[warn] .env not found"
fi

PORT="${PORT:-8080}"
MODE="${1:---full}"
mkdir -p logs

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
        ngrok http "$PORT" --log stdout > logs/ngrok.log 2>&1 &
        echo "[ngrok] pid=$! — check logs/ngrok.log for public URL"
    else
        echo "[ngrok] skipped"
    fi
}

start_rss() {
    echo "[rss] starting swarm (poll=${RSS_POLL_SECS:-900}s)..."
    python3 -m agents.rss_swarm > logs/rss.log 2>&1 &
    echo "[rss] pid=$!"
}

case "$MODE" in
    --api-only)   start_api; start_ngrok ;;
    --rss-only)   start_rss ;;
    --full|*)     start_api; start_ngrok; start_rss ;;
esac

sleep 1
echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║  FractalMesh v3 — Zero-Capital Revenue Stack LIVE               ║"
echo "╠══════════════════════════════════════════════════════════════════╣"
echo "║  REVENUE ENDPOINTS                                               ║"
echo "║  GET  /leads              — tiered dataset (public/auth)        ║"
echo "║  GET  /leads/feed.xml     — premium RSS feed (subscriber only)  ║"
echo "║  POST /leads/ingest       — trigger RSS harvest                 ║"
echo "║  POST /leads/subscribe    — create subscriber + access token    ║"
echo "║  POST /affiliate/register — onboard new affiliate               ║"
echo "║  GET  /affiliate/dashboard— affiliate stats (bearer token)      ║"
echo "║  GET  /affiliate/leaderboard — public commission leaderboard    ║"
echo "║  GET  /email/campaigns    — list email campaigns                ║"
echo "║  POST /email/campaigns    — create campaign                     ║"
echo "║  POST /email/campaigns/{id}/send — send via Gmail               ║"
echo "║  POST /email/contacts     — add outreach contact                ║"
echo "║  POST /email/contacts/import — bulk import contacts             ║"
echo "║  POST /seo/analyze        — full SEO + affiliate angle report   ║"
echo "║  POST /seo/meta-tags      — generate SEO meta tags             ║"
echo "╠══════════════════════════════════════════════════════════════════╣"
echo "║  AI / LLM                                                        ║"
echo "║  POST /openrouter/complete— free LLM completions (160+ models)  ║"
echo "║  GET  /openrouter/free-models — list free models                ║"
echo "║  POST /ai/github          — GitHub Models (Phi-4 etc.)          ║"
echo "║  POST /ai/xai             — Grok-3                              ║"
echo "╠══════════════════════════════════════════════════════════════════╣"
echo "║  PAYMENTS                                                        ║"
echo "║  GET  /products           — Stripe products                     ║"
echo "║  POST /products/checkout  — create checkout session             ║"
echo "║  POST /connect/account    — Stripe Connect account              ║"
echo "║  POST /connect/transfer   — transfer funds                      ║"
echo "║  POST /webhooks/stripe    — Stripe webhook                      ║"
echo "╠══════════════════════════════════════════════════════════════════╣"
echo "║  DOCS: http://localhost:$PORT/docs                              ║"
echo "╚══════════════════════════════════════════════════════════════════╝"

wait
