"""
Lead enricher — re-processes stored leads with unified AI to improve
summaries, rescore, generate affiliate angles, and tag content.
"""

import logging
from integrations.supabase_client import query, update
from integrations.unified_ai import enhance_for_seo, score_lead, generate_affiliate_email
from integrations import slack

log = logging.getLogger("lead_enricher")


def enrich_batch(limit: int = 20) -> int:
    """Enrich leads that have no enhanced summary yet."""
    leads = query("leads", limit=limit)
    unenriched = [l for l in leads if not l.get("raw", {}).get("enriched")]
    enriched_count = 0

    for lead in unenriched[:limit]:
        try:
            enhanced = enhance_for_seo(lead["title"], lead.get("summary", ""))
            new_score = score_lead(lead["title"], enhanced)
            tier = "premium" if new_score >= 75 else "standard" if new_score >= 55 else "basic"

            raw = lead.get("raw") or {}
            raw["enriched"] = True
            raw["affiliate_angles"] = _get_angles(lead["title"], enhanced)

            update("leads", lead["id"], {
                "summary":     enhanced,
                "intent_score": new_score,
                "tier":        tier,
                "raw":         raw,
            })
            enriched_count += 1
        except Exception as exc:
            log.warning("enrich failed for %s: %s", lead.get("id"), exc)

    if enriched_count:
        log.info("enriched %d leads", enriched_count)
        slack.send(f"Lead enrichment: {enriched_count} leads upgraded", level="info")
    return enriched_count


def _get_angles(title: str, content: str) -> list[str]:
    from integrations.unified_ai import complete
    prompt = (
        f"List 3 affiliate product categories for:\nTitle: {title}\n{content[:300]}\n"
        f"Reply with 3 numbered items only."
    )
    try:
        result = complete(prompt, max_tokens=150)
        return [l.strip() for l in result.split("\n") if l.strip() and l[0].isdigit()][:3]
    except Exception:
        return []


def generate_outreach_email(niche: str, product_angle: str, recipient_name: str = "there") -> dict:
    return generate_affiliate_email(niche, product_angle, recipient_name)
