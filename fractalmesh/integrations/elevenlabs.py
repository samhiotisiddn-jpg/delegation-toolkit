"""ElevenLabs text-to-speech integration."""
import os
import logging
import urllib.request
import json

log = logging.getLogger("elevenlabs")

_BASE = "https://api.elevenlabs.io/v1"
_KEY  = os.getenv("ELEVENLABS_API_KEY", "")
_DEFAULT_VOICE = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")  # Rachel


def _headers(content_type: str = "application/json") -> dict:
    if not _KEY:
        raise ValueError("ELEVENLABS_API_KEY not set")
    return {
        "xi-api-key": _KEY,
        "Content-Type": content_type,
        "Accept": "audio/mpeg",
    }


def tts(text: str, voice_id: str = _DEFAULT_VOICE,
        model: str = "eleven_multilingual_v2",
        stability: float = 0.5,
        similarity_boost: float = 0.75) -> bytes:
    """Convert text to speech. Returns raw MP3 bytes."""
    payload = json.dumps({
        "text": text,
        "model_id": model,
        "voice_settings": {
            "stability": stability,
            "similarity_boost": similarity_boost,
        },
    }).encode()
    req = urllib.request.Request(
        f"{_BASE}/text-to-speech/{voice_id}",
        data=payload,
        headers={
            "xi-api-key": _KEY,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read()
    except Exception as exc:
        log.error("elevenlabs tts error: %s", exc)
        raise


def list_voices() -> list[dict]:
    req = urllib.request.Request(
        f"{_BASE}/voices",
        headers={"xi-api-key": _KEY, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        return [
            {"voice_id": v["voice_id"], "name": v["name"],
             "category": v.get("category", ""), "labels": v.get("labels", {})}
            for v in data.get("voices", [])
        ]
    except Exception as exc:
        log.warning("elevenlabs list_voices: %s", exc)
        return []


def get_user_info() -> dict:
    req = urllib.request.Request(
        f"{_BASE}/user",
        headers={"xi-api-key": _KEY, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception as exc:
        log.warning("elevenlabs get_user_info: %s", exc)
        return {}
