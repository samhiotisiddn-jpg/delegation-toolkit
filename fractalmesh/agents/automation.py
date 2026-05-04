"""
Automation scheduler — runs all recurring jobs on fixed intervals.

Schedule:
  Every 15 min  — RSS ingest + supplementary sources
  Every 30 min  — Lead enrichment (AI rescore + enhance)
  Every 6 hrs   — Publish DEV.to digest (draft)
  Every 24 hrs  — Send weekly affiliate digest email campaign
  Continuous    — System metrics to Supabase
"""

import asyncio
import logging
import os
from datetime import datetime, timezone

from integrations import slack, make_webhooks
from integrations.supabase_client import query, insert

log = logging.getLogger("automation")

# Intervals in seconds
INTERVALS = {
    "rss_ingest":    int(os.environ.get("RSS_POLL_SECS", "900")),
    "source_fetch":  900,
    "lead_enrich":   1800,
    "digest_publish": 21600,
    "affiliate_report": 86400,
    "metrics":        300,
}


async def _job(name: str, interval: int, fn, *args, initial_delay: int = 0):
    if initial_delay:
        await asyncio.sleep(initial_delay)
    while True:
        try:
            log.info("[automation] running: %s", name)
            result = fn(*args)
            log.info("[automation] done: %s → %s", name, result)
        except Exception as exc:
            log.error("[automation] %s error: %s", name, exc)
            slack.send(f"Automation error: {name}", body=str(exc), level="error")
        await asyncio.sleep(interval)


async def _rss_job():
    await asyncio.sleep(10)
    while True:
        try:
            from agents.rss_swarm import ingest_once
            from agents.sources import fetch_all
            from integrations.supabase_client import insert
            from integrations.unified_ai import score_lead, enhance_for_seo

            threshold = float(os.environ.get("LEAD_SCORE_THRESHOLD", "40"))

            # Supplementary sources
            extra = fetch_all()
            added = 0
            for item in extra:
                score = score_lead(item["title"], item.get("summary", ""))
                if score < threshold:
                    continue
                enhanced = enhance_for_seo(item["title"], item.get("summary", ""))
                tier = "premium" if score >= 75 else "standard" if score >= 55 else "basic"
                try:
                    insert("leads", {
                        "title":       item["title"],
                        "url":         item.get("url", ""),
                        "source_feed": item.get("source", "supplementary"),
                        "summary":     enhanced,
                        "intent_score": score,
                        "tier":        tier,
                        "tags":        item.get("tags", []),
                        "raw":         item,
                    })
                    added += 1
                except Exception:
                    pass  # dedup

            rss_n = ingest_once()
            total = rss_n + added
            if total:
                log.info("ingest cycle: %d rss + %d supplementary", rss_n, added)

        except Exception as exc:
            log.error("[rss_job] %s", exc)

        await asyncio.sleep(INTERVALS["rss_ingest"])


async def _enrich_job():
    await asyncio.sleep(60)
    while True:
        try:
            from agents.lead_enricher import enrich_batch
            enrich_batch(20)
        except Exception as exc:
            log.error("[enrich_job] %s", exc)
        await asyncio.sleep(INTERVALS["lead_enrich"])


async def _digest_job():
    await asyncio.sleep(120)
    while True:
        try:
            from agents.content_publisher import publish_digest
            publish_digest(min_score=65.0, published=False)
        except Exception as exc:
            log.error("[digest_job] %s", exc)
        await asyncio.sleep(INTERVALS["digest_publish"])


async def _metrics_job():
    await asyncio.sleep(20)
    while True:
        try:
            leads      = query("leads", limit=1000)
            customers  = query("customers", {"is_active": True}, limit=500)
            affiliates = query("affiliates", {"is_active": True}, limit=500)
            orders     = query("orders", {"status": "paid"}, limit=500)

            revenue = sum(float(o.get("amount_aud", 0)) for o in orders)
            metrics = {
                "leads_total":     len(leads),
                "leads_premium":   sum(1 for l in leads if l.get("tier") == "premium"),
                "customers_active": len(customers),
                "affiliates_active": len(affiliates),
                "revenue_aud":     revenue,
                "timestamp":       datetime.now(timezone.utc).isoformat(),
            }
            insert("alerts", {
                "source": "metrics",
                "level":  "info",
                "title":  "System metrics",
                "raw":    metrics,
            })
            make_webhooks.trigger("metrics.snapshot", metrics)
        except Exception as exc:
            log.error("[metrics_job] %s", exc)
        await asyncio.sleep(INTERVALS["metrics"])


async def _affiliate_report_job():
    await asyncio.sleep(300)
    while True:
        try:
            affiliates = query("affiliates", {"is_active": True}, limit=100)
            top = sorted(affiliates, key=lambda a: a.get("total_revenue", 0), reverse=True)[:5]
            body = "\n".join(
                f"{a['name']}: {a['total_referrals']} referrals | ${a['total_revenue']:.2f} AUD"
                for a in top
            )
            slack.send("Daily affiliate report", body=body or "No affiliates yet", level="info",
                       fields={"total_affiliates": str(len(affiliates))})
        except Exception as exc:
            log.error("[affiliate_report] %s", exc)
        await asyncio.sleep(INTERVALS["affiliate_report"])


def start_all_jobs() -> list:
    """Create and return all automation tasks. Call from asyncio context."""
    return [
        asyncio.create_task(_rss_job()),
        asyncio.create_task(_enrich_job()),
        asyncio.create_task(_digest_job()),
        asyncio.create_task(_metrics_job()),
        asyncio.create_task(_affiliate_report_job()),
    ]
