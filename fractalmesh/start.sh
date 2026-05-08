#!/usr/bin/env bash
# FractalMesh v6 — Sovereign Autonomous Revenue Stack
# IronVision Nexus | ABN 56628117363 | Samuel James Hiotis
# Usage: ./start.sh [--full | --api-only | --help]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

C='\033[0;36m'; G='\033[0;32m'; Y='\033[1;33m'; NC='\033[0m'

[ -f ".env" ] && { set -a; source .env; set +a; echo -e "${G}[ok] .env loaded${NC}"; } \
              || echo -e "${Y}[warn] .env not found — using environment${NC}"

PORT="${PORT:-8080}"
mkdir -p logs

# ── Dependency check ──────────────────────────────────────────────────────
python3 -c "import fastapi, uvicorn" 2>/dev/null \
    || pip install -q -r requirements.txt

# Try ccxt for trading
python3 -c "import ccxt" 2>/dev/null \
    || pip install -q ccxt 2>/dev/null || true

# ── Functions ──────────────────────────────────────────────────────────────
start_api() {
    echo -e "${C}[api] starting FractalMesh v6 on :$PORT...${NC}"
    uvicorn api.main:app \
        --host 0.0.0.0 \
        --port "$PORT" \
        --workers 1 \
        --log-level info \
        > logs/api.log 2>&1 &
    API_PID=$!
    echo -e "${G}[api] pid=$API_PID${NC}"
}

