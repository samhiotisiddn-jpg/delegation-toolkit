"""
Automation scheduler v5 — all recurring jobs.

Schedule:
  Every 15 min  — RSS ingest + supplementary sources (HN, DEV.to, GitHub, arxiv, HF, CoinGecko)
  Every 30 min  — Lead enrichment (AI rescore + enhance)
  Every 1 hr    — Trading cycle (all strategies, KuCoin)
  Every 2 hrs   — WiGLE oracle cycle (RF + DEM extract + package)
  Every 2 hrs   — Reddit outreach cycle (scrape + stage pitches)
  Every 5 min   — Metrics snapshot → Supabase + Firebase + Make + Zapier
  Every 6 hrs   — DEV.to digest publish (draft)
  Every 24 hrs  — Affiliate performance report → Slack + Telegram
"""

import asyncio
import logging
import os
from datetime import datetime, timezone

from integrations import slack, make_webhooks
from integrations.supabase_client import query, insert

log = logging.getLogger("automation")

INTERVALS = {
    "rss_ingest":       int(os.environ.get("RSS_POLL_SECS", "900")),
    "lead_enrich":      1800,
    "trading_cycle":    3600,
    "oracle_cycle":     7200,
    "outreach_cycle":   7200,
    "metrics":          300,
    "digest_publish":   21600,
    "affiliate_report": 86400,
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
            from integrations.aegis import sanitize
            from integrations.unified_ai import score_lead, enhance_for_seo

            threshold = float(os.environ.get("LEAD_SCORE_THRESHOLD", "40"))

            extra = fetch_all()
            added = 0
            for item in extra:
                clean_title   = sanitize(item.get("title", ""))
                clean_summary = sanitize(item.get("summary", ""))
                score = score_lead(clean_title, clean_summary)
                if score < threshold:
                    continue
                enhanced = enhance_for_seo(clean_title, clean_summary)
                tier = "premium" if score >= 75 else "standard" if score >= 55 else "basic"
                try:
                    insert("leads", {
                        "title":        clean_title,
                        "url":          item.get("url", ""),
                        "source_feed":  item.get("source", "supplementary"),
                        "summary":      enhanced,
                        "intent_score": score,
                        "tier":         tier,
                        "tags":         item.get("tags", []),
                        "raw":          item,
                    })
                    added += 1
                except Exception:
                    pass

            rss_n = ingest_once()
            total = rss_n + added
            if total:
                log.info("ingest cycle: %d rss + %d supplementary", rss_n, added)
                try:
                    from integrations.zapier_mcp import notify_new_leads
                    notify_new_leads(total)
                except Exception:
                    pass

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


async def _trading_job():
    await asyncio.sleep(90)
    while True:
        try:
            from integrations.trading_engine import run_all_strategies, get_status
            status = get_status()
            if status.get("circuit_open"):
                log.warning("[trading_job] circuit breaker open — skipping cycle")
            else:
                results = run_all_strategies()
                executed = sum(
                    1 for strat_results in results.values()
                    for r in strat_results
                    if isinstance(r, dict) and r.get("mode") in ("live", "paper")
                       or isinstance(r, dict) and "id" in r
                )
                log.info("[trading_job] cycle complete — %d orders", executed)
                if executed:
                    try:
                        from integrations.telegram_bot import alert
                        alert("Trading Cycle", f"{executed} orders executed across {len(results)} strategies", "INFO")
                    except Exception:
                        pass
        except Exception as exc:
            log.error("[trading_job] %s", exc)
        await asyncio.sleep(INTERVALS["trading_cycle"])


async def _oracle_job():
    await asyncio.sleep(300)
    while True:
        try:
            from integrations.wigle_oracle import extract_wigle_rf, extract_satellite_dem, package_dataset
            rf  = extract_wigle_rf()
            dem = extract_satellite_dem()
            for label, r in [("rf", rf), ("dem", dem)]:
                if "path" in r and not r.get("error"):
                    package_dataset(r["path"])
            log.info("[oracle_job] cycle complete — rf=%s dem=%s", rf.get("network_count", "err"), "ok")
        except Exception as exc:
            log.error("[oracle_job] %s", exc)
        await asyncio.sleep(INTERVALS["oracle_cycle"])


async def _outreach_job():
    await asyncio.sleep(450)
    while True:
        try:
            from api.routes.outreach import scrape_reddit_leads, stage_pitch
            leads = scrape_reddit_leads("forhire", 50)[:5]
            for lead in leads:
                stage_pitch(lead["title"], lead["link"], lead.get("body", ""))
            if leads:
                log.info("[outreach_job] %d pitches staged", len(leads))
        except Exception as exc:
            log.error("[outreach_job] %s", exc)
        await asyncio.sleep(INTERVALS["outreach_cycle"])


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
                "leads_total":       len(leads),
                "leads_premium":     sum(1 for l in leads if l.get("tier") == "premium"),
                "customers_active":  len(customers),
                "affiliates_active": len(affiliates),
                "revenue_aud":       revenue,
                "timestamp":         datetime.now(timezone.utc).isoformat(),
            }
            insert("alerts", {"source": "metrics", "level": "info", "title": "System metrics", "raw": metrics})
            make_webhooks.trigger("metrics.snapshot", metrics)

            try:
                from integrations.firebase_client import push_metrics
                push_metrics(metrics)
            except Exception:
                pass

            try:
                from integrations.zapier_mcp import trigger as ztrigger
                ztrigger("metrics.snapshot", metrics)
            except Exception:
                pass

        except Exception as exc:
            log.error("[metrics_job] %s", exc)
        await asyncio.sleep(INTERVALS["metrics"])


async def _affiliate_report_job():
    await asyncio.sleep(600)
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
            try:
                from integrations.telegram_bot import alert
                alert("Affiliate Report", body or "No affiliates yet", "INFO")
            except Exception:
                pass
        except Exception as exc:
            log.error("[affiliate_report] %s", exc)
        await asyncio.sleep(INTERVALS["affiliate_report"])


def start_all_jobs() -> list:
    """Create and return all automation tasks. Call from asyncio context."""
    return [
        asyncio.create_task(_rss_job()),
        asyncio.create_task(_enrich_job()),
        asyncio.create_task(_trading_job()),
        asyncio.create_task(_oracle_job()),
        asyncio.create_task(_outreach_job()),
        asyncio.create_task(_digest_job()),
        asyncio.create_task(_metrics_job()),
        asyncio.create_task(_affiliate_report_job()),
    ]
