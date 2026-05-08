"""
Unified AI router — cascades through Venice → OpenAI → Google Gemini →
OpenRouter → xAI → GitHub AI.
Picks the first provider that succeeds.
"""

import logging
from typing import Callable

log = logging.getLogger("unified_ai")


def _try(fn: Callable, label: str, *args, **kwargs) -> str | None:
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        log.warning("[%s] failed: %s", label, exc)
        return None


def complete(
    prompt: str,
    system: str = "You are a helpful assistant.",
    max_tokens: int = 800,
    prefer: str = "venice",
) -> str:
    """Route to best available AI, cascade on failure."""
    from integrations import venice_ai, openai_client, google_ai, openrouter, xai_client, github_ai

    order = {
        "venice":     [(venice_ai.complete,     "venice",     venice_ai.VENICE_MODELS[0])],
        "openai":     [(openai_client.complete,  "openai",     "gpt-4o-mini")],
        "google":     [(google_ai.complete,      "google",     "gemini-2.0-flash")],
        "openrouter": [(openrouter.complete,     "openrouter", openrouter.FREE_MODELS[0])],
        "xai":        [(xai_client.complete,     "xai",        "grok-3")],
        "github":     [(github_ai.complete,      "github",     "microsoft/Phi-4-multimodal-instruct")],
    }.get(prefer, [])

    fallbacks = [
        (venice_ai.complete,    "venice",     venice_ai.VENICE_MODELS[0]),
        (openai_client.complete, "openai",    "gpt-4o-mini"),
        (google_ai.complete,    "google",     "gemini-2.0-flash"),
        (openrouter.complete,   "openrouter", openrouter.FREE_MODELS[0]),
        (xai_client.complete,   "xai",        "grok-3"),
        (github_ai.complete,    "github",     "microsoft/Phi-4-multimodal-instruct"),
    ]

    all_providers = order + [f for f in fallbacks if f[1] != prefer]

    for fn, label, model in all_providers:
        result = _try(fn, label, prompt, system, model, max_tokens)
        if result:
            log.info("unified_ai: served by %s", label)
            return result

    return "All AI providers unavailable."


def score_lead(title: str, summary: str) -> float:
    prompt = (
        f"Rate the commercial/business value 0-100.\n"
        f"Title: {title}\nSummary: {summary[:300]}\n"
        f"Reply with ONLY a number. No explanation."
    )
    try:
        r = complete(prompt, max_tokens=10)
        return min(100.0, max(0.0, float(r.strip().split()[0])))
    except Exception:
        return 0.0


def enhance_for_seo(title: str, content: str) -> str:
    prompt = (
        f"Rewrite as a concise 2-sentence SEO-optimised summary for a data feed.\n"
        f"Title: {title}\nOriginal: {content[:400]}"
    )
    try:
        return complete(prompt, max_tokens=150)
    except Exception:
        return content


def generate_affiliate_email(niche: str, product_angle: str, recipient_name: str = "there") -> dict:
    prompt = (
        f"Write a short, professional affiliate outreach email.\n"
        f"Niche: {niche}\nProduct: {product_angle}\nRecipient: {recipient_name}\n"
        f"Format:\nSUBJECT: ...\nBODY:\n..."
    )
    result = complete(prompt, max_tokens=300)
    lines = result.split("\n")
    subject = next((l.replace("SUBJECT:", "").strip() for l in lines if "SUBJECT:" in l), "Partnership opportunity")
    body_start = next((i for i, l in enumerate(lines) if "BODY:" in l), 1)
    body = "\n".join(lines[body_start + 1:]).strip()
    return {"subject": subject, "body": body}
