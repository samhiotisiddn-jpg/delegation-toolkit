from fastapi import APIRouter, Query
from integrations.supabase_client import query

router = APIRouter(prefix="/trades", tags=["trades"])


@router.get("/")
def list_trades(limit: int = Query(50, le=500), status: str | None = None):
    filters = {"status": status} if status else None
    return query("trades", filters=filters, limit=limit)
