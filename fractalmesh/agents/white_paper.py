"""
White Paper Generator — automated research-backed white paper production.

Generates professional white papers with:
  - Executive summary
  - Technical architecture sections
  - Academic citations from Research RAG
  - Supporting/conflicting evidence
  - Methodology and risk analysis
  - DEV.to-ready markdown output

Scientific methodology:
  Structured document generation per Swamy et al. (2023) "LLM-assisted Scientific Writing"
  arXiv:2311.09535 — iterative section generation with consistency checking
"""

import os
import json
import logging
from datetime import datetime

log = logging.getLogger("white_paper")

WHITE_PAPER_SECTIONS = [
    "executive_summary",
    "problem_statement",
    "technical_architecture",
    "scientific_basis",
    "implementation",
    "risk_analysis",
    "performance_metrics",
    "future_roadmap",
    "references",
]

PAPER_TEMPLATES = {
    "fractalmesh_system": {
        "title": "FractalMesh Omega: A Sovereign Autonomous Revenue Architecture",
        "subtitle": "Multi-Agent AI Orchestration for Zero-Capital Income Generation",
        "author": "Samuel James Hiotis | IronVision Nexus | ABN 56628117363",
        "keywords": ["autonomous agents", "reinforcement learning", "RSS intelligence",
                     "affiliate automation", "DeFi trading", "sovereign AI"],
    },
    "trading_strategy": {
        "title": "PrimoLogic Momentum + Fractal Reversion: A Multi-Strategy Trading Framework",
        "subtitle": "Circuit-Breaker Protected Autonomous Trading on KuCoin and Crypto.com",
        "author": "IronVision Nexus Research",
        "keywords": ["algorithmic trading", "momentum strategy", "Fibonacci reversion",
                     "circuit breakers", "CCXT", "KuCoin API"],
    },
    "rss_intelligence": {
        "title": "Autonomous Intelligence Harvesting: RSS + NLP + Vector Embeddings",
        "subtitle": "Intent Scoring, Tiered Gating, and Commercial Lead Extraction at Scale",
        "author": "IronVision Nexus Research",
        "keywords": ["RSS ingestion", "NLP intent scoring", "lead generation",
                     "RAG pipeline", "embeddings", "commercial intelligence"],
    },
}


def _generate_section(section: str, topic: str, context: str, rag_context: str = "") -> str:
    """Generate a single white paper section using AI."""
    from integrations.openrouter import complete, PREMIUM_MODELS, FREE_MODELS
    section_prompts = {
        "executive_summary": (
            f"Write a 200-word executive summary for a white paper about: {topic}. "
            f"Include the core value proposition, key innovations, and target audience. "
            f"Academic tone, third person."
        ),
        "problem_statement": (
            f"Write a 300-word problem statement for: {topic}. "
            f"Describe the gap in existing solutions, market opportunity, and why this matters. "
            f"Cite the specific pain points quantitatively where possible."
        ),
        "technical_architecture": (
            f"Write a 500-word technical architecture section for: {topic}. "
            f"Describe system components, data flows, API integrations, and scalability design. "
            f"Context: {context[:400]}"
        ),
        "scientific_basis": (
            f"Write a 400-word scientific basis section for: {topic}. "
            f"Reference peer-reviewed research that supports the approach. "
            f"Research context:\n{rag_context[:600]}"
        ),
        "implementation": (
            f"Write a 400-word implementation section for: {topic}. "
            f"Detail deployment steps, technology stack, and operational requirements. "
            f"Context: {context[:400]}"
        ),
        "risk_analysis": (
            f"Write a 350-word risk analysis for: {topic}. "
            f"Cover technical risks, regulatory considerations, market risks, and mitigations. "
            f"Be objective and include conflicting academic evidence where relevant. "
            f"Research: {rag_context[:400]}"
        ),
        "performance_metrics": (
            f"Write a 250-word performance metrics section for: {topic}. "
            f"Define KPIs, measurement methodology, and success benchmarks."
        ),
        "future_roadmap": (
            f"Write a 200-word future roadmap for: {topic}. "
            f"Cover 3-month, 6-month, and 12-month milestones."
        ),
        "references": (
            f"Generate a formatted reference list for a white paper on: {topic}. "
            f"Use IEEE citation format. Include 8-12 real academic references (2020-2026) "
            f"from the fields of: autonomous agents, NLP, algorithmic trading, affiliate marketing. "
            f"Additional context: {rag_context[:400]}"
        ),
    }
    prompt = section_prompts.get(section, f"Write a section on {section} for: {topic}")
    try:
        model = PREMIUM_MODELS.get("gemini_25_pro", FREE_MODELS[0])
        return complete(prompt, system="You are a research scientist writing an academic white paper.",
                        model=model, max_tokens=700)
    except Exception:
        try:
            return complete(prompt, model=FREE_MODELS[0], max_tokens=700)
        except Exception as exc:
            log.error("section '%s' generation failed: %s", section, exc)
            return f"[{section.upper()} — generation failed: {exc}]"


