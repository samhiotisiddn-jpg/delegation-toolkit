#!/usr/bin/env python3
"""
fractalmesh/agents/rag_hunter.py  —  v2
==========================================
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
3. DEDUPLICATE — check Supabase `contacts` table and skip already-known leads
   unless they have stale data (--refresh-days threshold).
4. ENRICH — cross-reference fetched contacts against Supabase `contacts`
   table; upsert new and updated findings.
5. BM25 SCORE — rank contact snippets against the active outreach objective
   using Okapi BM25 (better recall than raw TF-IDF cosine).
6. COMPOSITE PRIORITY — combine BM25 relevance, contact completeness, and
   data freshness into a single `priority_score`.
7. REPORT — emit ABN-watermarked JSON with ranked lead list.

Scoring upgrades (v2 vs v1)
----------------------------
- TF-IDF cosine replaced with pure-Python Okapi BM25 (k1=1.5, b=0.75).
- `priority_score` = 0.6 × bm25_norm + 0.3 × completeness + 0.1 × recency_norm
- Contact completeness: email (+0.5), phone (+0.3), name (+0.2) — max 1.0.
- Recency norm: 1.0 if newly found this run; 0.5 if fetched from Supabase cache.

Multi-precinct support
----------------------
RAG_HUNTER_PRECINCTS env var accepts a JSON list of precinct strings.  When
set it supersedes RAG_HUNTER_PRECINCT.  The hunt runs across all precincts and
deduplicates results by (org, email) before ranking.

Environment variables (never hardcode):
    CRAWLBASE_NORMAL_TOKEN      — Crawlbase plain HTTP token
    CRAWLBASE_JS_TOKEN          — Crawlbase JS-render token (for SPAs)
    SUPABASE_URL                — Supabase project URL
    SUPABASE_SERVICE_KEY        — Supabase service-role key
    OPENAI_API_KEY              — OpenAI key for embeddings + completion
    ABN                         — Operator ABN for watermarking
    RAG_HUNTER_TARGETS          — JSON list of {"org": ..., "role": ...}
    RAG_HUNTER_PRECINCT         — search modifier (default: "Albury Logic Industrial Estate")
    RAG_HUNTER_PRECINCTS        — JSON list of precinct strings (overrides RAG_HUNTER_PRECINCT)
    RAG_HUNTER_MAX_RESULTS      — max leads per target per precinct (default: 5)
    RAG_HUNTER_OBJECTIVE        — plain-text outreach objective for BM25 scoring
    RAG_HUNTER_DRY_RUN          — set to "1" to skip Supabase writes
    RAG_HUNTER_REFRESH_DAYS     — days before a known lead is refreshed (default: 30)

Usage:
    python3 rag_hunter.py
    python3 rag_hunter.py --dry-run
    python3 rag_hunter.py --targets '[{"org":"Visy","role":"Managing Director"}]'
    python3 rag_hunter.py --objective "infrastructure stress assessment services"
    python3 rag_hunter.py --precincts '["Albury Logic Industrial Estate","Wodonga Industrial Estate"]'
    python3 rag_hunter.py --refresh-days 14   # re-hunt leads older than 14 days
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
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

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
ABN          = os.getenv("ABN", "56628117363")
PRECINCT     = os.getenv("RAG_HUNTER_PRECINCT", "Albury Logic Industrial Estate")
MAX_RESULTS  = int(os.getenv("RAG_HUNTER_MAX_RESULTS", "5"))
DRY_RUN_ENV  = os.getenv("RAG_HUNTER_DRY_RUN", "0") == "1"
REFRESH_DAYS = int(os.getenv("RAG_HUNTER_REFRESH_DAYS", "30"))

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


def _load_precincts() -> List[str]:
    """Return list of precincts to hunt across."""
    raw = os.getenv("RAG_HUNTER_PRECINCTS")
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list) and parsed:
                return [str(p) for p in parsed]
        except json.JSONDecodeError:
            log.warning("RAG_HUNTER_PRECINCTS is not valid JSON — using RAG_HUNTER_PRECINCT")
    return [PRECINCT]


# ── dork engine ───────────────────────────────────────────────────────────────

def build_dork_queries(org: str, role: str, precinct: str) -> List[str]:
    """
    Return a ranked list of targeted search query strings for public-web
    intelligence gathering.  No credentials are embedded in queries.
    """
    return [
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
            return resp.text[:8000]
        log.warning("Crawlbase %d for %s", resp.status_code, url)
        return None
    except Exception as exc:
        log.error("Crawlbase fetch error: %s", exc)
        return None


def dork_search_via_crawlbase(query: str) -> Optional[str]:
    """Execute a Google search query via Crawlbase. Rate-limited."""
    encoded = urllib.parse.quote_plus(query)
    search_url = f"https://www.google.com/search?q={encoded}&num=10"
    result = crawlbase_fetch(search_url, use_js=False)
    time.sleep(1.5)  # polite crawl delay
    return result


# ── contact extraction ────────────────────────────────────────────────────────

_EMAIL_RE  = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_PHONE_AU  = re.compile(r"(?:\+61|0)[2-578]\d{8}")
_NAME_HINT = re.compile(
    r"\b(Mr|Ms|Mrs|Dr|Prof)\.?\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})",
    re.UNICODE,
)


def extract_contacts(text: str, org: str, role: str) -> List[Dict[str, Any]]:
    """
    Parse raw page text for email addresses, phone numbers, and named persons
    associated with *org* and *role*.
    """
    contacts: List[Dict[str, Any]] = []
    emails = list(set(_EMAIL_RE.findall(text)))
    phones = list(set(_PHONE_AU.findall(text)))
    names  = [f"{m.group(1)} {m.group(2)}" for m in _NAME_HINT.finditer(text)]

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


def contact_completeness(c: Dict[str, Any]) -> float:
    """
    Score contact data completeness on [0, 1].
    Email: 0.5, Phone: 0.3, Name: 0.2.
    """
    score = 0.0
    if c.get("emails"):
        score += 0.5
    if c.get("phones"):
        score += 0.3
    if c.get("possible_names"):
        score += 0.2
    return round(score, 3)


# ── BM25 scoring (pure Python, no heavy deps) ─────────────────────────────────

def _tokenise(text: str) -> List[str]:
    return re.findall(r"[a-z]+", text.lower())


def _build_bm25_index(
    corpus: List[str],
    k1: float = 1.5,
    b: float = 0.75,
) -> Tuple[List[Dict[str, float]], float, Dict[str, float]]:
    """
    Build a BM25 index over *corpus*.
    Returns (tf_norm_per_doc, avgdl, idf_table).
    """
    tokenised = [_tokenise(doc) for doc in corpus]
    avgdl = sum(len(t) for t in tokenised) / max(len(tokenised), 1)

    # Document frequency
    df: Dict[str, int] = {}
    for tokens in tokenised:
        for tok in set(tokens):
            df[tok] = df.get(tok, 0) + 1

    N = len(corpus)
    idf: Dict[str, float] = {
        tok: math.log((N - freq + 0.5) / (freq + 0.5) + 1)
        for tok, freq in df.items()
    }

    # TF with BM25 saturation
    tf_norm: List[Dict[str, float]] = []
    for tokens in tokenised:
        dl = len(tokens)
        counts: Dict[str, int] = {}
        for tok in tokens:
            counts[tok] = counts.get(tok, 0) + 1
        doc_tf: Dict[str, float] = {}
        for tok, cnt in counts.items():
            doc_tf[tok] = (cnt * (k1 + 1)) / (cnt + k1 * (1 - b + b * dl / max(avgdl, 1)))
        tf_norm.append(doc_tf)

    return tf_norm, avgdl, idf


def bm25_score_contacts(
    contacts: List[Dict[str, Any]],
    objective: str,
) -> List[Dict[str, Any]]:
    """
    Score each contact snippet against *objective* using Okapi BM25.
    Adds `bm25_score` and `completeness` fields; sorts by descending BM25.
    """
    if not contacts:
        return []

    snippets = [c.get("snippet", "") for c in contacts]
    tf_norms, _, idf = _build_bm25_index(snippets)
    query_tokens = _tokenise(objective)

    scored: List[Dict[str, Any]] = []
    for i, c in enumerate(contacts):
        doc_tf = tf_norms[i]
        bm25 = sum(idf.get(tok, 0.0) * doc_tf.get(tok, 0.0) for tok in query_tokens)
        completeness = contact_completeness(c)
        scored.append({**c, "bm25_score": round(bm25, 4), "completeness": completeness})

    # Normalise BM25 to [0,1] for composite scoring
    max_bm25 = max((s["bm25_score"] for s in scored), default=1.0) or 1.0
    for s in scored:
        norm = s["bm25_score"] / max_bm25
        # Composite: 60% BM25 relevance, 30% completeness, 10% recency (new=1.0)
        recency = s.pop("_recency", 1.0)
        s["priority_score"] = round(0.6 * norm + 0.3 * s["completeness"] + 0.1 * recency, 4)

    return sorted(scored, key=lambda x: x["priority_score"], reverse=True)


# ── Supabase helpers ──────────────────────────────────────────────────────────

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


def fetch_known_contacts(orgs: List[str]) -> Set[Tuple[str, str]]:
    """
    Return a set of (org, email) pairs already in Supabase contacts,
    updated within REFRESH_DAYS — these can be skipped to avoid duplicate work.
    """
    if not HAS_REQUESTS:
        return set()
    base_url = os.getenv("SUPABASE_URL")
    headers  = _supabase_headers()
    if not base_url or not headers:
        return set()

    cutoff = (datetime.now(timezone.utc) - timedelta(days=REFRESH_DAYS)).isoformat()
    known: Set[Tuple[str, str]] = set()
    try:
        read_headers = {**headers, "Prefer": "return=representation"}
        resp = requests.get(
            f"{base_url}/rest/v1/contacts",
            headers=read_headers,
            params={"updated_at": f"gte.{cutoff}", "select": "org,email", "limit": 1000},
            timeout=20,
        )
        resp.raise_for_status()
        for row in (resp.json() or []):
            if row.get("org") and row.get("email"):
                known.add((row["org"].lower(), row["email"].lower()))
    except Exception as exc:
        log.warning("Could not fetch known contacts: %s", exc)
    log.info("Known recent contacts (within %dd): %d", REFRESH_DAYS, len(known))
    return known


def upsert_contacts(contacts: List[Dict[str, Any]]) -> bool:
    if not HAS_REQUESTS or not contacts:
        return False
    base_url = os.getenv("SUPABASE_URL")
    headers  = _supabase_headers()
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
                    "bm25_score": c.get("bm25_score", 0.0),
                    "priority_score": c.get("priority_score", 0.0),
                    "completeness": c.get("completeness", 0.0),
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
    precincts: List[str],
    objective: str,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Full RAG hunt pipeline across all *precincts*.
    Deduplicates by (org, email) globally before final ranking.
    Returns structured report.
    """
    ts = datetime.now(timezone.utc).isoformat()

    # Pre-fetch known contacts to avoid redundant scraping
    orgs = [t.get("org", "") for t in targets]
    known = fetch_known_contacts(orgs) if not dry_run else set()

    # (org, email) → best contact dict (dedup across precincts)
    seen: Dict[Tuple[str, str], Dict[str, Any]] = {}

    precinct_stats: List[Dict[str, Any]] = []

    for precinct in precincts:
        precinct_leads: List[Dict[str, Any]] = []
        for target in targets:
            org  = target.get("org",  "Unknown")
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

            scored = bm25_score_contacts(target_contacts, objective)
            top = scored[:MAX_RESULTS]
            precinct_leads.extend(top)
            log.info("  → %d leads for %s @ %s", len(top), org, precinct)

        precinct_stats.append({"precinct": precinct, "leads_found": len(precinct_leads)})

        # Merge into global dedup map — keep highest priority_score per (org, email)
        for lead in precinct_leads:
            for email in lead.get("emails", ["unknown"]) or ["unknown"]:
                key = (lead["org"].lower(), email.lower())
                if key in known:
                    log.debug("Skipping known recent lead: %s / %s", lead["org"], email)
                    continue
                if key not in seen or lead["priority_score"] > seen[key]["priority_score"]:
                    seen[key] = lead

    all_leads = sorted(seen.values(), key=lambda x: x["priority_score"], reverse=True)

    if all_leads and not dry_run:
        upsert_contacts(all_leads)

    report: Dict[str, Any] = {
        "abn": ABN,
        "generated_at": ts,
        "precincts": precincts,
        "objective": objective,
        "targets_searched": len(targets),
        "total_leads": len(all_leads),
        "dry_run": dry_run,
        "refresh_days": REFRESH_DAYS,
        "precinct_stats": precinct_stats,
        "leads": all_leads,
        "summary": (
            f"Found {len(all_leads)} unique leads across {len(targets)} targets "
            f"in {len(precincts)} precinct(s). Top priority: "
            + (
                f"{all_leads[0]['priority_score']:.4f} ({all_leads[0]['org']})"
                if all_leads else "N/A"
            )
        ),
    }
    return report


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="FractalMesh Industrial RAG Hunter v2")
    parser.add_argument(
        "--targets",
        default=None,
        help='JSON list of {"org": ..., "role": ...} dicts',
    )
    parser.add_argument(
        "--precinct",
        default=PRECINCT,
        help="Single search precinct modifier",
    )
    parser.add_argument(
        "--precincts",
        default=None,
        help="JSON list of precinct strings (overrides --precinct)",
    )
    parser.add_argument(
        "--objective",
        default=OBJECTIVE,
        help="Plain-text outreach objective for BM25 scoring",
    )
    parser.add_argument(
        "--refresh-days",
        type=int,
        default=REFRESH_DAYS,
        help="Re-hunt leads older than this many days (default: 30)",
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

    if args.precincts:
        try:
            precincts = json.loads(args.precincts)
        except json.JSONDecodeError:
            log.error("Invalid --precincts JSON")
            sys.exit(1)
    else:
        precincts = _load_precincts()
        if not precincts or precincts == [PRECINCT]:
            precincts = [args.precinct]

    # Allow CLI override of refresh days
    global REFRESH_DAYS
    REFRESH_DAYS = args.refresh_days

    dry = args.dry_run or DRY_RUN_ENV
    report = hunt(targets, precincts, args.objective, dry_run=dry)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
