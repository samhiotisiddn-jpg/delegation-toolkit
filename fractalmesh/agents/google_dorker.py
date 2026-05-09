"""
Google Dorking Parallel Harvester — automated OSINT lead extraction.

Academic refs:
  - Hassan & Hijawi (2021) "OSINT for Cyber Threat Intelligence" — SUPPORT
    dorking as systematic reconnaissance methodology
  - Shodan + Google dork chaining: Grisafi et al. (2022) structured query
    generation for target profiling
  CONFLICTING:
  - Lin et al. (2023) "Ethical Limits of Automated OSINT" — notes ToS issues
    with automated Google scraping; mitigated here by using Bing/DuckDuckGo
    and Crawlbase proxy, plus rate limiting

Dork categories:
  - Hiring/contract leads (Reddit, LinkedIn, freelancer boards)
  - Potential clients with tech stacks matching our skills
  - Affiliate/partner discovery
  - Competitor analysis
  - Data product opportunities
"""

import os
import json
import time
import logging
import hashlib
import urllib.request
import urllib.parse
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

log = logging.getLogger("google_dorker")

_DISPATCH = os.path.expanduser(os.getenv("DISPATCH_DIR", "~/ai-mesh/dispatch_queue"))

# Dork templates — {keyword} replaced at runtime
DORK_TEMPLATES = {
    "hiring_python": [
        'site:reddit.com/r/forhire "hiring" "python" "api" -"closed"',
        'site:reddit.com/r/forhire "hiring" "automation" "bot" -"closed"',
        'site:reddit.com/r/forhire "hiring" "web3" OR "blockchain" -"closed"',
        'site:reddit.com/r/forhire "hiring" "data" "scraping" -"closed"',
        'site:reddit.com/r/forhire "paying" "developer" "api" -"closed"',
    ],
    "freelancer_boards": [
        'site:upwork.com/jobs "python" "api integration" "fixed price"',
        'site:toptal.com/jobs "python" "automation"',
        'site:peopleperhour.com "python" "automation" "api"',
    ],
    "affiliate_partners": [
        '"affiliate program" "recurring commission" "SaaS" "api"',
        '"partner program" "30%" commission "developer tools"',
        '"refer" "earn" "api" "developer" commission site:github.com',
    ],
    "data_buyers": [
        '"looking for" "data feed" "api" "bulk" "purchase"',
        '"want to buy" "RSS" OR "JSON" "data" "feed" developer',
        '"data marketplace" "api data" "buy" OR "purchase" 2026',
    ],
    "competitor_intel": [
        '"autonomous trading bot" site:github.com stars:>50',
        '"ai revenue automation" "open source" site:github.com',
        '"fractalmesh" OR "ironvision" site:github.com',
    ],
    "research_papers": [
        'site:arxiv.org "autonomous trading" "reinforcement learning" 2025 OR 2026',
        'site:arxiv.org "multi-agent" "revenue" "autonomous" 2025 OR 2026',
        'site:scholar.google.com "affiliate marketing automation" "machine learning"',
    ],
}

# Bing Search API (free tier via Azure) or fallback to Crawlbase
_BING_KEY = os.getenv("BING_SEARCH_KEY", "")
_CRAWLBASE = os.getenv("CRAWLBASE_NORMAL_TOKEN", "")


