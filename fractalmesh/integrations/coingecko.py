"""CoinGecko market data — prices, trending coins, market overview."""
import os
import urllib.request
import urllib.parse
import json
import logging

log = logging.getLogger("coingecko")

_BASE = "https://api.coingecko.com/api/v3"
_KEY = os.getenv("COINGECKO_API_KEY", "")


def _headers() -> dict:
    h = {"Accept": "application/json", "User-Agent": "FractalMesh/4.0"}
    if _KEY:
        h["x-cg-demo-api-key"] = _KEY
    return h


def _get(path: str, params: dict | None = None) -> dict | list:
    url = f"{_BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=_headers())
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def get_prices(coin_ids: list[str], vs: str = "aud") -> dict:
    """{'bitcoin': {'aud': 95000}, ...}"""
    try:
        return _get("/simple/price", {
            "ids": ",".join(coin_ids),
            "vs_currencies": vs,
            "include_24hr_change": "true",
            "include_market_cap": "true",
        })
    except Exception as exc:
        log.warning("coingecko get_prices: %s", exc)
        return {}


def get_trending() -> list[dict]:
    """Top-7 trending coins."""
    try:
        data = _get("/search/trending")
        return [
            {
                "id":    c["item"]["id"],
                "name":  c["item"]["name"],
                "symbol": c["item"]["symbol"],
                "rank":  c["item"].get("market_cap_rank"),
            }
            for c in data.get("coins", [])
        ]
    except Exception as exc:
        log.warning("coingecko get_trending: %s", exc)
        return []


def get_global() -> dict:
    try:
        data = _get("/global")
        return data.get("data", {})
    except Exception as exc:
        log.warning("coingecko get_global: %s", exc)
        return {}


def get_coin_detail(coin_id: str) -> dict:
    try:
        return _get(f"/coins/{coin_id}", {
            "localization": "false",
            "tickers": "false",
            "community_data": "false",
        })
    except Exception as exc:
        log.warning("coingecko get_coin_detail %s: %s", coin_id, exc)
        return {}


def format_market_summary() -> str:
    """Return a human-readable market summary string for RSS/digest use."""
    try:
        g = get_global()
        cap = g.get("total_market_cap", {}).get("aud", 0)
        change = g.get("market_cap_change_percentage_24h_usd", 0)
        dominance = g.get("market_cap_percentage", {})
        btc_d = dominance.get("btc", 0)
        eth_d = dominance.get("eth", 0)

        prices = get_prices(["bitcoin", "ethereum", "solana"])
        btc = prices.get("bitcoin", {}).get("aud", 0)
        eth = prices.get("ethereum", {}).get("aud", 0)
        sol = prices.get("solana", {}).get("aud", 0)

        return (
            f"Global market cap: A${cap:,.0f} ({change:+.1f}% 24h) | "
            f"BTC dominance {btc_d:.1f}% | ETH {eth_d:.1f}% | "
            f"BTC A${btc:,.0f} | ETH A${eth:,.0f} | SOL A${sol:,.0f}"
        )
    except Exception as exc:
        log.warning("coingecko format_market_summary: %s", exc)
        return "Market data unavailable"
