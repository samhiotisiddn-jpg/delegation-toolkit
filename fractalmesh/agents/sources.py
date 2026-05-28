"""
Extra data sources beyond RSS:
- Hacker News top stories API
- GitHub trending repos
- DEV.to latest articles
- arxiv (cs.AI, cs.AR, cs.DC)
- HuggingFace blog
- CoinGecko market summary
"""

import json
import urllib.request
import logging

log = logging.getLogger("sources")

_HN_TOP = "https://hacker-news.firebaseio.com/v0/topstories.json"
_HN_ITEM = "https://hacker-news.firebaseio.com/v0/item/{}.json"
_DEVTO   = "https://dev.to/api/articles?per_page=20&top=7"
_GH_TRENDING = "https://api.github.com/search/repositories?q=created:>2026-04-01&sort=stars&order=desc&per_page=20"

_ARXIV_FEEDS = [
    ("https://export.arxiv.org/rss/cs.AI",  "arxiv_ai"),
    ("https://export.arxiv.org/rss/cs.AR",  "arxiv_arch"),
    ("https://export.arxiv.org/rss/cs.DC",  "arxiv_dc"),
]
_HF_FEED = "https://huggingface.co/blog/feed.xml"


def _get(url: str, headers: dict | None = None) -> dict | list:
    req = urllib.request.Request(url, headers={
        "User-Agent": "FractalMesh/3.0",
        **(headers or {}),
    })
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def fetch_hackernews(limit: int = 20) -> list[dict]:
    try:
        ids = _get(_HN_TOP)[:limit]
        items = []
        for story_id in ids:
            try:
                item = _get(_HN_ITEM.format(story_id))
                if item and item.get("title"):
                    items.append({
                        "title":   item["title"],
                        "url":     item.get("url", f"https://news.ycombinator.com/item?id={story_id}"),
                        "summary": f"HN score: {item.get('score', 0)} | comments: {item.get('descendants', 0)}",
                        "source":  "hackernews",
                    })
            except Exception:
                pass
        return items
    except Exception as exc:
        log.warning("HN fetch failed: %s", exc)
        return []


def fetch_devto_articles(tag: str = "") -> list[dict]:
    try:
        url = f"https://dev.to/api/articles?per_page=20&top=7"
        if tag:
            url += f"&tag={tag}"
        articles = _get(url)
        return [
            {
                "title":   a["title"],
                "url":     a["url"],
                "summary": a.get("description", ""),
                "source":  "devto",
                "tags":    a.get("tag_list", []),
            }
            for a in articles
        ]
    except Exception as exc:
        log.warning("DEV.to fetch failed: %s", exc)
        return []


def fetch_github_trending(min_stars: int = 100) -> list[dict]:
    try:
        import os
        headers = {}
        token = os.environ.get("GITHUB_TOKEN", "")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        data = _get(_GH_TRENDING, headers)
        return [
            {
                "title":   f"{r['full_name']} ⭐{r['stargazers_count']}",
                "url":     r["html_url"],
                "summary": r.get("description", ""),
                "source":  "github_trending",
                "tags":    [r.get("language", "")],
            }
            for r in data.get("items", [])
            if r.get("stargazers_count", 0) >= min_stars
        ]
    except Exception as exc:
        log.warning("GitHub trending failed: %s", exc)
        return []


def fetch_arxiv(feed_url: str, source_label: str) -> list[dict]:
    """Fetch an arxiv RSS feed and return structured items."""
    try:
        import xml.etree.ElementTree as ET
        req = urllib.request.Request(feed_url, headers={"User-Agent": "FractalMesh/4.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            root = ET.fromstring(r.read())
        ns = {"rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
              "dc":  "http://purl.org/dc/elements/1.1/"}
        items = []
        for item in root.findall(".//{http://purl.org/rss/1.0/}item"):
            title = item.findtext("{http://purl.org/rss/1.0/}title", "").strip()
            link  = item.findtext("{http://purl.org/rss/1.0/}link", "").strip()
            desc  = item.findtext("{http://purl.org/rss/1.0/}description", "").strip()[:300]
            if title:
                items.append({"title": title, "url": link, "summary": desc, "source": source_label})
        return items
    except Exception as exc:
        log.warning("arxiv %s fetch failed: %s", source_label, exc)
        return []


def fetch_huggingface_blog() -> list[dict]:
    """Fetch HuggingFace blog RSS feed."""
    try:
        import xml.etree.ElementTree as ET
        req = urllib.request.Request(_HF_FEED, headers={"User-Agent": "FractalMesh/4.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            root = ET.fromstring(r.read())
        items = []
        for item in root.findall(".//item"):
            title = item.findtext("title", "").strip()
            link  = item.findtext("link", "").strip()
            desc  = item.findtext("description", "").strip()[:300]
            if title:
                items.append({"title": title, "url": link, "summary": desc, "source": "huggingface"})
        return items
    except Exception as exc:
        log.warning("HuggingFace feed failed: %s", exc)
        return []


def fetch_market_snapshot() -> list[dict]:
    """Fetch CoinGecko trending as lead-scored market items."""
    try:
        from integrations import coingecko
        trending = coingecko.get_trending()
        summary  = coingecko.format_market_summary()
        items = [
            {
                "title":   f"Trending: {c['name']} ({c['symbol'].upper()}) rank #{c['rank']}",
                "url":     f"https://www.coingecko.com/en/coins/{c['id']}",
                "summary": summary,
                "source":  "coingecko",
            }
            for c in trending
        ]
        return items
    except Exception as exc:
        log.warning("coingecko market snapshot failed: %s", exc)
        return []


def fetch_all() -> list[dict]:
    """Fetch from all supplementary sources."""
    results = []
    results.extend(fetch_hackernews(30))
    results.extend(fetch_devto_articles())
    results.extend(fetch_github_trending())
    for url, label in _ARXIV_FEEDS:
        results.extend(fetch_arxiv(url, label))
    results.extend(fetch_huggingface_blog())
    results.extend(fetch_market_snapshot())
    log.info("sources: fetched %d items total", len(results))
    return results