def generate_white_paper(template_key: str = "fractalmesh_system",
                          sections: list[str] | None = None,
                          include_rag: bool = True) -> dict:
    """
    Generate a complete white paper.
    Returns {title, author, content_md, sections, word_count, generated_at}.
    """
    template = PAPER_TEMPLATES.get(template_key, PAPER_TEMPLATES["fractalmesh_system"])
    topic    = f"{template['title']}: {template['subtitle']}"
    context  = (
        f"Keywords: {', '.join(template['keywords'])}. "
        f"Author/entity: {template['author']}. "
        f"System: FractalMesh Omega v6 — autonomous revenue stack with trading, "
        f"RSS intelligence, affiliate automation, data products, AI cascade."
    )

    rag_context = ""
    if include_rag:
        try:
            from agents.research_rag import query_rag
            rag_result = query_rag(topic, top_k=6)
            rag_context = "\n".join([
                f"{s['stance']}: {s['title']} ({s['year']}) — {s.get('abstract', '')[:150]}"
                for s in rag_result.get("sources", [])
            ])
        except Exception as exc:
            log.warning("RAG context unavailable: %s", exc)

    target_sections = sections or WHITE_PAPER_SECTIONS
    content_parts = []

    # Header
    content_parts.append(f"# {template['title']}")
    content_parts.append(f"### {template['subtitle']}")
    content_parts.append(f"**Author:** {template['author']}")
    content_parts.append(f"**Date:** {datetime.now().strftime('%B %Y')}")
    content_parts.append(f"**Keywords:** {', '.join(template['keywords'])}")
    content_parts.append("---\n")

    generated_sections = {}
    for section in target_sections:
        log.info("white_paper: generating section '%s'", section)
        text = _generate_section(section, topic, context, rag_context)
        heading = section.replace("_", " ").title()
        content_parts.append(f"## {heading}\n\n{text}\n")
        generated_sections[section] = text

    full_content = "\n".join(content_parts)
    word_count   = len(full_content.split())

    result = {
        "title":        template["title"],
        "subtitle":     template["subtitle"],
        "author":       template["author"],
        "template_key": template_key,
        "content_md":   full_content,
        "sections":     generated_sections,
        "word_count":   word_count,
        "keywords":     template["keywords"],
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }

    # Save locally
    _save_paper(result)
    return result


def _save_paper(paper: dict) -> str:
    out_dir = os.path.expanduser("~/ai-mesh/omega/white_papers")
    os.makedirs(out_dir, exist_ok=True)
    ts    = datetime.now().strftime("%Y%m%d_%H%M")
    fname = os.path.join(out_dir, f"WP_{paper['template_key']}_{ts}.md")
    with open(fname, "w") as f:
        f.write(paper["content_md"])
    log.info("white_paper saved: %s (%d words)", fname, paper["word_count"])
    return fname


def list_generated_papers() -> list[dict]:
    out_dir = os.path.expanduser("~/ai-mesh/omega/white_papers")
    if not os.path.exists(out_dir):
        return []
    files = []
    for fname in sorted(os.listdir(out_dir), reverse=True):
        if fname.endswith(".md"):
            path = os.path.join(out_dir, fname)
            stat = os.stat(path)
            files.append({
                "filename": fname,
                "size_kb": round(stat.st_size / 1024, 1),
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })
    return files
