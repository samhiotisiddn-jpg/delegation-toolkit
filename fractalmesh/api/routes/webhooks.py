import json
from fastapi import APIRouter, Request, HTTPException, Header
from integrations import stripe_client, slack, make_webhooks
from integrations.supabase_client import insert, update, query

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None),
):
    payload = await request.body()
    try:
        event = stripe_client.construct_webhook_event(payload, stripe_signature)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    insert("webhook_events", {
        "source": "stripe",
        "event_type": event["type"],
        "payload": dict(event),
    })

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        rows = query("orders", {"stripe_session_id": session["id"]})
        if rows:
            update("orders", rows[0]["id"], {
                "status": "paid",
                "stripe_payment_intent": session.get("payment_intent"),
                "raw": session,
            })
        slack.send("Payment received", level="info", fields={
            "amount": f"${session.get('amount_total', 0)/100:.2f} AUD",
            "email":  session.get("customer_email", "unknown"),
        })
        make_webhooks.trigger("payment.completed", session)

    return {"status": "ok"}


@router.post("/make")
async def make_webhook(request: Request):
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    insert("webhook_events", {
        "source": "make",
        "event_type": payload.get("event"),
        "payload": payload,
    })
    return {"status": "received"}
