"""
GitHub AI Models inference — uses your GitHub PAT to call models
hosted at https://models.github.ai/inference (Azure AI Inference API).

Default model: microsoft/Phi-4-multimodal-instruct
Also supports: openai/gpt-4o, meta/llama-3-70b-instruct, etc.

Env vars:
  GITHUB_TOKEN   your GitHub personal access token
"""

import os
import json
import urllib.request

_ENDPOINT = "https://models.github.ai/inference"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
        "Content-Type":  "application/json",
    }


def complete(
    prompt: str,
    system: str = "You are a helpful assistant.",
    model:  str = "microsoft/Phi-4-multimodal-instruct",
    max_tokens: int = 1000,
    temperature: float = 1.0,
) -> str:
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system",  "content": system},
            {"role": "user",    "content": prompt},
        ],
        "temperature": temperature,
        "max_tokens":  max_tokens,
        "top_p":       1.0,
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


def list_models() -> list:
    req = urllib.request.Request(f"{_ENDPOINT}/models", headers=_headers())
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read()).get("data", [])
