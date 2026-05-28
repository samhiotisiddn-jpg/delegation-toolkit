"""Zapier MCP webhook integration — trigger Zaps from FractalMesh events."""
import os
import json
import logging
import urllib.request

log = logging.getLogger("zapier_mcp")

_CONNECT_API = os.getenv("ZAPIER_CONNECT_API", "https://mcp.zapier.com/api/v1/connect")
_TOKEN_1 = os.getenv("ZAPIER_TOKEN_1", "")
_TOKEN_2 = os.getenv("ZAPIER_TOKEN_2", "")
_EMBED_ID = os.getenv("ZAPIER_MCP_EMBED_ID", "")


def _active_token() -> str:
    return _TOKEN_1 or _TOKEN_2


def trigger(action: str, data: dict, token: str | None = None) -> dict:
    """POST an action payload to Zapier MCP connect endpoint."""
    tok = token or _active_token()
    if not tok:
        log.debug("ZAPIER_TOKEN not set — skipping")
        return {}
    payload = json.dumps({
        "embed_id": _EMBED_ID,
        "action": action,
        "data": data,
        "timestamp": __import__("time").strftime("%Y-%m-%dT%H:%M:%SZ", __import__("time").gmtime()),
    }).encode()
    req = urllib.request.Request(
        _CONNECT_API,
        data=payload,
        headers={
            "Authorization": f"Bearer {tok}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read()) if r.read else {}
    except Exception as exc:
        log.warning("zapier trigger %s failed: %s", action, exc)
        return {"error": str(exc)}


def notify_revenue(amount_aud: float, source: str, description: str) -> dict:
    return trigger("revenue.received", {
        "amount_aud": amount_aud,
        "source": source,
        "description": description,
    })


def notify_new_leads(count: int, tier: str = "mixed") -> dict:
    return trigger("leads.ingested", {"count": count, "tier": tier})


def notify_trade(exchange: str, symbol: str, side: str, amount: float, price: float) -> dict:
    return trigger("trade.executed", {
        "exchange": exchange, "symbol": symbol,
        "side": side, "amount": amount, "price": price,
    })


def get_share_url(token_num: int = 1) -> str:
    return os.getenv(f"ZAPIER_SHARE_URL_{token_num}", "https://mcp.zapier.com")
