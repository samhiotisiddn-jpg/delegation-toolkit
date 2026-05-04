from fastapi import APIRouter, Query, Body
from integrations.supabase_client import query, insert
from integrations import slack, make_webhooks

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("/")
def list_alerts(limit: int = Query(50, le=500), level: str | None = None):
    filters = {"level": level} if level else None
    return query("alerts", filters=filters, limit=limit)


@router.post("/")
def create_alert(
    source: str = Body(...),
    level:  str = Body("info"),
    title:  str = Body(...),
    body:   str = Body(""),
):
    row = insert("alerts", {
        "source": source, "level": level,
        "title": title, "body": body,
    })
    slack.send(title=title, body=body, level=level, fields={"source": source})
    make_webhooks.trigger("alert.created", row)
    return row
