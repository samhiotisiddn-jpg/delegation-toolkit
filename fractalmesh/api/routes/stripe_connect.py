"""
Stripe Connect — create connected accounts and onboarding links.
Based on the furever-demo pattern.
"""

import os
import stripe
from fastapi import APIRouter, Body, HTTPException
from integrations.supabase_client import insert
from integrations import slack

router = APIRouter(prefix="/connect", tags=["stripe-connect"])


def _init():
    stripe.api_key = os.environ["STRIPE_SECRET_KEY"]


@router.post("/account")
def create_connected_account(email: str = Body(..., embed=True)):
    _init()
    account = stripe.Account.create(
        type="express",
        email=email,
        capabilities={"transfers": {"requested": True}},
    )
    insert("alerts", {
        "source": "stripe-connect",
        "level":  "info",
        "title":  f"Connected account created: {account.id}",
        "body":   email,
    })
    return {"account_id": account.id}


@router.post("/onboarding-link")
def create_onboarding_link(
    account_id:  str = Body(...),
    refresh_url: str = Body("https://localhost/refresh"),
    return_url:  str = Body("https://localhost/return"),
):
    _init()
    link = stripe.AccountLink.create(
        account=account_id,
        refresh_url=refresh_url,
        return_url=return_url,
        type="account_onboarding",
    )
    return {"url": link.url, "expires_at": link.expires_at}


@router.get("/account/{account_id}")
def get_account(account_id: str):
    _init()
    try:
        acct = stripe.Account.retrieve(account_id)
        return {
            "id":             acct.id,
            "email":          acct.email,
            "charges_enabled": acct.charges_enabled,
            "payouts_enabled": acct.payouts_enabled,
            "details_submitted": acct.details_submitted,
        }
    except stripe.error.InvalidRequestError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/transfer")
def create_transfer(
    amount_cents:  int = Body(...),
    account_id:    str = Body(...),
    description:   str = Body("FractalMesh transfer"),
):
    _init()
    transfer = stripe.Transfer.create(
        amount=amount_cents,
        currency="aud",
        destination=account_id,
        description=description,
    )
    slack.send("Transfer created", level="info", fields={
        "amount": f"${amount_cents/100:.2f} AUD",
        "to": account_id,
    })
    return {"transfer_id": transfer.id, "amount": amount_cents}
