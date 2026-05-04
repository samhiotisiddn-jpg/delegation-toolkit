"""
FractalMesh API — FastAPI server
Routes: trades, alerts, products/checkout, webhooks, github, devto
"""

import os
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import trades, alerts, products, webhooks, github, devto
from integrations import slack
from integrations.github_monitor import alert_new_commits

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s")

_GITHUB_POLL_SECS = 300  # check GitHub every 5 minutes


async def _github_poller():
    await asyncio.sleep(10)  # let server finish starting
    while True:
        try:
            since = (datetime.now(timezone.utc) - timedelta(seconds=_GITHUB_POLL_SECS)).isoformat()
            alert_new_commits(since)
        except Exception as exc:
            logging.warning("github poller error: %s", exc)
        await asyncio.sleep(_GITHUB_POLL_SECS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(_github_poller())
    slack.send("FractalMesh API online", level="info",
               fields={"port": os.environ.get("PORT", "8080")})
    yield
    slack.send("FractalMesh API shutting down", level="warn")


app = FastAPI(title="FractalMesh API", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(trades.router)
app.include_router(alerts.router)
app.include_router(products.router)
app.include_router(webhooks.router)
app.include_router(github.router)
app.include_router(devto.router)


@app.get("/health")
def health():
    return {"status": "ok", "version": "2.0.0"}
