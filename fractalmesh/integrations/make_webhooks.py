import os
import json
import urllib.request

# Comma-separated list of Make.com outbound webhook URLs in MAKE_WEBHOOK_URLS env var
_HOOKS: list[str] = []


def _hooks() -> list[str]:
    global _HOOKS
    if not _HOOKS:
        raw = os.environ.get("MAKE_WEBHOOK_URLS", "")
        _HOOKS = [u.strip() for u in raw.split(",") if u.strip()]
    return _HOOKS


def trigger(event_type: str, data: dict) -> None:
    """Fire all configured Make.com webhooks with a standard envelope."""
    payload = json.dumps({"event": event_type, "data": data}).encode()
    for hook in _hooks():
        try:
            req = urllib.request.Request(
                hook, data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception as exc:
            print(f"[make] failed to trigger {event_type}: {exc}")
