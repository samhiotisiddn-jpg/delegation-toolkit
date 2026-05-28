"""Trading engine routes — multi-exchange autonomous trading."""
from fastapi import APIRouter, Query, Body, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/trading", tags=["trading"])


class OrderRequest(BaseModel):
    exchange: str = "kucoin"
    symbol: str
    side: str  # buy | sell
    amount: float
    strategy: str = "manual"


@router.get("/status")
async def status():
    from integrations.trading_engine import get_status
    return get_status()


@router.get("/balances")
async def balances(exchange: str = Query("kucoin")):
    from integrations.trading_engine import get_balances
    result = get_balances(exchange)
    if "error" in result:
        raise HTTPException(502, result["error"])
    return result


@router.get("/ticker")
async def ticker(exchange: str = Query("kucoin"), symbol: str = Query("BTC/USDT")):
    from integrations.trading_engine import get_ticker
    result = get_ticker(exchange, symbol)
    if "error" in result:
        raise HTTPException(502, result["error"])
    return result


@router.post("/order")
async def place_order(req: OrderRequest):
    from integrations.trading_engine import place_order
    result = place_order(req.exchange, req.symbol, req.side, req.amount, req.strategy)
    if "error" in result:
        raise HTTPException(502, result["error"])
    return result


@router.post("/strategy/{name}")
async def run_strategy(name: str, exchange: str = Query("kucoin")):
    from integrations.trading_engine import execute_strategy, STRATEGIES
    if name not in STRATEGIES:
        raise HTTPException(404, f"Strategy '{name}' not found. Available: {list(STRATEGIES)}")
    return {"strategy": name, "results": execute_strategy(name, exchange)}


@router.post("/run-all")
async def run_all(exchange: str = Query("kucoin")):
    from integrations.trading_engine import run_all_strategies
    return run_all_strategies(exchange)


@router.get("/history")
async def trade_history(limit: int = Query(50, le=500)):
    from integrations.trading_engine import get_recent_trades
    return {"trades": get_recent_trades(limit)}


@router.get("/strategies")
async def list_strategies():
    from integrations.trading_engine import STRATEGIES
    return {"strategies": list(STRATEGIES.keys()), "details": STRATEGIES}
