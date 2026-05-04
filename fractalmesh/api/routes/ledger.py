import os
from fastapi import APIRouter, Body, HTTPException
from integrations.ledger import import_ledger
from integrations.supabase_client import query

router = APIRouter(prefix="/ledger", tags=["ledger"])


@router.post("/import")
def import_from_db(db_path: str = Body(..., embed=True)):
    if not os.path.exists(db_path):
        raise HTTPException(status_code=404, detail=f"File not found: {db_path}")
    records = import_ledger(db_path)
    return {"imported": len(records), "records": records}


@router.get("/income")
def get_income(limit: int = 100):
    return query("orders", filters={"customer_email": "ledger@local"}, limit=limit)