start_ngrok() {
    if command -v ngrok &>/dev/null && [ -n "${NGROK_AUTHTOKEN:-}" ]; then
        ngrok authtoken "$NGROK_AUTHTOKEN" --log=false 2>/dev/null || true
        ngrok http "$PORT" --log stdout > logs/ngrok.log 2>&1 &
        sleep 3
        TUNNEL=$(python3 -c "
import urllib.request, json
try:
    d = json.loads(urllib.request.urlopen('http://localhost:4040/api/tunnels').read())
    print(d['tunnels'][0]['public_url'])
except: print('tunnel unavailable')
" 2>/dev/null)
        echo -e "${G}[ngrok] $TUNNEL${NC}"
    else
        TUNNEL="(ngrok not configured)"
    fi
}

print_banner() {
    sleep 1
    echo ""
    echo -e "${Y}╔══════════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${Y}║        FRACTALMESH v6 — SOVEREIGN AUTONOMOUS REVENUE STACK          ║${NC}"
    echo -e "${Y}║        IronVision Nexus | ABN 56628117363 | Samuel James Hiotis     ║${NC}"
    echo -e "${Y}╠══════════════════════════════════════════════════════════════════════╣${NC}"
    echo -e "${C}║  DASHBOARD    http://localhost:$PORT/monitor/dashboard               ║${NC}"
    echo -e "${C}║  API DOCS     http://localhost:$PORT/docs                            ║${NC}"
    echo -e "${C}║  HEALTH       http://localhost:$PORT/health                          ║${NC}"
    echo -e "${Y}╠══════════════════════════════════════════════════════════════════════╣${NC}"
    echo -e "${C}║  AI CASCADE (Venice→OpenAI→Gemini→OpenRouter→xAI→GitHub)            ║${NC}"
    echo    "║  POST /ai/unified       — best available AI                          ║"
    echo    "║  POST /ai/venice        — Venice AI (llama-3.3-70b, deepseek-r1)    ║"
    echo    "║  POST /ai/openai        — GPT-4o-mini                                ║"
    echo    "║  POST /ai/gemini        — Gemini 2.0 Flash (auto key rotation)       ║"
    echo    "║  POST /ai/xai           — Grok-3                                     ║"
    echo    "║  POST /ai/github        — Phi-4 multimodal                           ║"
    echo    "║  POST /openrouter/complete — 160+ free models                        ║"
    echo -e "${Y}╠══════════════════════════════════════════════════════════════════════╣${NC}"
    echo -e "${C}║  TRADING (KuCoin + Crypto.com via ccxt)                             ║${NC}"
    echo    "║  GET  /trading/status          — circuit breaker, mode, exchanges    ║"
    echo    "║  GET  /trading/balances        — live account balances               ║"
    echo    "║  GET  /trading/ticker          — live ticker                         ║"
    echo    "║  POST /trading/order           — place market order                  ║"
    echo    "║  POST /trading/strategy/{name} — run strategy                        ║"
    echo    "║  POST /trading/run-all         — all strategies cycle                ║"
    echo    "║  GET  /trading/history         — trade log                           ║"
    echo -e "${Y}╠══════════════════════════════════════════════════════════════════════╣${NC}"
    echo -e "${C}║  DATA ORACLE (WiGLE RF + Copernicus satellite)                      ║${NC}"
    echo    "║  GET  /oracle/rf               — WiGLE network extract               ║"
    echo    "║  GET  /oracle/dem              — Copernicus DEM metadata             ║"
    echo    "║  GET  /oracle/datasets         — packaged data archives               ║"
    echo    "║  POST /oracle/run-cycle        — full extract + package              ║"
    echo -e "${Y}╠══════════════════════════════════════════════════════════════════════╣${NC}"
    echo -e "${C}║  REVENUE STACK                                                       ║${NC}"
    echo    "║  GET  /leads                   — tiered dataset (token-gated)        ║"
    echo    "║  GET  /leads/feed.xml          — premium gated RSS feed              ║"
    echo    "║  POST /leads/subscribe         — create subscriber + token           ║"
    echo    "║  POST /affiliate/register      — onboard affiliate partner           ║"
    echo    "║  POST /products/checkout       — Stripe checkout                     ║"
    echo    "║  GET  /market/prices           — CoinGecko AUD prices                ║"
    echo    "║  GET  /market/trending         — top trending coins                  ║"
    echo    "║  GET  /printful/products       — print-on-demand catalog             ║"
    echo    "║  POST /printful/orders         — create Printful order               ║"
    echo -e "${Y}╠══════════════════════════════════════════════════════════════════════╣${NC}"
    echo -e "${C}║  OUTREACH & COMMS                                                    ║${NC}"
    echo    "║  GET  /outreach/reddit         — scrape Reddit for-hire leads        ║"
    echo    "║  POST /outreach/run-cycle      — auto-stage pitches                  ║"
    echo    "║  POST /telegram/broadcast      — send Telegram alert                 ║"
    echo    "║  POST /tts/speak               — ElevenLabs TTS → MP3               ║"
    echo    "║  POST /firebase/metrics        — push to Firebase RTDB               ║"
    echo    "║  GET  /lba/identity            — sovereign ABN identity              ║"
    echo -e "${Y}╠══════════════════════════════════════════════════════════════════════╣${NC}"
    echo -e "${C}║  AUTOMATION (continuous background jobs)                             ║${NC}"
    echo    "║  Every 15m  RSS + arxiv + HF + HN + DEV.to + CoinGecko ingest      ║"
    echo    "║  Every 30m  AI lead enrichment + rescore                             ║"
    echo    "║  Every 1h   Trading cycle (all strategies)                           ║"
    echo    "║  Every 2h   WiGLE RF oracle + DEM extraction                        ║"
    echo    "║  Every 2h   Reddit outreach cycle                                    ║"
    echo    "║  Every 5m   Metrics → Supabase + Firebase + Make + Zapier           ║"
    echo    "║  Every 6h   DEV.to digest publish                                    ║"
    echo    "║  Every 24h  Affiliate report → Slack + Telegram                      ║"
    echo -e "${Y}╚══════════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

case "${1:---full}" in
    --api-only) start_api; print_banner ;;
    --help)
        echo "Usage: ./start.sh [--full | --api-only | --help]"
        echo "  --full      Start API + ngrok tunnel (default)"
        echo "  --api-only  Start API only"
        exit 0
        ;;
    --full|*)
        start_api
        start_ngrok
        print_banner
        ;;
esac

wait
