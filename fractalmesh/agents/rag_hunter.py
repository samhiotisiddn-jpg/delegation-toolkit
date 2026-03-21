#!/usr/bin/env python3
"""
fractalmesh/agents/rag_hunter.py
==================================
Industrial RAG Hunter
---------------------
Retrieval-Augmented Generation agent for building enriched intelligence
profiles on industrial operators within a defined precinct (default: Albury
Logic Industrial Estate).

Pipeline
--------
1. DORK — construct targeted search queries against public web sources to
   locate MD/CEO contacts at configured target organisations.
2. FETCH — retrieve and sanitise page text via Crawlbase (JS-render capable)
   to handle JS-gated LinkedIn / company sites.
3. ENRICH — cross-reference fetched contacts against Supabase `contacts`
   table; upsert new findings.
4. RAG SCORE — embed query + contact snippet pairs; rank by cosine similarity
   to the active outreach objective.
5. REPORT — emit ABN-watermarked JSON with ranked lead list.

Environment variables (never hardcode):
    CRAWLBASE_NORMAL_TOKEN      — Crawlbase plain HTTP token
    CRAWLBASE_JS_TOKEN          — Crawlbase JS-render token (for SPAs)
    SUPABASE_URL                — Supabase project URL
    SUPABASE_SERVICE_KEY        — Supabase service-role key
    OPENAI_API_KEY              — OpenAI key for embeddings + completion
    ABN                         — Operator ABN for watermarking
    RAG_HUNTER_TARGETS          — JSON list of {"org": ..., "role": ...}
    RAG_HUNTER_PRECINCT         — search modifier (default: "Albury Logic Industrial Estate")
    RAG_HUNTER_MAX_RESULTS      — max leads per target (default: 5)
    RAG_HUNTER_OBJECTIVE        — plain-text outreach objective for RAG scoring
    RAG_HUNTER_DRY_RUN          — set to "1" to skip Supabase writes

Usage:
    python3 rag_hunter.py
    python3 rag_hunter.py --dry-run
    python3 rag_hunter.py --targets '[{"org":"Visy","role":"Managing Director"}]'
    python3 rag_hunter.py --objective "infrastructure stress assessment services"
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import re
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# ── optional deps ─────────────────────────────────────────────────────────────
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

# ── logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [rag_hunter] %(levelname)s %(message)s",
)
log = logging.getLogger("rag_hunter")

# ── config ────────────────────────────────────────────────────────────────────
ABN = os.getenv("ABN", "56628117363")
PRECINCT = os.getenv("RAG_HUNTER_PRECINCT", "Albury Logic Industrial Estate")
MAX_RESULTS = int(os.getenv("RAG_HUNTER_MAX_RESULTS", "5"))
DRY_RUN_ENV = os.getenv("RAG_HUNTER_DRY_RUN", "0") == "1"

DEFAULT_OBJECTIVE = (
    "infrastructure stress assessment and structural monitoring services "
    "for industrial operators in the Albury-Wodonga corridor"
)
OBJECTIVE = os.getenv("RAG_HUNTER_OBJECTIVE", DEFAULT_OBJECTIVE)

DEFAULT_TARGETS = [
    {"org": "Visy", "role": "Managing Director"},
    {"org": "O'Brien Logistics", "role": "Managing Director"},
]


def _load_targets() -> List[Dict[str, str]]:
    raw = os.getenv("RAG_HUNTER_TARGETS")
    if raw:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            log.warning("RAG_HUNTER_TARGETS is not valid JSON — using defaults")
    return DEFAULT_TARGETS


# ── dork engine ───────────────────────────────────────────────────────────────

def build_dork_queries(org: str, role: str, precinct: str) -> List[str]:
    """
    Return a ranked list of targeted search query strings for public-web
    intelligence gathering.  No credentials are embedded in queries.
    """
    queries = [
        # LinkedIn dork — best for role/org confirmation
        f'site:linkedin.com/in "{role}" "{org}"',
        # Company page + contact
        f'"{org}" "{role}" "{precinct}" contact email',
        # News/press-release mentions
        f'"{org}" "{role}" site:au OR site:com.au announcement 2024 OR 2025',
        # Business registry
        f'"{org}" director ABN site:abr.business.gov.au OR site:asic.gov.au',
        # Precinct-specific directory
        f'"{org}" "{precinct}" logistics OR manufacturing directory',
    ]
    return queries


# ── Crawlbase fetch ───────────────────────────────────────────────────────────

_CB_BASE = "https://api.crawlbase.com/"


def crawlbase_fetch(url: str, use_js: bool = False) -> Optional[str]:
    """
    Fetch *url* via Crawlbase.  Use JS render token for SPA/LinkedIn pages.
    Returns page text (stripped of most HTML), or None on failure.
    """
    if not HAS_REQUESTS:
        log.error("requests not installed")
        return None

    token_key = "CRAWLBASE_JS_TOKEN" if use_js else "CRAWLBASE_NORMAL_TOKEN"
    token = os.getenv(token_key)
    if not token:
        log.warning("%s not set", token_key)
        return None

    params = {"token": token, "url": url, "format": "text"}
    try:
        resp = requests.get(_CB_BASE, params=params, timeout=45)
        if resp.status_code == 200:
            return resp.text[:8000]  # cap to avoid huge payloads
        log.warning("Crawlbase %d for %s", resp.status_code, url)
        return None
    except Exception as exc:
        log.error("Crawlbase fetch error: %s", exc)
        return None


def dork_search_via_crawlbase(query: str) -> Optional[str]:
    """
    Execute a Google search query via Crawlbase and return result text.
    Rate-limited to respect Crawlbase quotas.
    """
    encoded = urllib.parse.quote_plus(query)
    search_url = f"https://www.google.com/search?q={encoded}&num=10"
    result = crawlbase_fetch(search_url, use_js=False)
    time.sleep(1.5)  # polite crawl delay
    return result


# ── contact extraction ────────────────────────────────────────────────────────

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_PHONE_AU = re.compile(r"(?:\+61|0)[2-578]\d{8}")
_NAME_HINT = re.compile(
    r"\b(Mr|Ms|Mrs|Dr|Prof)\.?\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})",
    re.UNICODE,
)


def extract_contacts(text: str, org: str, role: str) -> List[Dict[str, Any]]:
    """
    Parse raw page text for email addresses, phone numbers, and named persons
    associated with *org* and *role*.
    """
    contacts = []
    emails = list(set(_EMAIL_RE.findall(text)))
    phones = list(set(_PHONE_AU.findall(text)))
    names = [f"{m.group(1)} {m.group(2)}" for m in _NAME_HINT.finditer(text)]

    if emails or phones or names:
        contacts.append({
            "org": org,
            "role": role,
            "emails": emails[:5],
            "phones": phones[:3],
            "possible_names": list(set(names))[:5],
            "snippet": text[:400].replace("\n", " ").strip(),
        })
    return contacts


# ── RAG scoring (pure Python cosine, no heavy deps) ───────────────────────────

def _tfidf_vector(text: str, vocab: List[str]) -> List[float]:
    """Minimal bag-of-words TF vector over *vocab* tokens."""
    tokens = re.findall(r"[a-z]+", text.lower())
    counts: Dict[str, int] = {}
    for t in tokens:
        counts[t] = counts.get(t, 0) + 1
    total = max(len(tokens), 1)
    return [counts.get(w, 0) / total for w in vocab]


def _cosine(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def rag_score_contacts(
    contacts: List[Dict[str, Any]],
    objective: str,
) -> List[Dict[str, Any]]:
    """
    Score each contact snippet against the outreach *objective* using
    TF cosine similarity.  Returns contacts sorted by descending score.
    """
    if not contacts:
        return []

    all_text = [objective] + [c.get("snippet", "") for c in contacts]
    vocab = list(
        {tok for text in all_text for tok in re.findall(r"[a-z]+", text.lower())}
    )

    obj_vec = _tfidf_vector(objective, vocab)
    scored = []
    for c in contacts:
        vec = _tfidf_vector(c.get("snippet", ""), vocab)
        score = _cosine(obj_vec, vec)
        scored.append({**c, "rag_score": round(score, 4)})

    return sorted(scored, key=lambda x: x["rag_score"], reverse=True)


# ── Supabase upsert ───────────────────────────────────────────────────────────

def _supabase_headers() -> Optional[Dict[str, str]]:
    key = os.getenv("SUPABASE_SERVICE_KEY")
    if not key:
        return None
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }


def upsert_contacts(contacts: List[Dict[str, Any]]) -> bool:
    if not HAS_REQUESTS or not contacts:
        return False
    base_url = os.getenv("SUPABASE_URL")
    headers = _supabase_headers()
    if not base_url or not headers:
        log.warning("Supabase credentials not set — skipping upsert")
        return False
    try:
        payload = []
        ts = datetime.now(timezone.utc).isoformat()
        for c in contacts:
            for email in c.get("emails", ["unknown"]) or ["unknown"]:
                payload.append({
                    "abn": ABN,
                    "org": c["org"],
                    "role": c["role"],
                    "email": email,
                    "phones": json.dumps(c.get("phones", [])),
                    "possible_names": json.dumps(c.get("possible_names", [])),
                    "rag_score": c.get("rag_score", 0.0),
                    "snippet": c.get("snippet", "")[:500],
                    "updated_at": ts,
                })
        resp = requests.post(
            f"{base_url}/rest/v1/contacts",
            headers=headers,
            json=payload,
            timeout=20,
        )
        resp.raise_for_status()
        log.info("Upserted %d contact records to Supabase", len(payload))
        return True
    except Exception as exc:
        log.error("Supabase upsert failed: %s", exc)
        return False


# ── main hunter pipeline ──────────────────────────────────────────────────────

def hunt(
    targets: List[Dict[str, str]],
    precinct: str,
    objective: str,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Full RAG hunt pipeline.  Returns structured report.
    """
    ts = datetime.now(timezone.utc).isoformat()
    all_leads: List[Dict[str, Any]] = []

    for target in targets:
        org = target.get("org", "Unknown")
        role = target.get("role", "Managing Director")
        log.info("Hunting: %s — %s @ %s", role, org, precinct)

        queries = build_dork_queries(org, role, precinct)
        target_contacts: List[Dict[str, Any]] = []

        for query in queries[:3]:  # top 3 queries per target
            log.debug("Query: %s", query)
            text = dork_search_via_crawlbase(query)
            if not text:
                continue
            found = extract_contacts(text, org, role)
            target_contacts.extend(found)

        scored = rag_score_contacts(target_contacts, objective)
        top = scored[:MAX_RESULTS]

        if top and not dry_run:
            upsert_contacts(top)

        all_leads.extend(top)
        log.info("  → %d leads found for %s", len(top), org)

    report = {
        "abn": ABN,
        "generated_at": ts,
        "precinct": precinct,
        "objective": objective,
        "targets_searched": len(targets),
        "total_leads": len(all_leads),
        "dry_run": dry_run,
        "leads": all_leads,
        "summary": (
            f"Found {len(all_leads)} leads across {len(targets)} targets "
            f"in {precinct}. Top score: "
            + (f"{all_leads[0]['rag_score']:.4f} ({all_leads[0]['org']})" if all_leads else "N/A")
        ),
    }
    return report


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="FractalMesh Industrial RAG Hunter")
    parser.add_argument(
        "--targets",
        default=None,
        help='JSON list of {"org": ..., "role": ...} dicts',
    )
    parser.add_argument(
        "--precinct",
        default=PRECINCT,
        help="Search precinct modifier",
    )
    parser.add_argument(
        "--objective",
        default=OBJECTIVE,
        help="Plain-text outreach objective for RAG scoring",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not write to Supabase",
    )
    args = parser.parse_args()

    targets = _load_targets()
    if args.targets:
        try:
            targets = json.loads(args.targets)
        except json.JSONDecodeError as exc:
            log.error("Invalid --targets JSON: %s", exc)
            sys.exit(1)

    dry = args.dry_run or DRY_RUN_ENV
    report = hunt(targets, args.precinct, args.objective, dry_run=dry)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
