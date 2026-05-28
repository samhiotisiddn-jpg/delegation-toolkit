"""Market data routes — CoinGecko prices, trending, global stats."""
from fastapi import APIRouter, Query

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/prices")
async def get_prices(
    coins: str = Query("bitcoin,ethereum,solana", description="Comma-separated coin IDs"),
    vs: str = Query("aud", description="vs currency"),
):
    from integrations import coingecko
    ids = [c.strip() for c in coins.split(",") if c.strip()]
    return coingecko.get_prices(ids, vs)


@router.get("/trending")
async def get_trending():
    from integrations import coingecko
    return {"trending": coingecko.get_trending()}


@router.get("/global")
async def get_global():
    from integrations import coingecko
    return coingecko.get_global()


@router.get("/summary")
async def get_summary():
    from integrations import coingecko
    return {"summary": coingecko.format_market_summary()}


@router.get("/coin/{coin_id}")
async def get_coin(coin_id: str):
    from integrations import coingecko
    return coingecko.get_coin_detail(coin_id)
