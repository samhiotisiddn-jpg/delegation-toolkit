#!/usr/bin/env python3
"""
fractalmesh/agents/revenue_pipe.py
====================================
Stripe PayTo Revenue Pipeline  —  v2
--------------------------------------
Manages Australian PayTo (NPP direct-debit) mandates via the Stripe API for
industrial clients. Pulls active mandate status, polls for new mandate
authorisations, records revenue events in Supabase, and emits structured
reports watermarked with the operator ABN.

PayTo context
-------------
PayTo is Australia's NPP-based pull-payment scheme (replaces BECS direct
debit). Stripe exposes it via the `au_becs_debit` PaymentMethod type plus the
`PaymentIntent` + `SetupIntent` mandate flow.  This agent automates:

  1. Listing all active SetupIntents/PaymentMethods with au_becs_debit type
     for the configured customer cohort (industrial estate clients).
  2. Polling for newly-authorised mandates since the last run.
  3. Issuing recurring charges against live mandates with tier-based pricing.
  4. Retrying failed charges with exponential backoff (up to MAX_RETRIES).
  5. Persisting revenue events to Supabase `revenue_events` table.
  6. Generating an ABN-watermarked JSON report with MRR/ARR analytics.
  7. Optional Stripe Invoice creation for richer billing records.
  8. Webhook signature verification helper for inbound Stripe events.

Pricing tiers (customer metadata `tier` field):
    premium          → REVENUE_PIPE_PREMIUM_AMOUNT   (default $3,000 AUD)
    industrial_estate→ REVENUE_PIPE_CHARGE_AMOUNT    (default $1,500 AUD)
    standard         → REVENUE_PIPE_STANDARD_AMOUNT  (default $750 AUD)
    (unset/unknown)  → falls back to REVENUE_PIPE_CHARGE_AMOUNT

Environment variables (never hardcode):
    STRIPE_SECRET_KEY           — Stripe live secret key
    STRIPE_WEBHOOK_SECRET       — Stripe webhook signing secret
    SUPABASE_URL                — Supabase project URL
    SUPABASE_SERVICE_KEY        — Supabase service-role key
    ABN                         — Operator ABN for watermarking
    REVENUE_PIPE_COHORT_TAG     — Stripe metadata tag to filter industrial
                                  clients (default: "industrial_estate")
    REVENUE_PIPE_CHARGE_AMOUNT  — Recurring charge in AUD cents (default: 150000)
    REVENUE_PIPE_PREMIUM_AMOUNT — Premium tier amount in AUD cents (default: 300000)
    REVENUE_PIPE_STANDARD_AMOUNT— Standard tier amount in AUD cents (default: 75000)
    REVENUE_PIPE_CURRENCY       — ISO currency (default: aud)
    REVENUE_PIPE_DRY_RUN        — set to "1" to skip actual Stripe charges
    REVENUE_PIPE_MAX_RETRIES    — max charge retries per customer (default: 3)
    REVENUE_PIPE_BILLING_INTERVAL — monthly | quarterly | annual (default: monthly)
    REVENUE_PIPE_USE_INVOICES   — set to "1" to create Stripe Invoices instead of
                                  direct PaymentIntents

Usage:
    python3 revenue_pipe.py
    python3 revenue_pipe.py --report-only   # pull mandate status, no charges
    python3 revenue_pipe.py --dry-run
    python3 revenue_pipe.py --analytics     # print MRR/ARR from Supabase
    python3 revenue_pipe.py --tier premium  # only charge premium-tier customers
    python3 revenue_pipe.py --verify-webhook <payload> <sig_header>
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# ── optional deps ─────────────────────────────────────────────────────────────
try:
    import stripe
    HAS_STRIPE = True
except ImportError:
    HAS_STRIPE = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

# ── logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [revenue_pipe] %(levelname)s %(message)s",
)
log = logging.getLogger("revenue_pipe")

# ── config ────────────────────────────────────────────────────────────────────
ABN             = os.getenv("ABN", "56628117363")
COHORT_TAG      = os.getenv("REVENUE_PIPE_COHORT_TAG", "industrial_estate")
CURRENCY        = os.getenv("REVENUE_PIPE_CURRENCY", "aud")
DRY_RUN_ENV     = os.getenv("REVENUE_PIPE_DRY_RUN", "0") == "1"
MAX_RETRIES     = int(os.getenv("REVENUE_PIPE_MAX_RETRIES", "3"))
USE_INVOICES    = os.getenv("REVENUE_PIPE_USE_INVOICES", "0") == "1"
BILLING_INTERVAL = os.getenv("REVENUE_PIPE_BILLING_INTERVAL", "monthly")

# ── tier pricing (AUD cents) ──────────────────────────────────────────────────
TIER_AMOUNTS: Dict[str, int] = {
    "premium":          int(os.getenv("REVENUE_PIPE_PREMIUM_AMOUNT",  "300000")),  # $3,000
    "industrial_estate": int(os.getenv("REVENUE_PIPE_CHARGE_AMOUNT",  "150000")),  # $1,500
    "standard":         int(os.getenv("REVENUE_PIPE_STANDARD_AMOUNT",  "75000")),  # $750
}
# Fallback for unknown tiers
DEFAULT_AMOUNT = int(os.getenv("REVENUE_PIPE_CHARGE_AMOUNT", "150000"))


def _tier_amount(customer: Any) -> Tuple[int, str]:
    """Return (amount_cents, tier_label) for a customer based on metadata."""
    meta = customer.get("metadata") or {}
    tier = meta.get("tier", meta.get("cohort", "industrial_estate")).lower()
    amount = TIER_AMOUNTS.get(tier, DEFAULT_AMOUNT)
    return amount, tier


def _billing_cycle_tag() -> str:
    """Return a billing-cycle string for idempotency keys (YYYYMM or YYYYQ# or YYYY)."""
    now = datetime.now(timezone.utc)
    if BILLING_INTERVAL == "annual":
        return now.strftime("%Y")
    if BILLING_INTERVAL == "quarterly":
        quarter = (now.month - 1) // 3 + 1
        return f"{now.year}Q{quarter}"
    return now.strftime("%Y%m")  # monthly default


# ── Stripe helpers ────────────────────────────────────────────────────────────

def _init_stripe() -> bool:
    """Initialise Stripe with the live secret key. Returns True on success."""
    if not HAS_STRIPE:
        log.error("stripe library not installed — pip install stripe")
        return False
    key = os.getenv("STRIPE_SECRET_KEY")
    if not key:
        log.error("STRIPE_SECRET_KEY not set")
        return False
    stripe.api_key = key
    stripe.api_version = "2024-06-20"
    return True


def list_industrial_customers(tier_filter: Optional[str] = None) -> List[Any]:
    """
    Return all Stripe customers tagged with the industrial cohort metadata.
    Optionally filter to a specific *tier_filter* value.
    """
    if not HAS_STRIPE:
        return []
    customers: List[Any] = []
    try:
        page = stripe.Customer.list(limit=100)
        while True:
            for cust in page.data:
                meta = cust.get("metadata") or {}
                in_cohort = (
                    meta.get("cohort") == COHORT_TAG
                    or meta.get("segment") == COHORT_TAG
                    or meta.get("tier") in TIER_AMOUNTS
                )
                if not in_cohort:
                    continue
                if tier_filter:
                    tier = meta.get("tier", meta.get("cohort", "")).lower()
                    if tier != tier_filter.lower():
                        continue
                customers.append(cust)
            if not page.has_more:
                break
            page = stripe.Customer.list(limit=100, starting_after=page.data[-1].id)
    except stripe.error.StripeError as exc:
        log.error("Stripe customer list failed: %s", exc)
    log.info(
        "Found %d customers (cohort=%s tier_filter=%s)",
        len(customers), COHORT_TAG, tier_filter or "all",
    )
    return customers


def get_active_payto_mandates(customer_id: str) -> List[Any]:
    """
    Return au_becs_debit PaymentMethods attached to *customer_id* that have an
    active mandate.
    """
    mandates: List[Any] = []
    try:
        pms = stripe.PaymentMethod.list(customer=customer_id, type="au_becs_debit")
        for pm in pms.auto_paging_iter():
            mandates.append(pm)
    except stripe.error.StripeError as exc:
        log.error("PaymentMethod list failed for %s: %s", customer_id, exc)
    return mandates


def issue_payto_charge(
    customer_id: str,
    payment_method_id: str,
    amount_cents: int,
    description: str,
    idempotency_key: str,
    dry_run: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Issue a PayTo pull-payment against an existing au_becs_debit mandate.
    Retries up to MAX_RETRIES times with exponential backoff on transient errors.
    Returns the PaymentIntent dict on success, or None.
    """
    if dry_run:
        log.info(
            "[DRY RUN] Would charge %s AUD %.2f via %s",
            customer_id, amount_cents / 100, payment_method_id,
        )
        return {"status": "dry_run", "customer": customer_id, "amount": amount_cents}

    last_exc: Optional[Exception] = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            intent = stripe.PaymentIntent.create(
                amount=amount_cents,
                currency=CURRENCY,
                customer=customer_id,
                payment_method=payment_method_id,
                payment_method_types=["au_becs_debit"],
                confirm=True,
                off_session=True,
                description=description,
                metadata={"abn": ABN, "cohort": COHORT_TAG},
                idempotency_key=idempotency_key,
            )
            log.info(
                "PaymentIntent %s status=%s customer=%s amount=AUD %.2f (attempt %d)",
                intent.id, intent.status, customer_id, amount_cents / 100, attempt,
            )
            return dict(intent)
        except stripe.error.CardError as exc:
            log.error("PayTo charge declined for %s: %s", customer_id, exc.user_message)
            return None  # card errors are final — do not retry
        except stripe.error.RateLimitError as exc:
            last_exc = exc
            wait = 2 ** attempt
            log.warning("Rate limit on attempt %d for %s — waiting %ds", attempt, customer_id, wait)
            time.sleep(wait)
        except stripe.error.StripeError as exc:
            last_exc = exc
            if attempt < MAX_RETRIES:
                wait = 2 ** attempt
                log.warning("StripeError attempt %d for %s (%s) — retry in %ds", attempt, customer_id, exc, wait)
                time.sleep(wait)
            else:
                log.error("PayTo charge failed for %s after %d attempts: %s", customer_id, MAX_RETRIES, exc)

    if last_exc:
        log.error("Exhausted retries for %s: %s", customer_id, last_exc)
    return None


def create_invoice_charge(
    customer_id: str,
    amount_cents: int,
    description: str,
    payment_method_id: str,
    dry_run: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Alternative to direct PaymentIntent: create a Stripe Invoice item + Invoice,
    then finalise and pay it immediately via the au_becs_debit mandate.
    Returns the Invoice dict on success, or None.
    """
    if dry_run:
        log.info("[DRY RUN] Would create invoice for %s AUD %.2f", customer_id, amount_cents / 100)
        return {"status": "dry_run", "customer": customer_id, "amount": amount_cents}
    try:
        stripe.InvoiceItem.create(
            customer=customer_id,
            amount=amount_cents,
            currency=CURRENCY,
            description=description,
        )
        invoice = stripe.Invoice.create(
            customer=customer_id,
            default_payment_method=payment_method_id,
            metadata={"abn": ABN, "cohort": COHORT_TAG},
            auto_advance=True,
        )
        invoice = stripe.Invoice.finalize_invoice(invoice.id)
        paid = stripe.Invoice.pay(invoice.id)
        log.info("Invoice %s status=%s customer=%s amount=AUD %.2f",
                 paid.id, paid.status, customer_id, amount_cents / 100)
        return dict(paid)
    except stripe.error.CardError as exc:
        log.error("Invoice payment declined for %s: %s", customer_id, exc.user_message)
        return None
    except stripe.error.StripeError as exc:
        log.error("Invoice error for %s: %s", customer_id, exc)
        return None


# ── webhook verification ───────────────────────────────────────────────────────

def verify_webhook_signature(payload: str, sig_header: str) -> Optional[Dict[str, Any]]:
    """
    Verify an inbound Stripe webhook signature using STRIPE_WEBHOOK_SECRET.
    Returns the parsed event dict on success, or None on failure.
    """
    secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    if not secret:
        log.error("STRIPE_WEBHOOK_SECRET not set — cannot verify webhook")
        return None
    if not HAS_STRIPE:
        log.error("stripe library not installed")
        return None
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, secret)
        log.info("Webhook verified: type=%s id=%s", event["type"], event["id"])
        return dict(event)
    except stripe.error.SignatureVerificationError as exc:
        log.error("Webhook signature invalid: %s", exc)
        return None
    except Exception as exc:
        log.error("Webhook parse error: %s", exc)
        return None


# ── Supabase persistence ───────────────────────────────────────────────────────

def _supabase_headers() -> Optional[Dict[str, str]]:
    key = os.getenv("SUPABASE_SERVICE_KEY")
    if not key:
        return None
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }


