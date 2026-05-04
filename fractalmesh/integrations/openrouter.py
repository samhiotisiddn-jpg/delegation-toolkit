"""
OpenRouter — routes completions across 160+ models including free tier.
Defaults to a free model; set model= to override.

Env vars:
  OPENROUTER_API_KEY    main key
  OPENROUTER_MGMT_KEY   management key (model fleet control)
"""

import os
import json
import urllib.request

_BASE = "https://openrouter.ai/api/v1"

FREE_MODELS = [
    "mistralai/mistral-7b-instruct:free",
    "microsoft/phi-3-mini-128k-instruct:free",
    "meta-llama/llama-3-8b-instruct:free",
    "google/gemma-2-9b-it:free",
    "qwen/qwen-2-7b-instruct:free",
]


def _headers(mgmt: bool = False) -> dict:
    key = os.environ["OPENROUTER_MGMT_KEY"] if mgmt else os.environ["OPENROUTER_API_KEY"]
    return {
        "Authorization":  f"Bearer {key}",
        "Content-Type":   "application/json",
        "HTTP-Referer":   "https://fractalmesh.io",
        "X-Title":        "FractalMesh",
    }


def complete(
    prompt: str,
    system: str = "You are a helpful assistant.",
    model:  str = FREE_MODELS[0],
    max_tokens: int = 800,
) -> str:
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": prompt},
        ],
        "max_tokens": max_tokens,
    }).encode()
    req = urllib.request.Request(
        f"{_BASE}/chat/completions",
        data=payload, headers=_headers(), method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    return data["choices"][0]["message"]["content"]


def score_lead(title: str, summary: str) -> float:
    """Use a free LLM to score a lead's commercial intent 0-100."""
    prompt = (
        f"Rate the commercial/business value of this content item from 0 to 100.\n"
        f"Title: {title}\nSummary: {summary[:300]}\n"
        f"Reply with ONLY a number 0-100. No explanation."
    )
    try:
        result = complete(prompt, model=FREE_MODELS[0], max_tokens=10)
        return min(100.0, max(0.0, float(result.strip().split()[0])))
    except Exception:
        return 0.0


def enhance_content(title: str, summary: str) -> str:
    """Rewrite/enhance content for SEO and dataset packaging."""
    prompt = (
        f"Rewrite this into a concise, SEO-optimised 2-sentence summary "
        f"for a professional data feed.\nTitle: {title}\nOriginal: {summary[:400]}"
    )
    try:
        return complete(prompt, model=FREE_MODELS[0], max_tokens=150)
    except Exception:
        return summary


def list_free_models() -> list:
    req = urllib.request.Request(
        f"{_BASE}/models", headers=_headers(),
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.loads(r.read())
    return [m for m in data.get("data", []) if ":free" in m.get("id", "")]
