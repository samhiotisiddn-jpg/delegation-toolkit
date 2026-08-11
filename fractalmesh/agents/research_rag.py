"""
Research RAG v1 — Retrieval-Augmented Generation over academic papers and RSS feeds.

Scientific foundation:
  - Lewis et al. (2020) "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks"
    arXiv:2005.11401 — foundational RAG architecture
  - Karpukhin et al. (2020) "Dense Passage Retrieval for Open-Domain QA"
    arXiv:2004.12832 — dense vector retrieval
  - Zhao et al. (2023) "A Survey of Large Language Models" arXiv:2303.18223
  - CONFLICTING: Shi et al. (2023) "Large Language Models Can Be Easily Distracted by Irrelevant
    Context" arXiv:2302.00093 — noise in RAG context degrades accuracy

Pipeline:
  1. Ingest papers from arxiv / Semantic Scholar / CrossRef
  2. Embed title+abstract via text-embedding-3-small (1536d)
  3. Store vectors + metadata in Supabase (JSON column, no pgvector needed)
  4. Query: embed query → cosine rank → return top-k → feed to LLM
"""

import json
import logging
import hashlib
import urllib.request
import urllib.parse

log = logging.getLogger("research_rag")

_ARXIV_SEARCH  = "https://export.arxiv.org/api/query"
_SEMANTIC_BASE = "https://api.semanticscholar.org/graph/v1"
_CROSSREF_BASE = "https://api.crossref.org/works"

# In-memory cache (evicted on restart; Supabase is persistent store)
_VECTOR_CACHE: dict[str, dict] = {}

RESEARCH_TOPICS = [
    # Supporting the system
    "reinforcement learning trading cryptocurrency",
    "multi-agent AI autonomous revenue generation",
    "RSS feed NLP intent scoring lead generation",
    "affiliate marketing automation machine learning",
    "knowledge graph market intelligence RAG",
    "OSINT automated lead harvesting",
    "autonomous trading deep reinforcement learning PPO",
    # Conflicting / critical
    "risks autonomous AI trading systems",
    "LLM hallucination RAG accuracy degradation",
    "cryptocurrency trading strategy overfitting",
]


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:20]


