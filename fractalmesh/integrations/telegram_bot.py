"""Telegram bot alerts and messaging via Bot API."""
import os
import urllib.request
import urllib.parse
import json
import logging

log = logging.getLogger("telegram_bot")

_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
_BASE = f"https://api.telegram.org/bot{_TOKEN}"


def _call(method: str, payload: dict) -> dict:
    if not _TOKEN:
        log.debug("TELEGRAM_BOT_TOKEN not set — skipping")
        return {}
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{_BASE}/{method}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception as exc:
        log.warning("telegram %s failed: %s", method, exc)
        return {}


def send(chat_id: str, text: str, parse_mode: str = "Markdown") -> dict:
    return _call("sendMessage", {"chat_id": chat_id, "text": text, "parse_mode": parse_mode})


def broadcast(text: str, parse_mode: str = "Markdown") -> list[dict]:
    """Send to all chat IDs in TELEGRAM_CHAT_IDS env var (comma-separated)."""
    ids = [c.strip() for c in os.getenv("TELEGRAM_CHAT_IDS", "").split(",") if c.strip()]
    return [send(cid, text, parse_mode) for cid in ids]


def alert(title: str, body: str, level: str = "INFO") -> None:
    icons = {"INFO": "ℹ️", "WARN": "⚠️", "ERROR": "🚨", "OK": "✅"}
    icon = icons.get(level, "📢")
    msg = f"{icon} *{title}*\n{body}"
    broadcast(msg)


def get_updates(offset: int = 0) -> list[dict]:
    result = _call("getUpdates", {"offset": offset, "timeout": 5})
    return result.get("result", [])
