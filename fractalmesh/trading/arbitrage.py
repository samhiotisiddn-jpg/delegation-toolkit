"""
KuCoin intra-exchange triangular arbitrage engine.

Looks for price spreads across spot pairs and executes when the
spread exceeds MIN_SPREAD_PCT (default 0.5%).

Environment variables required:
  KUCOIN_API_KEY, KUCOIN_API_SECRET, KUCOIN_PASSPHRASE
  MIN_SPREAD_PCT   (default 0.5)
  MAX_ORDER_USDT   (default 50)
  DRY_RUN          (default true — set to "false" to live trade)
"""

import os
import time
import logging
from datetime import datetime, timezone

from kucoin.client import Trade, Market
from integrations import slack, make_webhooks
from integrations.supabase_client import insert

log = logging.getLogger("arbitrage")

MIN_SPREAD  = float(os.environ.get("MIN_SPREAD_PCT", "0.5"))
MAX_USDT    = float(os.environ.get("MAX_ORDER_USDT", "50"))
DRY_RUN     = os.environ.get("DRY_RUN", "true").lower() != "false"
POLL_SECS   = int(os.environ.get("POLL_SECS", "60"))

# Pairs to monitor — extend as needed
WATCH_PAIRS = [
    ("BTC-USDT", "ETH-USDT", "ETH-BTC"),
    ("BTC-USDT", "XRP-USDT", "XRP-BTC"),
]


def _clients():
    key        = os.environ["KUCOIN_API_KEY"]
    secret     = os.environ["KUCOIN_API_SECRET"]
    passphrase = os.environ["KUCOIN_PASSPHRASE"]
    market = Market(key=key, secret=secret, passphrase=passphrase)
    trade  = Trade(key=key, secret=secret, passphrase=passphrase)
    return market, trade


def _get_price(market: Market, pair: str) -> float:
    ticker = market.get_ticker(pair)
    return float(ticker["price"])


def _check_triangle(market: Market, a_usdt: str, b_usdt: str, b_a: str) -> dict | None:
    """
    Triangle: buy A with USDT → sell A for B → sell B for USDT
    Returns opportunity dict if spread >= MIN_SPREAD, else None.
    """
    try:
        price_a  = _get_price(market, a_usdt)   # e.g. BTC-USDT
        price_b  = _get_price(market, b_usdt)   # e.g. ETH-USDT
        price_ba = _get_price(market, b_a)       # e.g. ETH-BTC
    except Exception as exc:
        log.warning("price fetch error: %s", exc)
        return None

    # Theoretical: 1 USDT → A → B → USDT
    implied = (1 / price_a) * (1 / price_ba) * price_b
    spread  = (implied - 1) * 100  # percent

    if spread >= MIN_SPREAD:
        return {
            "pair":       f"{a_usdt}/{b_usdt}/{b_a}",
            "spread_pct": round(spread, 4),
            "price_a":    price_a,
            "price_b":    price_b,
            "price_ba":   price_ba,
        }
    return None


def _execute(trade: Trade, opp: dict) -> dict:
    if DRY_RUN:
        log.info("[DRY RUN] would trade %s spread=%.4f%%", opp["pair"], opp["spread_pct"])
        return {**opp, "status": "skipped", "pnl_usdt": 0}

    # Simplified: market buy on first leg only as a starting point
    # Extend with full triangle logic for live trading
    try:
        qty = round(MAX_USDT / opp["price_a"], 6)
        order = trade.create_market_order(
            symbol=opp["pair"].split("/")[0],
            side="buy",
            size=str(qty),
        )
        return {**opp, "status": "executed", "raw": order, "pnl_usdt": None}
    except Exception as exc:
        return {**opp, "status": "failed", "error": str(exc)}


def _record(opp: dict, result: dict):
    row = {
        "pair":        opp["pair"],
        "buy_price":   opp["price_a"],
        "sell_price":  opp["price_b"],
        "spread_pct":  opp["spread_pct"],
        "quantity":    round(MAX_USDT / opp["price_a"], 6),
        "status":      result["status"],
        "error":       result.get("error"),
        "raw":         result.get("raw"),
    }
    insert("trades", row)

    level = "info" if result["status"] in ("executed", "skipped") else "error"
    slack.send(
        title=f"Trade {result['status'].upper()}: {opp['pair']}",
        body=f"Spread: {opp['spread_pct']}% | DRY_RUN={DRY_RUN}",
        level=level,
        fields={"spread": f"{opp['spread_pct']}%", "status": result["status"]},
    )
    make_webhooks.trigger("trade.result", {**opp, **result})


def run_once():
    market, trade = _clients()
    for triplet in WATCH_PAIRS:
        opp = _check_triangle(market, *triplet)
        if opp:
            log.info("opportunity: %s spread=%.4f%%", opp["pair"], opp["spread_pct"])
            result = _execute(trade, opp)
            _record(opp, result)


def run_forever():
    log.info("Arbitrage engine starting | dry_run=%s | poll=%ss", DRY_RUN, POLL_SECS)
    slack.send("Arbitrage engine started", level="info",
               fields={"dry_run": str(DRY_RUN), "poll_secs": str(POLL_SECS)})
    while True:
        try:
            run_once()
        except Exception as exc:
            log.error("engine error: %s", exc)
            slack.send("Arbitrage engine error", body=str(exc), level="error")
        time.sleep(POLL_SECS)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    run_forever()
