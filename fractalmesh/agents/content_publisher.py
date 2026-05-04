"""
Content publisher — auto-publishes top leads as DEV.to articles
and syncs summaries to Slack + Make.com.
"""

import logging
from integrations.supabase_client import query, update
from integrations.devto import publish_article
from integrations import slack, make_webhooks
from integrations.unified_ai import complete

log = logging.getLogger("content_publisher")


def _build_article(leads: list[dict]) -> dict:
    titles = "\n".join(f"- {l['title']}" for l in leads[:10])
    prompt = (
        f"Write a DEV.to article intro paragraph (150 words max) for a curated "
        f"intelligence digest. Professional, data-focused tone.\n"
        f"Topics covered:\n{titles}"
    )
    intro = complete(prompt, max_tokens=200)

    lines = [
        "## FractalMesh Intelligence Digest\n",
        intro, "\n",
        "---\n",
        "### Top Leads This Cycle\n",
    ]
    for lead in leads[:15]:
        score = lead.get("intent_score", 0)
        lines.append(
            f"**[{lead['title']}]({lead.get('url', '#')})** "
            f"— Score: {score:.0f} | Tier: {lead.get('tier','')}\n\n"
            f"{lead.get('summary', '')}\n"
        )

    tags = ["productivity", "data", "automation", "startup", "ai"]
    return {
        "title":         "FractalMesh Intelligence Digest",
        "body_markdown": "\n".join(lines),
        "tags":          tags,
        "published":     False,  # set True to go live automatically
    }


def publish_digest(min_score: float = 60.0, published: bool = False) -> dict | None:
    leads = query("leads", limit=20)
    top = [l for l in leads if float(l.get("intent_score", 0)) >= min_score]
    if not top:
        log.info("no leads above threshold %.0f for digest", min_score)
        return None

    article = _build_article(top)
    article["published"] = published
    result = publish_article(
        title=article["title"],
        body_markdown=article["body_markdown"],
        tags=article["tags"],
        published=published,
    )

    slack.send("DEV.to digest published", level="info", fields={
        "leads": str(len(top)),
        "url": result.get("url", ""),
        "published": str(published),
    })
    make_webhooks.trigger("digest.published", {"count": len(top), "url": result.get("url")})
    return result
