"""Automation control — trigger jobs on demand."""

from fastapi import APIRouter, Body
from agents import rss_swarm, lead_enricher, content_publisher, sources

router = APIRouter(prefix="/automation", tags=["automation"])


@router.post("/ingest")
def trigger_ingest():
    rss = rss_swarm.ingest_once()
    extra = sources.fetch_all()
    return {"rss_ingested": rss, "supplementary_fetched": len(extra)}


@router.post("/enrich")
def trigger_enrich(limit: int = Body(20, embed=True)):
    n = lead_enricher.enrich_batch(limit)
    return {"enriched": n}


@router.post("/digest")
def trigger_digest(
    min_score: float = Body(65.0),
    published: bool  = Body(False),
):
    result = content_publisher.publish_digest(min_score, published)
    return result or {"detail": "no leads above threshold"}


@router.post("/outreach-email")
def generate_outreach(
    niche:          str = Body(...),
    product_angle:  str = Body(...),
    recipient_name: str = Body("there"),
):
    return lead_enricher.generate_outreach_email(niche, product_angle, recipient_name)


@router.get("/sources/preview")
def preview_sources():
    return {
        "hackernews": sources.fetch_hackernews(5),
        "devto":      sources.fetch_devto_articles()[:5],
        "github":     sources.fetch_github_trending()[:5],
    }
