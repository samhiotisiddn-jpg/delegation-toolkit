"""
FractalMesh API v4 — Full monetisation + automation stack
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
)
from integrations import slack
from integrations.github_monitor import alert_new_commits
from agents.automation import start_all_jobs

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    tasks = start_all_jobs()
    slack.send("FractalMesh v4 online — all automation active", level="info",
               fields={"port": os.environ.get("PORT", "8080"),
                       "jobs": str(len(tasks))})
    yield
    for t in tasks:
        t.cancel()
    slack.send("FractalMesh shutting down", level="warn")


app = FastAPI(
    title="FractalMesh API",
    version="4.0.0",
    description="Zero-capital revenue stack: RSS datasets, affiliates, SEO, email outreach",
    lifespan=lifespan,
)

app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

# ── Revenue ────────────────────────────────────────────────────────────────
app.include_router(leads.router)
app.include_router(affiliate.router)
app.include_router(email_campaigns.router)
app.include_router(seo.router)

# ── Automation & monitoring ────────────────────────────────────────────────
app.include_router(automation_routes.router)
app.include_router(monitoring.router)

# ── AI layer ───────────────────────────────────────────────────────────────
app.include_router(ai.router)               # Venice, xAI, GitHub, unified
app.include_router(openrouter_routes.router)

# ── Payments ───────────────────────────────────────────────────────────────
app.include_router(products.router)
app.include_router(webhooks.router)
app.include_router(stripe_connect.router)

# ── Integrations ───────────────────────────────────────────────────────────
app.include_router(alerts.router)
app.include_router(github.router)
app.include_router(devto.router)
app.include_router(ledger.router)


@app.get("/health")
def health():
    return {"status": "ok", "version": "4.0.0"}
