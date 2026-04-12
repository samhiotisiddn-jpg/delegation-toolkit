"""
FractalMesh API — FastAPI server
Exposes: trades, alerts, products/checkout, webhooks (Stripe + Make.com)
"""

import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import trades, alerts, products, webhooks
from integrations import slack

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    slack.send("FractalMesh API online", level="info",
               fields={"port": os.environ.get("PORT", "8080")})
    yield
    slack.send("FractalMesh API shutting down", level="warn")


app = FastAPI(title="FractalMesh API", version="1.0.0", lifespan=lifespan)

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


@app.get("/health")
def health():
    return {"status": "ok"}
