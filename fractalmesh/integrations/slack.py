import os
import json
import urllib.request
from typing import Literal

Level = Literal["info", "warn", "error", "critical"]

_COLOURS = {
    "info":     "#36a64f",
    "warn":     "#ffcc00",
    "error":    "#e01e5a",
    "critical": "#8B0000",
}

_HOOKS: list[str] = []


def _hooks() -> list[str]:
    global _HOOKS
    if not _HOOKS:
        raw = os.environ.get("SLACK_WEBHOOK_URLS", "")
        _HOOKS = [u.strip() for u in raw.split(",") if u.strip()]
    return _HOOKS


def send(title: str, body: str = "", level: Level = "info", fields: dict | None = None) -> None:
    """Post a message to all configured Slack webhooks."""
    attachment = {
        "color": _COLOURS.get(level, "#36a64f"),
        "title": f"[{level.upper()}] {title}",
        "text":  body,
        "fields": [{"title": k, "value": str(v), "short": True} for k, v in (fields or {}).items()],
        "footer": "FractalMesh",
    }
    payload = json.dumps({"attachments": [attachment]}).encode()

    for hook in _hooks():
        try:
            req = urllib.request.Request(
                hook, data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception as exc:
            print(f"[slack] failed to send to hook: {exc}")
