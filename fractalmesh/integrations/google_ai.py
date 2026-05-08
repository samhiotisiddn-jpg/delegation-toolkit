"""
Google Gemini provider with automatic key rotation on failure.
Reads GOOGLE_API_KEYS (comma-separated) and rotates to next key on any error.
Pattern ported from google_ai_studio.ts.
"""
import os
import urllib.request
import json
import logging
import time

log = logging.getLogger("google_ai")

_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
COOLDOWN = int(os.getenv("COOLDOWN_MS", "10000")) / 1000

_raw_keys = [k.strip() for k in os.getenv("GOOGLE_API_KEYS", "").split(",") if k.strip()]
_keys = [{"value": k, "fails": 0, "successes": 0, "health": True, "last_error": None} for k in _raw_keys]
_active_idx = 0


def _rotate() -> dict:
    global _active_idx
    _active_idx = (_active_idx + 1) % max(len(_keys), 1)
    log.warning("google_ai: rotated to key index %d", _active_idx)
    return _keys[_active_idx] if _keys else {}


def complete(
    prompt: str,
    system: str = "You are a helpful assistant.",
    model: str = "",
    max_tokens: int = 800,
) -> str:
    if not _keys:
        raise ValueError("No GOOGLE_API_KEYS configured")

    model = model or os.getenv("GOOGLE_AI_MODEL", "gemini-2.0-flash")
    attempts = 0
    last_error = None

    while attempts < len(_keys):
        key_obj = _keys[_active_idx]
        key_val = key_obj["value"]
        url = f"{_BASE}/{model}:generateContent?key={key_val}"
        payload = json.dumps({
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.3},
        }).encode()
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read())
            key_obj["successes"] += 1
            key_obj["health"] = True
            key_obj["last_error"] = None
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception as exc:
            last_error = str(exc)
            key_obj["fails"] += 1
            key_obj["health"] = False
            key_obj["last_error"] = last_error
            _rotate()
            attempts += 1
            if attempts >= len(_keys):
                log.error("google_ai: all %d keys failed, cooldown %.1fs", len(_keys), COOLDOWN)
                time.sleep(COOLDOWN)

    raise RuntimeError(f"All Google AI keys failed. Last: {last_error}")


def get_key_stats() -> list[dict]:
    return [
        {
            "index": i,
            "active": i == _active_idx,
            "health": k["health"],
            "fails": k["fails"],
            "successes": k["successes"],
            "last_error": k["last_error"],
        }
        for i, k in enumerate(_keys)
    ]
