"""
Venice AI — OpenAI-compatible client (uncensored/permissive models).
vck_ key prefix.
"""

import os, json, urllib.request

_BASE = "https://api.venice.ai/api/v1"

VENICE_MODELS = [
    "llama-3.3-70b",
    "mistral-31-24b",
    "llama-3.2-3b",
    "deepseek-r1-671b",
]


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {os.environ['AI_GATEWAY_API_KEY']}",
        "Content-Type":  "application/json",
    }


def complete(
    prompt: str,
    system: str = "You are a helpful assistant.",
    model:  str = VENICE_MODELS[0],
    max_tokens: int = 1000,
) -> str:
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": prompt},
        ],
        "max_tokens": max_tokens,
        "venice_parameters": {"include_venice_system_prompt": False},
    }).encode()
    req = urllib.request.Request(
        f"{_BASE}/chat/completions",
        data=payload, headers=_headers(), method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"]


def list_models() -> list:
    req = urllib.request.Request(f"{_BASE}/models", headers=_headers())
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read()).get("data", [])
