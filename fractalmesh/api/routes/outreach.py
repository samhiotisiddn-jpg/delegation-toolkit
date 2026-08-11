"""Outreach hunter routes — Reddit leads, pitch staging, Crawlbase scraping."""
import os
import logging
import urllib.request
import urllib.parse
import json
from fastapi import APIRouter, Query, Body, HTTPException
from datetime import datetime

router = APIRouter(prefix="/outreach", tags=["outreach"])
log = logging.getLogger("outreach_routes")

DISPATCH_DIR = os.path.expanduser(os.getenv("DISPATCH_DIR", "~/ai-mesh/dispatch_queue"))
KEYWORDS = ["python", "api", "bot", "crypto", "automation", "data", "scraping", "web3", "blockchain", "ai"]


def _ensure_dispatch():
    os.makedirs(DISPATCH_DIR, exist_ok=True)


def scrape_reddit_leads(subreddit: str = "forhire", limit: int = 50) -> list[dict]:
    try:
        req = urllib.request.Request(
            f"https://www.reddit.com/r/{subreddit}/new.json?limit={limit}",
            headers={"User-Agent": "FractalMesh/5.0:outreach"},
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        posts = data["data"]["children"]
        leads = []
        for p in posts:
            d = p["data"]
            title = d.get("title", "").lower()
            if "hiring" in title and any(k in title for k in KEYWORDS):
                leads.append({
                    "title": d["title"],
                    "link": f"https://reddit.com{d['permalink']}",
                    "body": d.get("selftext", "")[:400],
                    "score": d.get("score", 0),
                })
        return leads
    except Exception as exc:
        log.warning("reddit scrape error: %s", exc)
        return []


def crawlbase_scrape(url: str) -> str:
    token = os.getenv("CRAWLBASE_NORMAL_TOKEN", "")
    if not token:
        return ""
    try:
        req = urllib.request.Request(
            f"https://api.crawlbase.com/?token={token}&url={urllib.parse.quote(url)}",
            headers={"User-Agent": "FractalMesh/5.0"},
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read().decode("utf-8", errors="ignore")[:1000]
    except Exception as exc:
        log.warning("crawlbase error: %s", exc)
        return ""


def stage_pitch(title: str, link: str, body: str = "") -> str:
    _ensure_dispatch()
    ts    = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = os.path.join(DISPATCH_DIR, f"PITCH_{ts}.txt")
    abn   = os.getenv("ABN", "56628117363")
    name  = os.getenv("DIRECTOR", "Samuel James Hiotis")
    pitch = (
        f"TO: Lead via Reddit — {link}\n"
        f"FROM: {name} | IronVision Nexus | ABN {abn}\n"
        f"SUBJECT: Application — {title}\n\n"
        f"I operate a sovereign AI mesh infrastructure in Albury, NSW, specialising in:\n"
        f"- Autonomous trading systems (KuCoin, Crypto.com, Coinbase)\n"
        f"- Multi-agent AI orchestration (OpenAI, Anthropic, xAI, Venice)\n"
        f"- Web3 / blockchain automation (ETH, Polygon, Arbitrum via Alchemy)\n"
        f"- Data extraction pipelines (Crawlbase, WiGLE, Copernicus satellite)\n"
        f"- Full-stack Python/FastAPI automation and REST API integration\n\n"
        f"Lead context:\n{body[:300]}\n\n"
        f"Available for immediate engagement. USDC or AUD settlement accepted.\n"
        f"Contact: sam.hiotis@gmail.com | 0439 008 640\n"
        f"GitHub: github.com/wiglledisonionpi88\n"
    )
    with open(fname, "w") as f:
        f.write(pitch)
    return fname


@router.get("/reddit")
async def get_reddit_leads(
    subreddit: str = Query("forhire"),
    limit: int = Query(50, le=100),
):
    leads = scrape_reddit_leads(subreddit, limit)
    return {"subreddit": subreddit, "leads": leads, "count": len(leads)}


@router.post("/crawlbase")
async def scrape_url(url: str = Body(..., embed=True)):
    content = crawlbase_scrape(url)
    return {"url": url, "content": content, "length": len(content)}


@router.post("/pitch")
async def create_pitch(
    title: str = Body(...),
    link: str = Body(...),
    body: str = Body(""),
):
    fname = stage_pitch(title, link, body)
    return {"staged": fname, "status": "ok"}


@router.post("/run-cycle")
async def run_outreach_cycle(
    subreddit: str = Query("forhire"),
    limit: int = Query(5, le=20),
):
    """Scrape leads and auto-stage top matches."""
    leads = scrape_reddit_leads(subreddit, 50)[:limit]
    staged = []
    for lead in leads:
        fname = stage_pitch(lead["title"], lead["link"], lead.get("body", ""))
        staged.append(fname)
    return {"leads_found": len(leads), "pitches_staged": len(staged), "files": staged}


@router.get("/staged")
async def list_staged():
    """List staged pitches in dispatch queue."""
    _ensure_dispatch()
    files = sorted(os.listdir(DISPATCH_DIR), reverse=True)
    return {"count": len(files), "files": files[:50]}


@router.get("/staged/{filename}")
async def read_pitch(filename: str):
    _ensure_dispatch()
    path = os.path.join(DISPATCH_DIR, filename)
    if not os.path.exists(path) or not filename.endswith(".txt"):
        raise HTTPException(404, "Pitch not found")
    with open(path) as f:
        return {"filename": filename, "content": f.read()}
