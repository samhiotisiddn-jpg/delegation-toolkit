"""
Dark-web / OSINT harvester (legal public OSINT only).

* Searches Tor-accessible indexes (Ahmia) for keywords.
* Queries public breach-notification APIs.
* Wraps all Tor traffic through a SOCKS5 proxy.

ENV:
  TOR_SOCKS5_PROXY      e.g. socks5h://127.0.0.1:9050
  OSINT_KEYWORDS        comma-separated targets
  HIBP_API_KEY          HaveIBeenPwned API key (optional)
"""

import os
import re
import json
import logging
import urllib.request
from datetime import datetime

log = logging.getLogger("darkweb_osint")

_PROXY = os.getenv("TOR_SOCKS5_PROXY", "")
_KEYWORDS = [k.strip() for k in os.getenv("OSINT_KEYWORDS", "").split(",") if k.strip()]
_HIBP = os.getenv("HIBP_API_KEY", "")


def _opener() -> urllib.request.OpenerDirector:
    if _PROXY:
        return urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": _PROXY, "https": _PROXY}),
            urllib.request.HTTPHandler(),
        )
    return urllib.request.build_opener()


def _get(url: str, headers: dict | None = None) -> str:
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "FractalMesh/OSINT"})
    with _opener().open(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="ignore")


def search_ahmia(query: str, pages: int = 1) -> list[dict]:
    """Use Ahmia.fi hidden-service search via its public gateway."""
    results = []
    for p in range(pages):
        url = f"https://ahmia.fi/search/?q={urllib.parse.quote(query)}&p={p}"
        try:
            html = _get(url)
            for m in re.finditer(r'<a href="(https?://[^"]+)"[^>]*>([^<]+)</a>', html):
                results.append({"title": m.group(2).strip(), "url": m.group(1), "source": "ahmia", "query": query})
        except Exception as exc:
            log.warning("ahmia search failed: %s", exc)
    return results[:20]


def query_hibp_breach(account: str) -> dict:
    """Query a single account against HIBP breach API."""
    if not _HIBP:
        return {"mode": "sim", "account": account}
    url = f"https://haveibeenpwned.com/api/v3/breachedaccount/{urllib.parse.quote(account)}"
    headers = {"hibp-api-key": _HIBP, "User-Agent": "FractalMeshOSINT"}
    try:
        data = _get(url, headers)
        return {"account": account, "breaches": json.loads(data), "source": "hibp"}
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {"account": account, "breaches": [], "source": "hibp"}
        return {"account": account, "error": str(exc)}
    except Exception as exc:
        return {"account": account, "error": str(exc)}


def run_osint_cycle() -> dict:
    hits = []
    for kw in _KEYWORDS:
        hits.extend(search_ahmia(kw))
    breached_accounts = []
    # Treat any keyword that looks like an email as HIBP account
    for kw in _KEYWORDS:
        if "@" in kw:
            breached_accounts.append(query_hibp_breach(kw))
    return {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "keywords": _KEYWORDS,
        "ahmia_hits": hits,
        "breach_checks": breached_accounts,
        "count": len(hits),
    }
