#!/usr/bin/env bash
# FractalMesh v4 — zero-capital revenue stack
# Usage: ./start.sh [--full | --api-only]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

[ -f ".env" ] && { set -a; source .env; set +a; echo "[ok] .env loaded"; } \
              || echo "[warn] .env not found"

PORT="${PORT:-8080}"
mkdir -p logs

python3 -c "import fastapi" 2>/dev/null || pip install -q -r requirements.txt

start_api() {
    echo "[api] starting on :$PORT..."
    uvicorn api.main:app --host 0.0.0.0 --port "$PORT" > logs/api.log 2>&1 &
    echo "[api] pid=$! — all automation runs inside the API process"
}

start_ngrok() {
    if command -v ngrok &>/dev/null && [ -n "${NGROK_AUTHTOKEN:-}" ]; then
        ngrok authtoken "$NGROK_AUTHTOKEN" --log=false 2>/dev/null || true
        ngrok http "$PORT" --log stdout > logs/ngrok.log 2>&1 &
        sleep 2
        TUNNEL=$(python3 -c "
import urllib.request, json
try:
    d = json.loads(urllib.request.urlopen('http://localhost:4040/api/tunnels').read())
    print(d['tunnels'][0]['public_url'])
except: print('check logs/ngrok.log')
" 2>/dev/null)
        echo "[ngrok] public URL: $TUNNEL"
    fi
}

case "${1:---full}" in
    --api-only) start_api ;;
    --full|*)   start_api; start_ngrok ;;
esac

sleep 1
echo ""
echo "╔═══════════════════════════════════════════════════════════════════╗"
echo "║  FractalMesh v4 — Zero-Capital Revenue Stack                      ║"
echo "╠═══════════════════════════════════════════════════════════════════╣"
echo "║  DASHBOARD:  http://localhost:$PORT/monitor/dashboard             ║"
echo "║  API DOCS:   http://localhost:$PORT/docs                          ║"
echo "╠═══════════════════════════════════════════════════════════════════╣"
echo "║  REVENUE                                                           ║"
echo "║  GET  /leads                   tiered dataset (token-gated)       ║"
echo "║  GET  /leads/feed.xml          premium gated RSS feed             ║"
echo "║  POST /leads/subscribe         create subscriber + token          ║"
echo "║  POST /affiliate/register      onboard affiliate partner          ║"
echo "║  GET  /affiliate/dashboard     commission stats                   ║"
echo "║  POST /products/checkout       Stripe checkout                    ║"
echo "║  POST /connect/account         Stripe Connect onboarding          ║"
echo "╠═══════════════════════════════════════════════════════════════════╣"
echo "║  AUTOMATION (runs continuously in background)                      ║"
echo "║  Every 15m  RSS ingest + HN + DEV.to + GitHub trending           ║"
echo "║  Every 30m  AI lead enrichment + rescore                          ║"
echo "║  Every 6h   DEV.to digest auto-publish (draft)                   ║"
echo "║  Every 24h  Affiliate performance report → Slack                  ║"
echo "║  Every 5m   Metrics snapshot → Supabase + Make.com               ║"
echo "╠═══════════════════════════════════════════════════════════════════╣"
echo "║  AI GATEWAY                                                        ║"
echo "║  POST /ai/unified   Venice→OpenRouter→xAI→GitHub cascade         ║"
echo "║  POST /ai/venice    Venice AI (llama-3.3-70b etc.)               ║"
echo "║  POST /ai/xai       Grok-3                                        ║"
echo "║  POST /ai/github    Phi-4 multimodal                              ║"
echo "║  POST /openrouter/complete  160+ free models                      ║"
echo "╠═══════════════════════════════════════════════════════════════════╣"
echo "║  EMAIL & SEO                                                       ║"
echo "║  POST /email/campaigns/{id}/send  Gmail SMTP campaign             ║"
echo "║  POST /email/contacts/import      bulk contact import             ║"
echo "║  POST /seo/analyze                readability+affiliate angles    ║"
echo "║  POST /automation/outreach-email  AI-written affiliate email      ║"
echo "║  POST /automation/digest          publish DEV.to digest now       ║"
echo "╚═══════════════════════════════════════════════════════════════════╝"

wait
