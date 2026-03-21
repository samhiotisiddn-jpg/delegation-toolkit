#!/usr/bin/env python3
"""
fractalmesh/mesh/bridges/xai-grok_bridge.py  —  v2

FractalMesh stdin → xAI Grok API → stdout bridge.
Called by the runtime bus:
    echo '{"session_id":"...","from":"...","message":"..."}' | python3 xai-grok_bridge.py

v2 upgrades
-----------
- Configurable system prompt via XAI_SYSTEM_PROMPT env var.
- Exponential-backoff retry on 429 rate-limit and 5xx server errors (up to MAX_RETRIES).
- Conversation context: pass "history" list in the input JSON to maintain multi-turn state.
- XAI_STREAM env var: set to "1" to request streaming (returns concatenated final text).
- Richer meta block: includes retry_count, model, token estimates.

Environment variables (set in your .env or shell before starting):
    XAI_API_KEY        — xAI Grok API key (required)
    XAI_MODEL          — model name (default: grok-beta)
    XAI_MAX_TOKENS     — max response tokens (default: 4096)
    XAI_TEMPERATURE    — sampling temperature (default: 0.7)
    XAI_SYSTEM_PROMPT  — optional system prompt injected at conversation start
    XAI_MAX_RETRIES    — max retries on transient errors (default: 3)
    XAI_STREAM         — set to "1" to enable streaming (default: 0)

Input JSON schema:
    {
      "session_id": "string",
      "from": "string",
      "message": "string",
      "history": [                        // optional multi-turn history
        {"role": "user",      "content": "..."},
        {"role": "assistant", "content": "..."}
      ]
    }

Never hardcode credentials here. Load them from the environment only.
"""

import sys
import json
import os
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

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
    "multi_turn", "system_prompt", "streaming",
]

_RETRY_STATUS_CODES = {429, 500, 502, 503, 504}


def _call_xai(
    message: str,
    history: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """
    Send message (with optional conversation history) to xAI Grok API.
    Returns {"text": str, "retries": int, "model": str}.
    Retries up to XAI_MAX_RETRIES on rate-limit / server errors.
    """
    api_key = os.getenv("XAI_API_KEY")
    if not api_key:
        log.error("XAI_API_KEY not set")
        return {"text": "[ERROR] XAI_API_KEY not set in environment", "retries": 0, "model": ""}

    model       = os.getenv("XAI_MODEL", "grok-beta")
    max_tokens  = int(os.getenv("XAI_MAX_TOKENS", "4096"))
    temperature = float(os.getenv("XAI_TEMPERATURE", "0.7"))
    max_retries = int(os.getenv("XAI_MAX_RETRIES", "3"))
    stream      = os.getenv("XAI_STREAM", "0") == "1"
    system_prompt = os.getenv("XAI_SYSTEM_PROMPT", "")

    # Build messages array
    messages: List[Dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    if history:
        for turn in history:
            if turn.get("role") in ("user", "assistant", "system") and turn.get("content"):
                messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": message})

    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if stream:
        payload["stream"] = True

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    try:
        import requests as req_lib
    except ImportError:
        log.error("requests not installed — run: pip install requests")
        return {"text": "[ERROR] requests library not installed", "retries": 0, "model": model}

    last_err: str = ""
    for attempt in range(1, max_retries + 1):
        try:
            if stream:
                resp = req_lib.post(
                    "https://api.x.ai/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=120,
                    stream=True,
                )
                if resp.status_code in _RETRY_STATUS_CODES:
                    raise _TransientError(resp.status_code)
                resp.raise_for_status()
                # Collect streamed chunks
                collected = []
                for line in resp.iter_lines():
                    if not line:
                        continue
                    line_str = line.decode("utf-8") if isinstance(line, bytes) else line
                    if line_str.startswith("data: "):
                        data = line_str[6:]
                        if data.strip() == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            delta = chunk["choices"][0].get("delta", {})
                            if delta.get("content"):
                                collected.append(delta["content"])
                        except (json.JSONDecodeError, KeyError, IndexError):
                            pass
                text = "".join(collected)
            else:
                resp = req_lib.post(
                    "https://api.x.ai/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=90,
                )
                if resp.status_code in _RETRY_STATUS_CODES:
                    raise _TransientError(resp.status_code)
                resp.raise_for_status()
                text = resp.json()["choices"][0]["message"]["content"]

            return {"text": text, "retries": attempt - 1, "model": model}

        except _TransientError as exc:
            wait = 2 ** attempt
            last_err = f"HTTP {exc.status_code}"
            log.warning("Transient error %s attempt %d — retrying in %ds", exc.status_code, attempt, wait)
            time.sleep(wait)
        except Exception as exc:
            last_err = str(exc)[:200]
            if attempt < max_retries:
                wait = 2 ** attempt
                log.warning("xAI call error attempt %d: %s — retry in %ds", attempt, exc, wait)
                time.sleep(wait)
            else:
                log.error("xAI call failed after %d attempts: %s", max_retries, exc)

    return {
        "text": f"[xai-grok error after {max_retries} retries] {last_err}",
        "retries": max_retries,
        "model": model,
    }


class _TransientError(Exception):
    def __init__(self, status_code: int):
        self.status_code = status_code
        super().__init__(f"HTTP {status_code}")


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
    sender     = data.get("from", "broadcast")
    message    = data.get("message", "Hello from FractalMesh")
    history    = data.get("history")  # optional list of prior turns

    log.info(
        "session=%s from=%s msg_len=%d history_turns=%d",
        session_id, sender, len(message), len(history) if history else 0,
    )

    result = _call_xai(message, history=history)
    reply  = result["text"]

    response = {
        "session_id": session_id,
        "from": NODE_ID,
        "to": sender,
        "message": reply,
        "meta": {
            "timestamp": _now_iso(),
            "node": NODE_ID,
            "model": result["model"] or os.getenv("XAI_MODEL", "grok-beta"),
            "retries": result["retries"],
            "history_turns": len(history) if history else 0,
            "capabilities": CAPABILITIES,
        },
    }

    print(json.dumps(response))
    log.info("session=%s reply_len=%d retries=%d", session_id, len(reply), result["retries"])


if __name__ == "__main__":
    main()
