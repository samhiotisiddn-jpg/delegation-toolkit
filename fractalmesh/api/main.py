"""
FractalMesh API v3 — RSS dataset, affiliate marketing, email outreach, SEO
"""

import os
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import (
    leads, affiliate, email_campaigns, seo,
    openrouter_routes, alerts, products, webhooks,
    github, devto, ai, ledger, stripe_connect,
)
from integrations import slack
from integrations.github_monitor import alert_new_commits
from datetime import datetime, timezone, timedelta

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s")

_GITHUB_POLL = 300
_RSS_POLL    = int(os.environ.get("RSS_POLL_SECS", "900"))


async def _github_poller():
    await asyncio.sleep(15)
    while True:
        try:
            since = (datetime.now(timezone.utc) - timedelta(seconds=_GITHUB_POLL)).isoformat()
            alert_new_commits(since)
        except Exception as exc:
            logging.warning("github poller: %s", exc)
        await asyncio.sleep(_GITHUB_POLL)


async def _rss_poller():
    await asyncio.sleep(30)
    while True:
        try:
            from agents.rss_swarm import ingest_once
            n = ingest_once()
            if n:
                logging.info("rss poller: %d new leads", n)
        except Exception as exc:
            logging.warning("rss poller: %s", exc)
        await asyncio.sleep(_RSS_POLL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(_github_poller())
    asyncio.create_task(_rss_poller())
    slack.send("FractalMesh API v3 online", level="info",
               fields={"port": os.environ.get("PORT", "8080"),
                       "rss_poll": f"{_RSS_POLL}s"})
    yield
    slack.send("FractalMesh API shutting down", level="warn")


app = FastAPI(title="FractalMesh API", version="3.0.0", lifespan=lifespan)

app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

# Core revenue routes
app.include_router(leads.router)
app.include_router(affiliate.router)
app.include_router(email_campaigns.router)
app.include_router(seo.router)
app.include_router(openrouter_routes.router)

# Infrastructure
app.include_router(alerts.router)
app.include_router(products.router)
app.include_router(webhooks.router)
app.include_router(stripe_connect.router)
app.include_router(ledger.router)

# Integrations
app.include_router(github.router)
app.include_router(devto.router)
app.include_router(ai.router)


@app.get("/health")
def health():
    return {"status": "ok", "version": "3.0.0"}