def _bing_search(query: str, count: int = 10) -> list[dict]:
    if not _BING_KEY:
        return []
    params = urllib.parse.urlencode({"q": query, "count": count, "mkt": "en-AU"})
    req = urllib.request.Request(
        f"https://api.bing.microsoft.com/v7.0/search?{params}",
        headers={"Ocp-Apim-Subscription-Key": _BING_KEY},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        return [
            {"url": w["url"], "title": w["name"], "snippet": w.get("snippet", ""),
             "source": "bing"}
            for w in data.get("webPages", {}).get("value", [])
        ]
    except Exception as exc:
        log.warning("bing_search '%s': %s", query, exc)
        return []


def _duckduckgo_search(query: str) -> list[dict]:
    """DuckDuckGo HTML scrape via Crawlbase (no API key required)."""
    if not _CRAWLBASE:
        return []
    encoded = urllib.parse.quote(f"https://duckduckgo.com/html/?q={urllib.parse.quote(query)}")
    try:
        req = urllib.request.Request(
            f"https://api.crawlbase.com/?token={_CRAWLBASE}&url={encoded}",
            headers={"User-Agent": "FractalMesh/6.0"},
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            html = r.read().decode("utf-8", errors="ignore")
        # Extract result URLs from DDG HTML
        import re
        results = []
        for m in re.finditer(r'href="(https?://[^"]+)"[^>]*>([^<]+)</a>', html):
            url, title = m.group(1), m.group(2).strip()
            if url and not "duckduckgo.com" in url and not "ad_domain" in url:
                results.append({"url": url, "title": title, "snippet": "", "source": "duckduckgo"})
        return results[:10]
    except Exception as exc:
        log.warning("duckduckgo '%s': %s", query, exc)
        return []


def _score_result(result: dict) -> float:
    """Heuristic score for a dork result's lead quality."""
    from integrations.openrouter import score_lead
    try:
        return score_lead(result.get("title", ""), result.get("snippet", ""))
    except Exception:
        title = result.get("title", "").lower()
        score = 0.0
        keywords = ["hiring", "paying", "urgent", "immediate", "python", "api", "blockchain",
                    "automation", "data", "crypto", "web3", "bot", "$", "usd", "aud"]
        for kw in keywords:
            if kw in title:
                score += 8.0
        return min(score, 80.0)


def harvest_dork(query: str, category: str, rate_limit_sec: float = 1.5) -> list[dict]:
    """Execute a single dork query, score results, return enriched leads."""
    time.sleep(rate_limit_sec)  # rate limiting
    results = _bing_search(query) or _duckduckgo_search(query)
    enriched = []
    for r in results:
        r["score"] = _score_result(r)
        r["dork"] = query
        r["category"] = category
        r["harvested_at"] = datetime.utcnow().isoformat() + "Z"
        r["id"] = hashlib.sha256(r["url"].encode()).hexdigest()[:16]
        enriched.append(r)
    return sorted(enriched, key=lambda x: x["score"], reverse=True)


def harvest_all_dorks(max_workers: int = 4, min_score: float = 40.0) -> dict:
    """
    Run all dork categories in parallel (ThreadPoolExecutor).
    Returns structured results by category.
    """
    tasks = []
    for category, queries in DORK_TEMPLATES.items():
        for query in queries:
            tasks.append((query, category))

    all_results: dict[str, list] = {cat: [] for cat in DORK_TEMPLATES}
    total_leads = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(harvest_dork, query, category): (query, category)
            for query, category in tasks
        }
        for future in as_completed(futures):
            query, category = futures[future]
            try:
                results = future.result()
                high_value = [r for r in results if r["score"] >= min_score]
                all_results[category].extend(high_value)
                total_leads += len(high_value)
                log.info("dork '%s': %d results, %d high-value", query[:50], len(results), len(high_value))
            except Exception as exc:
                log.warning("dork failed '%s': %s", query[:50], exc)

    # Stage top leads as pitches
    stage_top_leads(all_results)

    return {
        "total_leads": total_leads,
        "by_category": {cat: len(leads) for cat, leads in all_results.items()},
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "results": all_results,
    }


def stage_top_leads(results_by_category: dict, max_per_category: int = 3) -> int:
    """Auto-stage pitches for top dork results."""
    os.makedirs(_DISPATCH, exist_ok=True)
    staged = 0
    abn  = os.getenv("ABN", "56628117363")
    name = os.getenv("DIRECTOR", "Samuel James Hiotis")

    for category, leads in results_by_category.items():
        top = sorted(leads, key=lambda x: x["score"], reverse=True)[:max_per_category]
        for lead in top:
            ts    = datetime.now().strftime("%Y%m%d_%H%M%S")
            fname = os.path.join(_DISPATCH, f"DORK_{category}_{ts}.txt")
            pitch = (
                f"CATEGORY: {category}\n"
                f"SOURCE URL: {lead['url']}\n"
                f"DORK QUERY: {lead['dork']}\n"
                f"RELEVANCE SCORE: {lead['score']:.1f}/100\n"
                f"FROM: {name} | IronVision Nexus | ABN {abn}\n\n"
                f"Title: {lead['title']}\n"
                f"Snippet: {lead.get('snippet', '')[:300]}\n\n"
                f"PITCH:\nI can deliver exactly what you need. "
                f"I specialise in Python/FastAPI automation, AI agent orchestration, "
                f"trading system integration (KuCoin, Crypto.com), Web3/blockchain automation, "
                f"and enterprise data pipelines. Available immediately for AUD or USDC.\n"
                f"Contact: sam.hiotis@gmail.com | 0439 008 640\n"
            )
            with open(fname, "w") as f:
                f.write(pitch)
            staged += 1
    return staged


def get_dork_categories() -> dict:
    return {cat: len(queries) for cat, queries in DORK_TEMPLATES.items()}
