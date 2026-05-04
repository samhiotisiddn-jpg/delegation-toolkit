"""
xAI / Grok inference client.

Env vars:
  XAI_API_KEY
"""

import os
import json
import urllib.request

_ENDPOINT = "https://api.x.ai/v1"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {os.environ['XAI_API_KEY']}",
        "Content-Type":  "application/json",
    }


def complete(
    prompt: str,
    system: str = "You are a helpful assistant.",
    model:  str = "grok-3",
    max_tokens: int = 1000,
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
        f"{_ENDPOINT}/chat/completions",
        data=payload,
        headers=_headers(),
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    return data["choices"][0]["message"]["content"]
