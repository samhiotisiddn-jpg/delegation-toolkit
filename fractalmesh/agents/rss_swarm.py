"""
RSS Swarm — ingests configured feeds, scores each item with OpenRouter,
stores results in Supabase leads table.

ENV:
  RSS_FEEDS            comma-separated feed URLs
  LEAD_SCORE_THRESHOLD  minimum score to keep (default 40)
  RSS_POLL_SECS        poll interval (default 900)
"""

import os
import time
import hashlib
import logging
import urllib.request
import xml.etree.ElementTree as ET

from integrations.supabase_client import insert, query
from integrations import slack, make_webhooks
from integrations.openrouter import score_lead, enhance_content
from integrations.aegis import sanitize

log = logging.getLogger("rss_swarm")

THRESHOLD  = float(os.environ.get("LEAD_SCORE_THRESHOLD", "40"))
POLL_SECS  = int(os.environ.get("RSS_POLL_SECS", "900"))


def _feeds() -> list[str]:
    raw = os.environ.get("RSS_FEEDS", "")
    return [f.strip() for f in raw.split(",") if f.strip()]


def _fetch_feed(url: str) -> list[dict]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "FractalMesh/2.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            tree = ET.fromstring(r.read())
    except Exception as exc:
        log.warning("feed error %s: %s", url, exc)
        return []

    items = []
    ns = {"atom": "http://www.w3.org/2005/Atom"}

    # RSS 2.0
    for item in tree.findall(".//item"):
        title   = (item.findtext("title") or "").strip()
        link    = (item.findtext("link") or "").strip()
        desc    = (item.findtext("description") or "").strip()
        pub     = item.findtext("pubDate") or ""
        if title:
            items.append({"title": title, "url": link, "summary": desc, "published": pub})

    # Atom
    for entry in tree.findall("atom:entry", ns):
        title   = (entry.findtext("atom:title", namespaces=ns) or "").strip()
        link    = entry.find("atom:link", ns)
        href    = link.get("href", "") if link is not None else ""
        summary = (entry.findtext("atom:summary", namespaces=ns) or "").strip()
        if title:
            items.append({"title": title, "url": href, "summary": summary})

    return items


def _dedup_key(title: str, url: str) -> str:
    return hashlib.sha256(f"{title}{url}".encode()).hexdigest()[:16]


def _known_ids() -> set:
    rows = query("leads", limit=500)
    return {r.get("raw", {}).get("dedup") for r in rows if r.get("raw")}


def ingest_once() -> int:
    known = _known_ids()
    new_count = 0

    for feed_url in _feeds():
        items = _fetch_feed(feed_url)
        for item in items:
            key = _dedup_key(item["title"], item["url"])
            if key in known:
                continue
            known.add(key)

            # Aegis UTS #39 sanitization before scoring
            clean_title   = sanitize(item["title"])
            clean_summary = sanitize(item["summary"])

            score = score_lead(clean_title, clean_summary)
            if score < THRESHOLD:
                continue

            enhanced = enhance_content(clean_title, clean_summary)
            tier = "premium" if score >= 75 else "standard" if score >= 55 else "basic"

            insert("leads", {
                "title":       clean_title,
                "url":         item["url"],
                "source_feed": feed_url,
                "summary":     enhanced,
                "intent_score": score,
                "tier":        tier,
                "raw":         {**item, "dedup": key},
            })
            new_count += 1

    if new_count:
        slack.send(f"RSS Swarm: {new_count} new leads ingested", level="info",
                   fields={"threshold": str(THRESHOLD)})
        make_webhooks.trigger("leads.ingested", {"count": new_count})
    return new_count


def run_forever():
    log.info("RSS swarm starting | feeds=%d | threshold=%.0f | poll=%ds",
             len(_feeds()), THRESHOLD, POLL_SECS)
    while True:
        try:
            n = ingest_once()
            log.info("ingested %d new leads", n)
        except Exception as exc:
            log.error("swarm error: %s", exc)
            slack.send("RSS swarm error", body=str(exc), level="error")
        time.sleep(POLL_SECS)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    run_forever()
