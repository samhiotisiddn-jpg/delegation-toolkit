"""Firebase Realtime Database routes."""
from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/firebase", tags=["firebase"])


class RTDBWrite(BaseModel):
    path: str
    data: dict
    token: str | None = None


@router.post("/set")
async def rtdb_set(req: RTDBWrite):
    from integrations.firebase_client import rtdb_set
    result = rtdb_set(req.path, req.data, req.token)
    if "error" in result:
        raise HTTPException(502, result["error"])
    return {"path": req.path, "result": result}


@router.get("/get")
async def rtdb_get(path: str, token: str | None = None):
    from integrations.firebase_client import rtdb_get
    result = rtdb_get(path, token)
    if "error" in result:
        raise HTTPException(502, result["error"])
    return {"path": path, "data": result}


@router.post("/metrics")
async def push_metrics(metrics: dict = Body(...)):
    from integrations.firebase_client import push_metrics
    return push_metrics(metrics)


@router.post("/alert")
async def push_alert(
    title: str = Body(...),
    body: str = Body(...),
    level: str = Body("info"),
):
    from integrations.firebase_client import push_alert
    return push_alert(title, body, level)
