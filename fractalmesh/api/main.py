"""
FractalMesh API v6 — Full sovereign stack
Trading • Data Oracle • Outreach • AI Cascade • Market Data • TTS • Firebase
"""

import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import (
    leads, affiliate, email_campaigns, seo,
    openrouter_routes, alerts, products, webhooks,
    github, devto, ai, ledger, stripe_connect,
    monitoring, automation_routes,
    market_data, printful_routes, telegram_routes,
    trading, oracle, outreach, lba, firebase_routes, tts_routes,
)
from integrations import slack
from agents.automation import start_all_jobs

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    tasks = start_all_jobs()
    slack.send("FractalMesh v6 ONLINE — 8 automation jobs active", level="info",
               fields={"port": os.environ.get("PORT", "8080"), "jobs": str(len(tasks))})
    try:
        from integrations.telegram_bot import alert
        alert("FractalMesh v6", "All systems online — trading, oracle, outreach, RSS active", "OK")
    except Exception:
        pass
    yield
    for t in tasks:
        t.cancel()
    slack.send("FractalMesh shutting down", level="warn")


app = FastAPI(
    title="FractalMesh API",
    version="6.0.0",
    description=(
        "Sovereign autonomous revenue stack — "
        "Trading · Data Oracle · AI Cascade · Outreach · "
        "Market Data · Print-on-Demand · TTS · Firebase"
    ),
    lifespan=lifespan,
)

app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

# ── Revenue ────────────────────────────────────────────────────────────────
app.include_router(leads.router)
app.include_router(affiliate.router)
app.include_router(email_campaigns.router)
app.include_router(seo.router)
app.include_router(products.router)
app.include_router(webhooks.router)
app.include_router(stripe_connect.router)

# ── Automation & monitoring ────────────────────────────────────────────────
app.include_router(automation_routes.router)
app.include_router(monitoring.router)

# ── AI layer ───────────────────────────────────────────────────────────────
app.include_router(ai.router)               # Venice · OpenAI · Gemini · xAI · GitHub · unified
app.include_router(openrouter_routes.router)

# ── Trading ────────────────────────────────────────────────────────────────
app.include_router(trading.router)

# ── Data oracle ────────────────────────────────────────────────────────────
app.include_router(oracle.router)

# ── Outreach & LBA ────────────────────────────────────────────────────────
app.include_router(outreach.router)
app.include_router(lba.router)

# ── Market data ────────────────────────────────────────────────────────────
app.include_router(market_data.router)

# ── Print-on-demand ────────────────────────────────────────────────────────
app.include_router(printful_routes.router)

# ── Comms ─────────────────────────────────────────────────────────────────
app.include_router(telegram_routes.router)
app.include_router(tts_routes.router)

# ── Firebase ───────────────────────────────────────────────────────────────
app.include_router(firebase_routes.router)

# ── Dev integrations ──────────────────────────────────────────────────────
app.include_router(alerts.router)
app.include_router(github.router)
app.include_router(devto.router)
app.include_router(ledger.router)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "version": "6.0.0",
        "entity": os.getenv("ENTITY", "IronVision Nexus"),
        "abn": os.getenv("ABN", "56628117363"),
    }
