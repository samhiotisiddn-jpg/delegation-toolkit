import os
import stripe


def _init():
    stripe.api_key = os.environ["STRIPE_SECRET_KEY"]


def create_checkout_session(product_name: str, price_aud_cents: int,
                             customer_email: str | None = None,
                             success_url: str = "https://localhost/success",
                             cancel_url: str = "https://localhost/cancel") -> dict:
    _init()
    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[{
            "price_data": {
                "currency": "aud",
                "unit_amount": price_aud_cents,
                "product_data": {"name": product_name},
            },
            "quantity": 1,
        }],
        mode="payment",
        customer_email=customer_email,
        success_url=success_url,
        cancel_url=cancel_url,
    )
    return {"session_id": session.id, "url": session.url}


def construct_webhook_event(payload: bytes, sig_header: str) -> stripe.Event:
    _init()
    secret = os.environ["STRIPE_WEBHOOK_SECRET"]
    return stripe.Webhook.construct_event(payload, sig_header, secret)


def list_products() -> list:
    _init()
    products = stripe.Product.list(active=True, limit=100)
    prices   = {p.product: p for p in stripe.Price.list(active=True, limit=100).data}
    result = []
    for prod in products.data:
        price = prices.get(prod.id)
        result.append({
            "id":          prod.id,
            "name":        prod.name,
            "description": prod.description,
            "price_aud":   price.unit_amount / 100 if price else None,
            "price_id":    price.id if price else None,
        })
    return result
