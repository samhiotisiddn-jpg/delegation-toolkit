from fastapi import APIRouter, Body
from integrations import stripe_client
from integrations.supabase_client import query, insert

router = APIRouter(prefix="/products", tags=["products"])


@router.get("/")
def list_products():
    return stripe_client.list_products()


@router.post("/checkout")
def create_checkout(
    product_name:     str   = Body(...),
    price_aud_cents:  int   = Body(...),
    customer_email:   str | None = Body(None),
    success_url:      str   = Body("https://localhost/success"),
    cancel_url:       str   = Body("https://localhost/cancel"),
):
    session = stripe_client.create_checkout_session(
        product_name=product_name,
        price_aud_cents=price_aud_cents,
        customer_email=customer_email,
        success_url=success_url,
        cancel_url=cancel_url,
    )
    insert("orders", {
        "stripe_session_id": session["session_id"],
        "amount_aud": price_aud_cents / 100,
        "customer_email": customer_email,
        "status": "pending",
    })
    return session