def search_arxiv(query: str, max_results: int = 10) -> list[dict]:
    """Search arxiv API and return structured paper records."""
    import xml.etree.ElementTree as ET
    params = urllib.parse.urlencode({
        "search_query": f"all:{urllib.parse.quote(query)}",
        "max_results": max_results,
        "sortBy": "relevance",
        "sortOrder": "descending",
    })
    try:
        req = urllib.request.Request(
            f"{_ARXIV_SEARCH}?{params}",
            headers={"User-Agent": "FractalMesh/6.0 (research@fractalmesh.io)"},
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            tree = ET.fromstring(r.read())
        ns = {"atom": "http://www.w3.org/2005/Atom",
              "arxiv": "http://arxiv.org/schemas/atom"}
        papers = []
        for entry in tree.findall("atom:entry", ns):
            title   = entry.findtext("atom:title", "", ns).strip().replace("\n", " ")
            summary = entry.findtext("atom:summary", "", ns).strip().replace("\n", " ")
            link    = entry.findtext("atom:id", "", ns).strip()
            authors = [a.findtext("atom:name", "", ns) for a in entry.findall("atom:author", ns)]
            published = entry.findtext("atom:published", "", ns)[:10]
            cats    = [c.get("term", "") for c in entry.findall("atom:category", ns)]
            papers.append({
                "id":        _sha(link),
                "title":     title,
                "abstract":  summary[:800],
                "authors":   authors[:5],
                "url":       link,
                "published": published,
                "source":    "arxiv",
                "categories": cats,
                "query":     query,
            })
        return papers
    except Exception as exc:
        log.warning("arxiv search '%s': %s", query, exc)
        return []


def search_semantic_scholar(query: str, limit: int = 10) -> list[dict]:
    """Search Semantic Scholar open API."""
    params = urllib.parse.urlencode({
        "query": query,
        "limit": limit,
        "fields": "title,abstract,authors,year,externalIds,citationCount,url",
    })
    try:
        req = urllib.request.Request(
            f"{_SEMANTIC_BASE}/paper/search?{params}",
            headers={"User-Agent": "FractalMesh/6.0"},
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read())
        papers = []
        for p in data.get("data", []):
            authors = [a.get("name", "") for a in p.get("authors", [])][:5]
            papers.append({
                "id":        _sha(p.get("paperId", "") + p.get("title", "")),
                "title":     p.get("title", ""),
                "abstract":  (p.get("abstract") or "")[:800],
                "authors":   authors,
                "url":       p.get("url", ""),
                "published": str(p.get("year", "")),
                "source":    "semantic_scholar",
                "citations": p.get("citationCount", 0),
                "query":     query,
            })
        return papers
    except Exception as exc:
        log.warning("semantic scholar '%s': %s", query, exc)
        return []


def classify_stance(abstract: str, query: str) -> str:
    """Classify whether a paper SUPPORTS or CONFLICTS with the system query."""
    from integrations.openrouter import complete, FREE_MODELS
    prompt = (
        f"Does this academic abstract SUPPORT or CONFLICT with the topic: '{query}'?\n"
        f"Abstract: {abstract[:400]}\n"
        f"Reply with exactly one word: SUPPORT or CONFLICT"
    )
    try:
        r = complete(prompt, model=FREE_MODELS[0], max_tokens=5)
        return "SUPPORT" if "SUPPORT" in r.upper() else "CONFLICT"
    except Exception:
        return "SUPPORT"


def embed_papers(papers: list[dict]) -> list[dict]:
    """Embed title+abstract for each paper, store vector in dict."""
    from integrations.openrouter import embed
    texts = [f"{p['title']} {p['abstract'][:300]}" for p in papers]
    try:
        vectors = embed(texts)
        for p, v in zip(papers, vectors):
            p["vector"] = v
    except Exception as exc:
        log.warning("embed_papers failed: %s", exc)
        for p in papers:
            p["vector"] = []
    return papers


def store_papers(papers: list[dict]) -> int:
    """Store papers in Supabase research_papers table."""
    from integrations.supabase_client import insert
    stored = 0
    for p in papers:
        try:
            insert("research_papers", {
                "paper_id":  p["id"],
                "title":     p["title"],
                "abstract":  p["abstract"],
                "authors":   p.get("authors", []),
                "url":       p["url"],
                "published": p.get("published", ""),
                "source":    p.get("source", ""),
                "query":     p.get("query", ""),
                "stance":    p.get("stance", "SUPPORT"),
                "citations": p.get("citations", 0),
                "vector":    p.get("vector", []),
            })
            _VECTOR_CACHE[p["id"]] = p
            stored += 1
        except Exception:
            pass  # dedup
    return stored


def query_rag(question: str, top_k: int = 5) -> dict:
    """
    RAG query: embed question → cosine rank cached papers → LLM synthesis.
    Returns {answer, sources, supporting, conflicting}.
    """
    from integrations.openrouter import embed, cosine_similarity, complete, FREE_MODELS

    if not _VECTOR_CACHE:
        _load_cache()

    if not _VECTOR_CACHE:
        return {"answer": "No research papers indexed yet.", "sources": [], "supporting": [], "conflicting": []}

    try:
        q_vec = embed([question])[0]
    except Exception:
        return {"answer": "Embedding service unavailable.", "sources": []}

    scored = []
    for pid, paper in _VECTOR_CACHE.items():
        vec = paper.get("vector", [])
        if vec:
            sim = cosine_similarity(q_vec, vec)
            scored.append((sim, paper))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = [p for _, p in scored[:top_k]]

    context_parts = []
    supporting = []
    conflicting = []
    for p in top:
        label = p.get("stance", "SUPPORT")
        blurb = f"[{label}] {p['title']} ({p.get('published', '')}) — {p['abstract'][:250]}"
        context_parts.append(blurb)
        if label == "CONFLICT":
            conflicting.append({"title": p["title"], "url": p["url"], "year": p.get("published", "")})
        else:
            supporting.append({"title": p["title"], "url": p["url"], "year": p.get("published", "")})

    context = "\n\n".join(context_parts)
    prompt = (
        f"Based on these research papers, answer the question: '{question}'\n\n"
        f"Papers (SUPPORT/CONFLICT labeled):\n{context}\n\n"
        f"Provide a concise 3-5 sentence synthesis, noting where papers agree/conflict."
    )
    answer = complete(prompt, system="You are a research analyst.", model=FREE_MODELS[0], max_tokens=400)

    return {
        "answer": answer,
        "sources": [{"title": p["title"], "url": p["url"], "stance": p.get("stance", "?"),
                     "year": p.get("published", "")} for p in top],
        "supporting": supporting,
        "conflicting": conflicting,
    }


def _load_cache() -> None:
    """Load paper vectors from Supabase into memory cache."""
    from integrations.supabase_client import query
    try:
        rows = query("research_papers", limit=500)
        for r in rows:
            if r.get("vector"):
                _VECTOR_CACHE[r["paper_id"]] = r
        log.info("research_rag: loaded %d papers into cache", len(_VECTOR_CACHE))
    except Exception as exc:
        log.warning("load_cache failed: %s", exc)


def ingest_all_topics(max_per_topic: int = 8) -> int:
    """Fetch papers for all RESEARCH_TOPICS, embed, classify, store."""
    total = 0
    for topic in RESEARCH_TOPICS:
        papers = search_arxiv(topic, max_per_topic)
        papers += search_semantic_scholar(topic, max_per_topic // 2)
        for p in papers:
            p["stance"] = classify_stance(p["abstract"], topic)
        papers = embed_papers(papers)
        n = store_papers(papers)
        total += n
        log.info("research_rag: topic='%s' → %d new papers", topic, n)
    return total


def generate_system_report() -> str:
    """Generate a full academic assessment of the FractalMesh system."""
    from integrations.openrouter import complete_owl

    _load_cache()
    supporting = [p for p in _VECTOR_CACHE.values() if p.get("stance") == "SUPPORT"]
    conflicting = [p for p in _VECTOR_CACHE.values() if p.get("stance") == "CONFLICT"]

    sup_text = "\n".join(f"- {p['title']} ({p.get('published','')})" for p in supporting[:10])
    con_text = "\n".join(f"- {p['title']} ({p.get('published','')})" for p in conflicting[:5])

    prompt = (
        "Write a 600-word academic-style assessment of the FractalMesh autonomous revenue system, "
        "covering: (1) scientific basis for each component, (2) peer-reviewed evidence supporting "
        "the architecture, (3) known risks and conflicting research, (4) recommended mitigations.\n\n"
        f"Supporting papers:\n{sup_text or 'none indexed'}\n\n"
        f"Conflicting papers:\n{con_text or 'none indexed'}\n\n"
        "Write in professional academic tone with in-text citations."
    )
    try:
        return complete_owl(prompt, max_tokens=900)
    except Exception:
        from integrations.openrouter import complete, FREE_MODELS
        return complete(prompt, model=FREE_MODELS[0], max_tokens=900)