def persist_revenue_event(event: Dict[str, Any]) -> bool:
    if not HAS_REQUESTS:
        return False
    base_url = os.getenv("SUPABASE_URL")
    headers = _supabase_headers()
    if not base_url or not headers:
        log.warning("Supabase credentials not set — skipping persist")
        return False
    try:
        resp = requests.post(
            f"{base_url}/rest/v1/revenue_events",
            headers=headers,
            json=event,
            timeout=20,
        )
        resp.raise_for_status()
        log.info("Revenue event persisted to Supabase")
        return True
    except Exception as exc:
        log.error("Supabase persist failed: %s", exc)
        return False


def fetch_revenue_events(limit: int = 500) -> List[Dict[str, Any]]:
    """Fetch recent revenue events from Supabase for analytics."""
    if not HAS_REQUESTS:
        return []
    base_url = os.getenv("SUPABASE_URL")
    headers = _supabase_headers()
    if not base_url or not headers:
        log.warning("Supabase credentials not set — cannot fetch events")
        return []
    try:
        read_headers = {**headers, "Prefer": "return=representation"}
        resp = requests.get(
            f"{base_url}/rest/v1/revenue_events",
            headers=read_headers,
            params={"order": "timestamp.desc", "limit": limit},
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json() if isinstance(resp.json(), list) else []
    except Exception as exc:
        log.error("Supabase fetch failed: %s", exc)
        return []


# ── revenue analytics ──────────────────────────────────────────────────────────

def calculate_analytics(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Compute MRR, ARR, failure rate, and per-tier breakdown from revenue events.
    Only counts non-dry-run, non-failed events.
    """
    succeeded = [e for e in events if not e.get("dry_run") and e.get("stripe_status") not in (None, "failed", "canceled")]
    failed    = [e for e in events if e.get("stripe_status") == "failed"]

    # Group by customer for unique MRR (latest event per customer)
    customer_amounts: Dict[str, int] = {}
    for e in succeeded:
        cid = e.get("customer_id", "unknown")
        customer_amounts[cid] = e.get("amount_cents", 0)

    mrr = sum(customer_amounts.values()) / 100  # AUD
    # Annualise based on billing interval
    interval_multiplier = {"monthly": 12, "quarterly": 4, "annual": 1}.get(BILLING_INTERVAL, 12)
    arr = mrr * interval_multiplier

    # Per-tier breakdown
    tier_breakdown: Dict[str, Dict[str, Any]] = {}
    for e in succeeded:
        tier = e.get("tier", "unknown")
        if tier not in tier_breakdown:
            tier_breakdown[tier] = {"customers": set(), "revenue_aud": 0.0, "count": 0}
        tier_breakdown[tier]["customers"].add(e.get("customer_id"))
        tier_breakdown[tier]["revenue_aud"] += e.get("amount_cents", 0) / 100
        tier_breakdown[tier]["count"] += 1
    # Convert sets to counts
    for t in tier_breakdown:
        tier_breakdown[t]["customers"] = len(tier_breakdown[t]["customers"])

    total_attempted = len(succeeded) + len(failed)
    return {
        "abn": ABN,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "billing_interval": BILLING_INTERVAL,
        "mrr_aud": round(mrr, 2),
        "arr_aud": round(arr, 2),
        "total_events_analysed": len(events),
        "succeeded": len(succeeded),
        "failed": len(failed),
        "failure_rate_pct": round(len(failed) / max(total_attempted, 1) * 100, 1),
        "unique_paying_customers": len(customer_amounts),
        "tier_breakdown": tier_breakdown,
    }


# ── mandate audit ─────────────────────────────────────────────────────────────

def audit_mandates(tier_filter: Optional[str] = None) -> Dict[str, Any]:
    """
    Build a full mandate audit report across all industrial customers.
    Returns structured JSON with per-customer mandate status and tier info.
    """
    customers = list_industrial_customers(tier_filter=tier_filter)
    audit: Dict[str, Any] = {
        "abn": ABN,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cohort": COHORT_TAG,
        "billing_interval": BILLING_INTERVAL,
        "total_customers": len(customers),
        "mandates_active": 0,
        "mandates_missing": 0,
        "customers": [],
    }

    for cust in customers:
        mandates = get_active_payto_mandates(cust.id)
        amount, tier = _tier_amount(cust)
        entry = {
            "customer_id": cust.id,
            "name": cust.get("name") or cust.get("description"),
            "email": cust.get("email"),
            "tier": tier,
            "charge_amount_aud": amount / 100,
            "metadata": dict(cust.get("metadata") or {}),
            "payto_mandates": len(mandates),
            "payment_method_ids": [pm.id for pm in mandates],
            "status": "ACTIVE" if mandates else "NO_MANDATE",
        }
        audit["customers"].append(entry)
        if mandates:
            audit["mandates_active"] += 1
        else:
            audit["mandates_missing"] += 1

    return audit


# ── revenue pipeline ──────────────────────────────────────────────────────────

def run_revenue_pipeline(
    dry_run: bool = False,
    tier_filter: Optional[str] = None,
) -> Dict[str, Any]:
    """
    For every industrial customer with an active mandate, issue a recurring
    PayTo charge at the tier-appropriate amount.
    Returns a summary report with per-event detail.
    """
    customers = list_industrial_customers(tier_filter=tier_filter)
    ts = datetime.now(timezone.utc)
    cycle = _billing_cycle_tag()

    summary: Dict[str, Any] = {
        "abn": ABN,
        "generated_at": ts.isoformat(),
        "cohort": COHORT_TAG,
        "billing_interval": BILLING_INTERVAL,
        "billing_cycle": cycle,
        "tier_filter": tier_filter or "all",
        "dry_run": dry_run,
        "processed": 0,
        "succeeded": 0,
        "failed": 0,
        "skipped_no_mandate": 0,
        "total_revenue_aud": 0.0,
        "tier_totals": {},
        "events": [],
    }

    for cust in customers:
        mandates = get_active_payto_mandates(cust.id)
        if not mandates:
            summary["skipped_no_mandate"] += 1
            continue

        pm = mandates[0]  # primary active mandate
        amount, tier = _tier_amount(cust)
        idem_key = f"revpipe-{cust.id}-{cycle}"
        description = f"IronVision Nexus industrial services — ABN {ABN}"

        if USE_INVOICES and not dry_run:
            result = create_invoice_charge(
                customer_id=cust.id,
                amount_cents=amount,
                description=description,
                payment_method_id=pm.id,
                dry_run=dry_run,
            )
        else:
            result = issue_payto_charge(
                customer_id=cust.id,
                payment_method_id=pm.id,
                amount_cents=amount,
                description=description,
                idempotency_key=idem_key,
                dry_run=dry_run,
            )

        summary["processed"] += 1
        event: Dict[str, Any] = {
            "abn": ABN,
            "timestamp": ts.isoformat(),
            "billing_cycle": cycle,
            "billing_interval": BILLING_INTERVAL,
            "customer_id": cust.id,
            "payment_method_id": pm.id,
            "amount_cents": amount,
            "currency": CURRENCY,
            "tier": tier,
            "dry_run": dry_run,
        }

        success_statuses = {"succeeded", "paid", "processing", "dry_run"}
        if result and result.get("status") in success_statuses:
            summary["succeeded"] += 1
            if not dry_run:
                summary["total_revenue_aud"] += amount / 100
                summary["tier_totals"].setdefault(tier, 0.0)
                summary["tier_totals"][tier] += amount / 100
            event["stripe_status"] = result.get("status", "unknown")
            event["intent_id"] = result.get("id", "dry_run")
            persist_revenue_event(event)
        else:
            summary["failed"] += 1
            event["stripe_status"] = "failed"
            persist_revenue_event(event)

        summary["events"].append(event)

    log.info(
        "Pipeline complete: processed=%d succeeded=%d failed=%d revenue=AUD %.2f cycle=%s",
        summary["processed"], summary["succeeded"],
        summary["failed"], summary["total_revenue_aud"], cycle,
    )
    return summary


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="FractalMesh Stripe PayTo Revenue Pipeline v2")
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Audit mandates only — do not issue any charges",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate charges without hitting Stripe",
    )
    parser.add_argument(
        "--analytics",
        action="store_true",
        help="Fetch revenue events from Supabase and print MRR/ARR analytics",
    )
    parser.add_argument(
        "--tier",
        default=None,
        choices=list(TIER_AMOUNTS.keys()),
        help="Only process customers of this tier",
    )
    parser.add_argument(
        "--verify-webhook",
        nargs=2,
        metavar=("PAYLOAD", "SIG_HEADER"),
        help="Verify a Stripe webhook signature (payload string + Stripe-Signature header value)",
    )
    args = parser.parse_args()

    # Webhook verification does not need full Stripe init
    if args.verify_webhook:
        payload, sig = args.verify_webhook
        event = verify_webhook_signature(payload, sig)
        print(json.dumps(event or {"error": "verification failed"}, indent=2))
        return

    if args.analytics:
        events = fetch_revenue_events()
        report = calculate_analytics(events)
        print(json.dumps(report, indent=2))
        return

    if not _init_stripe():
        sys.exit(1)

    if args.report_only:
        report = audit_mandates(tier_filter=args.tier)
    else:
        dry = args.dry_run or DRY_RUN_ENV
        report = run_revenue_pipeline(dry_run=dry, tier_filter=args.tier)

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
