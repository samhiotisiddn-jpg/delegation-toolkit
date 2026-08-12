# Safe Payment Webhook Architecture

A defensive blueprint for receiving payment-provider webhooks without executing transactions autonomously or exposing secrets.

## Goals

- Verify webhook signatures to reject forged payloads.
- Ensure idempotency so the same event is never processed twice.
- Maintain a strict payment-intent state machine.
- Log every decision to an immutable audit table.
- Require explicit human approval before any disbursement, refund, or payout.

## Architecture

```
┌──────────────┐     HTTPS/TLS      ┌──────────────────┐
│   Stripe /   │ ──────────────────▶│  Webhook handler │
│   Square /   │    signed payload  │  (stateless)     │
│   Gumroad    │                    └────────┬─────────┘
└──────────────┘                             │
                                             ▼
                              ┌─────────────────────────────┐
                              │ Signature check             │
                              │ Idempotency check           │
                              │ State-machine validation    │
                              └────────┬────────────────────┘
                                       │
                          ┌────────────┼────────────┐
                          ▼            ▼            ▼
                    Audit log    Idempotent    Human approval
                                 record        queue (for payouts)
```

## Webhook handler checklist

| Step | Required | Notes |
|---|---|---|
| TLS termination | ✅ | Use a reverse proxy or load balancer with a valid certificate. |
| Signature verification | ✅ | Compute HMAC-SHA256 with the provider signing secret. Reject on mismatch. |
| Timestamp tolerance | ✅ | Reject payloads older than 5 minutes. |
| Idempotency key | ✅ | Store `event.id` and refuse replays. |
| Event type allow-list | ✅ | Only process known event types. |
| State validation | ✅ | Confirm the payment intent status transition is legal. |
| Audit logging | ✅ | Append-only; include event id, timestamp, source IP, signature result. |
| Human gate | ✅ | Payouts, refunds, and non-standard flows go to a human approval queue. |

## Example: Stripe webhook signature verification (Python/FastAPI)

```python
import hmac
import hashlib
import stripe
from fastapi import Header, HTTPException, Request

STRIPE_WEBHOOK_SECRET = "whsec_..."  # From environment

@app.post("/webhooks/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="Stripe-Signature"),
):
    payload = await request.body()
    try:
        event = stripe.Webhook.construct_event(
            payload, stripe_signature, STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        raise HTTPException(400, "Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(401, "Invalid signature")

    # Idempotency guard
    if already_processed(event["id"]):
        return {"status": "already processed"}

    # State-machine validation
    if event["type"] == "payment_intent.succeeded":
        pi = event["data"]["object"]
        if pi["status"] != "succeeded":
            raise HTTPException(409, "Unexpected payment intent status")

    # Audit log (append-only)
    audit_log(event, decision="accepted")

    # Human approval queue for anything beyond simple order fulfillment
    if event["type"] in {"charge.refunded", "payout.created"}:
        enqueue_for_human_approval(event)
        return {"status": "pending human approval"}

    process_fulfillment(event)
    return {"status": "ok"}
```

## Circuit breaker guidance

- **Signature failures**: fail-closed. Return `401` and alert ops.
- **Provider API unavailability**: fail-open for reads, fail-closed for writes.
- **Database unavailability**: queue events durably (e.g., Redis Streams, SQS) and retry with exponential backoff.

## Secret storage

Never put `STRIPE_SECRET_KEY` or `STRIPE_WEBHOOK_SECRET` in code. Use:

- Environment variables for local development.
- A secrets manager (AWS Secrets Manager, HashiCorp Vault, 1Password Secrets Automation) for production.
- GitHub Actions secrets for CI/CD.

## Audit table schema (PostgreSQL example)

```sql
CREATE TABLE webhook_audit (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    provider TEXT NOT NULL,
    event_id TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    signature_valid BOOLEAN NOT NULL,
    decision TEXT NOT NULL,
    payload JSONB NOT NULL,
    source_ip INET
);
```

Enable Row Level Security to make this table append-only for the webhook role:

```sql
ALTER TABLE webhook_audit ENABLE ROW LEVEL SECURITY;
CREATE POLICY webhook_audit_append_only ON webhook_audit
    FOR ALL
    TO webhook_role
    USING (false)
    WITH CHECK (true);
```

## What this template does NOT allow

- Autonomous transaction execution without human approval.
- Autonomous refunds, payouts, chargebacks, or fund movements.
- Reading or scraping customer data beyond what the webhook delivers.
- Dark-web or unverified-source integrations.

## References

- Stripe webhook signatures: https://docs.stripe.com/webhooks/signatures
- OWASP Cheat Sheet: Web Service Security
- NIST SP 800-63 Digital Identity Guidelines
