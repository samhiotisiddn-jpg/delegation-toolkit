#!/usr/bin/env python3
"""
fractalmesh/mesh/bridges/xai-grok_bridge.py

FractalMesh stdin → xAI Grok API → stdout bridge.
Called by the runtime bus:
    echo '{"session_id":"...","from":"...","message":"..."}' | python3 xai-grok_bridge.py

Environment variables (set in your .env or shell before starting):
    XAI_API_KEY        — xAI Grok API key (required)
    XAI_MODEL          — model name (default: grok-beta)
    XAI_MAX_TOKENS     — max response tokens (default: 4096)
    XAI_TEMPERATURE    — sampling temperature (default: 0.7)

Never hardcode credentials here. Load them from the environment only.
"""

import sys
import json
import os
import logging
from datetime import datetime, timezone

# ── logging ───────────────────────────────────────────────────────────────────
_LOG_PATH = os.path.join(
    os.path.expanduser("~"), "ai-mesh", "logs", "xai-grok.log"
)
os.makedirs(os.path.dirname(_LOG_PATH), exist_ok=True)
logging.basicConfig(
    filename=_LOG_PATH,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] xai-grok %(message)s",
)
log = logging.getLogger("xai-grok")

NODE_ID = "xai-grok"
CAPABILITIES = [
    "stripe", "printful", "alchemy", "web3", "exchanges",
    "kucoin", "cryptocom", "coinbase", "wallets", "metamask",
    "eos", "hbar", "cronos", "wigle", "xyo", "rf_oracle",
    "openai", "langsmith", "ai", "telegram", "gmail",
    "messaging", "coingecko", "opensea", "github", "tipbot",
    "wax", "aleo", "gcp", "oauth", "xai", "twitter",
    "crawlbase", "uniswap", "firebase", "legislation",
    "coolify", "iddn", "cvgt", "lighthouse", "tonnel",
    "compliance", "smart_contracts", "royalties", "rag",
    "defi", "dex", "ccxt", "nft", "etf", "stocks",
    "commodities", "automation", "monetization", "outreach",
    "affiliate", "correspondence", "follow_up", "digital_twin",
]


def _call_xai(prompt: str) -> str:
    """Send prompt to xAI Grok API; return text reply."""
    api_key = os.getenv("XAI_API_KEY")
    if not api_key:
        log.error("XAI_API_KEY not set")
        return "[ERROR] XAI_API_KEY not set in environment"

    model = os.getenv("XAI_MODEL", "grok-beta")
    max_tokens = int(os.getenv("XAI_MAX_TOKENS", "4096"))
    temperature = float(os.getenv("XAI_TEMPERATURE", "0.7"))

    try:
        import requests  # optional dep; graceful error if absent

        resp = requests.post(
            "https://api.x.ai/v1/chat/completions",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
            timeout=90,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    except ImportError:
        log.error("requests not installed — run: pip install requests")
        return "[ERROR] requests library not installed"
    except Exception as exc:
        log.error("xAI call failed: %s", exc)
        return f"[xai-grok error] {str(exc)[:300]}"


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def main() -> None:
    raw = sys.stdin.read().strip()
    if not raw:
        raw = '{"session_id":"ping","from":"test","message":"ping"}'

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": f"Invalid JSON input: {exc}"}))
        sys.exit(1)

    session_id = data.get("session_id", "unknown")
    sender = data.get("from", "broadcast")
    message = data.get("message", "Hello from FractalMesh")

    log.info("session=%s from=%s msg_len=%d", session_id, sender, len(message))

    reply = _call_xai(message)

    response = {
        "session_id": session_id,
        "from": NODE_ID,
        "to": sender,
        "message": reply,
        "meta": {
            "timestamp": _now_iso(),
            "node": NODE_ID,
            "model": os.getenv("XAI_MODEL", "grok-beta"),
            "capabilities": CAPABILITIES,
        },
    }

    print(json.dumps(response))
    log.info("session=%s reply_len=%d", session_id, len(reply))


if __name__ == "__main__":
    main()
