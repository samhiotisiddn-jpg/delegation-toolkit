"""
Extra data sources beyond RSS:
- Hacker News top stories API
- Product Hunt (via RSS)
- GitHub trending repos
- DEV.to latest articles
"""

import json
import urllib.request
import logging

log = logging.getLogger("sources")

_HN_TOP = "https://hacker-news.firebaseio.com/v0/topstories.json"
_HN_ITEM = "https://hacker-news.firebaseio.com/v0/item/{}.json"
_DEVTO   = "https://dev.to/api/articles?per_page=20&top=7"
_GH_TRENDING = "https://api.github.com/search/repositories?q=created:>2026-04-01&sort=stars&order=desc&per_page=20"


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


def fetch_all() -> list[dict]:
    """Fetch from all supplementary sources."""
    results = []
    results.extend(fetch_hackernews(30))
    results.extend(fetch_devto_articles())
    results.extend(fetch_github_trending())
    log.info("sources: fetched %d items", len(results))
    return results
