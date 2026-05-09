"""
OpenRouter integration v2 — routes to 160+ models including Owl Alpha,
Gemma 4, Gemini 3.x, GPT-5.1, Claude Sonnet, free-tier models.
Supports completions, embeddings (text-embedding-3-small), and model listing.

Key refs:
  Touvron et al. (2023) LLaMA 2 — https://arxiv.org/abs/2307.09288
  Jiang et al. (2023) Mistral 7B — https://arxiv.org/abs/2310.06825
  OpenRouter model routing: https://openrouter.ai/docs
"""

import os
import json
import urllib.request
import logging

log = logging.getLogger("openrouter")

_BASE = "https://openrouter.ai/api/v1"

# Free tier models — zero cost
FREE_MODELS = [
    "qwen/qwen3-coder:free",
    "minimax/minimax-m2.5:free",
    "mistralai/mistral-7b-instruct:free",
    "meta-llama/llama-3-8b-instruct:free",
    "google/gemma-2-9b-it:free",
    "microsoft/phi-3-mini-128k-instruct:free",
    "qwen/qwen-2-7b-instruct:free",
]

# Premium / high-capability models (billed per token)
PREMIUM_MODELS = {
    "owl_alpha":        "openrouter/owl-alpha",
    "gemma4_26b":       "google/gemma-4-26b-it:nitro",
    "gemma4_31b":       "google/gemma-4-31b-it",
    "gemini_31_pro":    "google/gemini-3.1-pro-preview",
    "gemini_25_pro":    "google/gemini-2.5-pro",
    "gemini_3_flash":   "google/gemini-3-flash-preview",
    "gpt4o_mini":       "openai/gpt-4o-mini",
    "gpt51":            "openai/gpt-5.1",
    "claude_sonnet45":  "anthropic/claude-sonnet-4-5",
    "grok41_fast":      "x-ai/grok-4.1-fast",
}

# Embedding model
EMBED_MODEL = "openai/text-embedding-3-small"


def _key(mgmt: bool = False) -> str:
    env = "OPENROUTER_MGMT_KEY" if mgmt else "OPENROUTER_API_KEY"
    key = os.environ.get(env, "")
    if not key:
        raise ValueError(f"{env} not set")
    return key


def _headers(mgmt: bool = False) -> dict:
    return {
        "Authorization": f"Bearer {_key(mgmt)}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://fractalmesh.io",
        "X-Title": "FractalMesh v6",
    }


def complete(
    prompt: str,
    system: str = "You are a helpful assistant.",
    model: str = FREE_MODELS[0],
    max_tokens: int = 800,
    temperature: float = 0.3,
) -> str:
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }).encode()
    req = urllib.request.Request(
        f"{_BASE}/chat/completions",
        data=payload, headers=_headers(), method="POST",
    )
    with urllib.request.urlopen(req, timeout=45) as r:
        data = json.loads(r.read())
    return data["choices"][0]["message"]["content"].strip()


def complete_owl(prompt: str, system: str = "You are a helpful assistant.", max_tokens: int = 1200) -> str:
    """Owl Alpha — OpenRouter's autonomous reasoning model."""
    return complete(prompt, system, PREMIUM_MODELS["owl_alpha"], max_tokens)


def embed(texts: list[str]) -> list[list[float]]:
    """Generate embeddings via text-embedding-3-small (1536 dims)."""
    payload = json.dumps({"model": EMBED_MODEL, "input": texts}).encode()
    req = urllib.request.Request(
        f"{_BASE}/embeddings",
        data=payload, headers=_headers(), method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    return [item["embedding"] for item in sorted(data["data"], key=lambda x: x["index"])]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Pure-Python cosine similarity for RAG ranking."""
    dot = sum(x * y for x, y in zip(a, b))
    na  = sum(x * x for x in a) ** 0.5
    nb  = sum(y * y for y in b) ** 0.5
    return dot / (na * nb + 1e-9)


def score_lead(title: str, summary: str) -> float:
    """Score a lead's commercial intent 0-100 using free model."""
    prompt = (
        f"Rate commercial/business value 0-100.\n"
        f"Title: {title}\nSummary: {summary[:300]}\n"
        f"Reply with ONLY a number 0-100."
    )
    try:
        r = complete(prompt, model=FREE_MODELS[0], max_tokens=10)
        return min(100.0, max(0.0, float(r.strip().split()[0])))
    except Exception:
        return 0.0


def enhance_content(title: str, summary: str) -> str:
    """Rewrite content for SEO and dataset packaging."""
    prompt = (
        f"Rewrite into a concise, SEO-optimised 2-sentence summary "
        f"for a professional data feed.\nTitle: {title}\nOriginal: {summary[:400]}"
    )
    try:
        return complete(prompt, model=FREE_MODELS[0], max_tokens=150)
    except Exception:
        return summary


def list_free_models() -> list[dict]:
    try:
        req = urllib.request.Request(f"{_BASE}/models", headers=_headers())
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        return [m for m in data.get("data", []) if ":free" in m.get("id", "")]
    except Exception as exc:
        log.warning("list_free_models: %s", exc)
        return []


def list_all_models() -> list[dict]:
    try:
        req = urllib.request.Request(f"{_BASE}/models", headers=_headers())
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        return data.get("data", [])
    except Exception as exc:
        log.warning("list_all_models: %s", exc)
        return []


def get_generation_stats() -> dict:
    """Get current API key usage stats."""
    try:
        req = urllib.request.Request(f"{_BASE}/auth/key", headers=_headers())
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception as exc:
        log.warning("get_generation_stats: %s", exc)
        return {}
