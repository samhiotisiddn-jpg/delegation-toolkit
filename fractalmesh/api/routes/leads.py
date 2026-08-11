"""
Leads / dataset API — tiered access to RSS-ingested intelligence.
Public: 5 results, no scores.
Standard/Premium: full dataset with scores via bearer token.
"""

import secrets
from fastapi import APIRouter, Query, Header, HTTPException, Body
from fastapi.responses import Response
from integrations.supabase_client import query, insert
from agents.rss_swarm import ingest_once

router = APIRouter(prefix="/leads", tags=["leads"])


def _auth(token: str | None) -> str:
    """Returns tier based on token. 'public' if no valid token."""
    if not token or not token.startswith("Bearer "):
        return "public"
    tok = token.replace("Bearer ", "")
    customers = query("customers", {"access_token": tok, "is_active": True}, limit=1)
    if customers:
        return customers[0]["subscription_tier"]
    return "public"


@router.get("/")
def list_leads(
    authorization: str | None = Header(None),
    limit: int = Query(20, le=500),
    tier: str | None = Query(None),
    min_score: float = Query(0),
):
    access = _auth(authorization)

    if access == "public":
        rows = query("leads", limit=5)
        return {
            "tier": "public",
            "count": len(rows),
            "data": [{"title": r["title"], "created_at": r["created_at"]} for r in rows],
            "upgrade": "POST /leads/subscribe to unlock full dataset",
        }

    filters = {}
    if tier:
        filters["tier"] = tier

    rows = query("leads", filters=filters or None, limit=limit)
    if min_score > 0:
        rows = [r for r in rows if float(r.get("intent_score", 0)) >= min_score]

    return {"tier": access, "count": len(rows), "data": rows}


@router.get("/feed.xml")
def rss_feed(authorization: str | None = Header(None)):
    """Premium gated RSS feed — machine-readable dataset."""
    access = _auth(authorization)
    if access not in ("standard", "premium"):
        raise HTTPException(status_code=401, detail="Subscription required")

    rows = query("leads", limit=100)
    items = "\n".join(
        f"<item><title><![CDATA[{r['title']}]]></title>"
        f"<link>{r.get('url','')}</link>"
        f"<description><![CDATA[{r.get('summary','')}]]></description>"
        f"<score>{r.get('intent_score',0)}</score>"
        f"<tier>{r.get('tier','')}</tier>"
        f"<pubDate>{r['created_at']}</pubDate></item>"
        for r in rows
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<rss version="2.0"><channel>'
        '<title>FractalMesh Premium Data Feed</title>'
        f'{items}</channel></rss>'
    )
    return Response(content=xml, media_type="application/rss+xml")


@router.post("/ingest")
def trigger_ingest():
    """Manually trigger RSS ingestion cycle."""
    n = ingest_once()
    return {"ingested": n}


@router.post("/subscribe")
def subscribe(
    email:    str = Body(...),
    tier:     str = Body("basic"),
    ref_code: str | None = Body(None),
):
    """Create a customer subscription record (call after Stripe payment)."""
    token = secrets.token_urlsafe(32)
    customer = insert("customers", {
        "email":             email,
        "subscription_tier": tier,
        "access_token":      token,
    })

    if ref_code:
        affiliates = query("affiliates", {"affiliate_code": ref_code}, limit=1)
        if affiliates:
            insert("affiliate_referrals", {
                "affiliate_id": affiliates[0]["id"],
                "customer_id":  customer["id"],
            })

    return {"access_token": token, "tier": tier, "email": email}
