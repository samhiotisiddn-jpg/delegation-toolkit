"""OpenAI GPT-4 completions client."""
import os
import urllib.request
import urllib.error
import json
import logging

log = logging.getLogger("openai_client")

_BASE = "https://api.openai.com/v1"
_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def _api_key() -> str:
    key = os.getenv("OPENAI_API_KEY", "")
    if not key:
        raise ValueError("OPENAI_API_KEY not set")
    return key


def complete(
    prompt: str,
    system: str = "You are a helpful assistant.",
    model: str = _MODEL,
    max_tokens: int = 800,
) -> str:
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.3,
    }).encode()

    req = urllib.request.Request(
        f"{_BASE}/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {_api_key()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    return data["choices"][0]["message"]["content"].strip()


def score_lead(title: str, summary: str) -> float:
    prompt = (
        f"Rate the commercial/business value 0-100.\n"
        f"Title: {title}\nSummary: {summary[:300]}\n"
        f"Reply with ONLY a number."
    )
    try:
        r = complete(prompt, max_tokens=10)
        return min(100.0, max(0.0, float(r.strip().split()[0])))
    except Exception:
        return 0.0
