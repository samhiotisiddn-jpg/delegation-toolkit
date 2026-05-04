from fastapi import APIRouter, Body
from integrations.devto import get_my_articles, publish_article
from integrations.supabase_client import query

router = APIRouter(prefix="/devto", tags=["devto"])


@router.get("/articles")
def my_articles():
    return get_my_articles()


@router.post("/publish")
def publish(
    title:         str        = Body(...),
    body_markdown: str        = Body(...),
    tags:          list[str]  = Body(["fractalmesh"]),
    published:     bool       = Body(False),
):
    return publish_article(title, body_markdown, tags, published)


@router.post("/publish-trade-summary")
def publish_trade_summary():
    from integrations.devto import publish_trade_summary as _pub
    trades = query("trades", limit=50)
    result = _pub(trades)
    return result or {"detail": "no trades to summarise"}
