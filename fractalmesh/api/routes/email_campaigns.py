from fastapi import APIRouter, Body, BackgroundTasks
from integrations.supabase_client import query, insert
from agents.email_outreach import send_campaign, add_contact

router = APIRouter(prefix="/email", tags=["email"])


@router.get("/campaigns")
def list_campaigns():
    return query("email_campaigns", limit=50)


@router.post("/campaigns")
def create_campaign(
    name:      str = Body(...),
    subject:   str = Body(...),
    body_text: str = Body(...),
    body_html: str | None = Body(None),
):
    return insert("email_campaigns", {
        "name": name, "subject": subject,
        "body_text": body_text, "body_html": body_html,
        "status": "draft",
    })


@router.post("/campaigns/{campaign_id}/send")
def send(campaign_id: str, background_tasks: BackgroundTasks):
    background_tasks.add_task(send_campaign, campaign_id)
    return {"status": "queued", "campaign_id": campaign_id}


@router.get("/contacts")
def list_contacts(limit: int = 100):
    return query("email_contacts", limit=limit)


@router.post("/contacts")
def add(
    email:  str = Body(...),
    name:   str = Body(""),
    source: str = Body(""),
    tags:   list[str] = Body([]),
):
    return add_contact(email, name, source, tags)


@router.post("/contacts/import")
def bulk_import(contacts: list[dict] = Body(...)):
    added = []
    for c in contacts:
        try:
            row = add_contact(
                c.get("email", ""),
                c.get("name", ""),
                c.get("source", "import"),
                c.get("tags", []),
            )
            added.append(row)
        except Exception:
            pass
    return {"imported": len(added)}
