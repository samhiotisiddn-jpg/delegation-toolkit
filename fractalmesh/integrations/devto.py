"""
DEV Community (dev.to) publishing integration.

Env vars:
  DEV_API_KEY   your DEV API key
"""

import os
import json
import urllib.request

_BASE = "https://dev.to/api"


def _headers() -> dict:
    return {
        "api-key":      os.environ["DEV_API_KEY"],
        "Content-Type": "application/json",
    }


def publish_article(title: str, body_markdown: str,
                    tags: list[str] | None = None,
                    published: bool = True) -> dict:
    payload = json.dumps({
        "article": {
            "title":         title,
            "body_markdown": body_markdown,
            "published":     published,
            "tags":          tags or ["fractalmesh", "trading", "automation"],
        }
    }).encode()
    req = urllib.request.Request(
        f"{_BASE}/articles",
        data=payload,
        headers=_headers(),
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def get_my_articles(per_page: int = 10) -> list:
    req = urllib.request.Request(
        f"{_BASE}/articles/me?per_page={per_page}",
        headers=_headers(),
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def publish_trade_summary(trades: list[dict]) -> dict | None:
    """Auto-publish a trade summary article from recent trade records."""
    if not trades:
        return None

    executed = [t for t in trades if t["status"] == "executed"]
    total_pnl = sum(float(t.get("pnl_usdt") or 0) for t in executed)

    lines = [
        "## FractalMesh Trade Summary\n",
        f"**Period:** last {len(trades)} scanned | **Executed:** {len(executed)}\n",
        f"**Total P&L:** ${total_pnl:.4f} USDT\n\n",
        "| Pair | Spread | Status |",
        "|---|---|---|",
    ]
    for t in trades[:20]:
        lines.append(f"| {t['pair']} | {t['spread_pct']}% | {t['status']} |")

    return publish_article(
        title="FractalMesh Arbitrage Report",
        body_markdown="\n".join(lines),
        tags=["trading", "crypto", "automation", "python"],
        published=False,  # draft — set True to go live
    )
