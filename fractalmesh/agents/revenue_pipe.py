#!/usr/bin/env python3
"""
fractalmesh/agents/revenue_pipe.py
====================================
Stripe PayTo Revenue Pipeline
------------------------------
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
  3. Issuing recurring charges against live mandates.
  4. Persisting revenue events to Supabase `revenue_events` table.
  5. Generating an ABN-watermarked JSON report.

Environment variables (never hardcode):
    STRIPE_SECRET_KEY           — Stripe live secret key
    STRIPE_WEBHOOK_SECRET       — Stripe webhook signing secret (optional, for
                                  inbound webhook verification)
    SUPABASE_URL                — Supabase project URL
    SUPABASE_SERVICE_KEY        — Supabase service-role key
    ABN                         — Operator ABN for watermarking
    REVENUE_PIPE_COHORT_TAG     — Stripe metadata tag to filter industrial
                                  clients (default: "industrial_estate")
    REVENUE_PIPE_CHARGE_AMOUNT  — Recurring charge amount in AUD cents
                                  (default: 150000 = $1,500.00)
    REVENUE_PIPE_CURRENCY       — ISO currency (default: aud)
    REVENUE_PIPE_DRY_RUN        — set to "1" to skip actual Stripe charges

Usage:
    python3 revenue_pipe.py
    python3 revenue_pipe.py --report-only   # pull mandate status, no charges
    python3 revenue_pipe.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

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
ABN = os.getenv("ABN", "56628117363")
COHORT_TAG = os.getenv("REVENUE_PIPE_COHORT_TAG", "industrial_estate")
CHARGE_AMOUNT = int(os.getenv("REVENUE_PIPE_CHARGE_AMOUNT", "150000"))  # AUD cents
CURRENCY = os.getenv("REVENUE_PIPE_CURRENCY", "aud")
DRY_RUN_ENV = os.getenv("REVENUE_PIPE_DRY_RUN", "0") == "1"


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
    stripe.api_version = "2024-06-20"  # pin to stable version
    return True


def list_industrial_customers() -> List[Any]:
    """Return all Stripe customers tagged with the industrial cohort metadata."""
    if not HAS_STRIPE:
        return []
    customers = []
    try:
        page = stripe.Customer.list(limit=100)
        while True:
            for cust in page.data:
                meta = cust.get("metadata") or {}
                if meta.get("cohort") == COHORT_TAG or meta.get("segment") == COHORT_TAG:
                    customers.append(cust)
            if not page.has_more:
                break
            page = stripe.Customer.list(limit=100, starting_after=page.data[-1].id)
    except stripe.error.StripeError as exc:
        log.error("Stripe customer list failed: %s", exc)
    log.info("Found %d industrial customers (cohort=%s)", len(customers), COHORT_TAG)
    return customers


def get_active_payto_mandates(customer_id: str) -> List[Any]:
    """
    Return au_becs_debit PaymentMethods attached to *customer_id* that have an
    active mandate.  PayTo mandates surface via the `setup_future_usage`
    mechanism and SetupIntent; once authorised, the PaymentMethod persists.
    """
    mandates = []
    try:
        pms = stripe.PaymentMethod.list(customer=customer_id, type="au_becs_debit")
        for pm in pms.auto_paging_iter():
            # A mandate is live when the PaymentMethod is chargeable
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
    Returns the PaymentIntent dict on success, or None.
    """
    if dry_run:
        log.info(
            "[DRY RUN] Would charge %s (%s) AUD %.2f via PaymentMethod %s",
            customer_id,
            description,
            amount_cents / 100,
            payment_method_id,
        )
        return {"status": "dry_run", "customer": customer_id, "amount": amount_cents}

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
            "PaymentIntent %s status=%s customer=%s amount=%.2f AUD",
            intent.id,
            intent.status,
            customer_id,
            amount_cents / 100,
        )
        return dict(intent)
    except stripe.error.CardError as exc:
        log.error("PayTo charge declined for %s: %s", customer_id, exc.user_message)
        return None
    except stripe.error.StripeError as exc:
        log.error("PayTo charge error for %s: %s", customer_id, exc)
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


# ── mandate audit ─────────────────────────────────────────────────────────────

def audit_mandates() -> Dict[str, Any]:
    """
    Build a full mandate audit report across all industrial customers.
    Returns structured JSON with per-customer mandate status.
    """
    customers = list_industrial_customers()
    audit: Dict[str, Any] = {
        "abn": ABN,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cohort": COHORT_TAG,
        "total_customers": len(customers),
        "mandates_active": 0,
        "mandates_missing": 0,
        "customers": [],
    }

    for cust in customers:
        mandates = get_active_payto_mandates(cust.id)
        entry = {
            "customer_id": cust.id,
            "name": cust.get("name") or cust.get("description"),
            "email": cust.get("email"),
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

def run_revenue_pipeline(dry_run: bool = False) -> Dict[str, Any]:
    """
    For every industrial customer with an active mandate, issue a recurring
    PayTo charge.  Returns a summary report.
    """
    customers = list_industrial_customers()
    ts = datetime.now(timezone.utc)

    summary = {
        "abn": ABN,
        "generated_at": ts.isoformat(),
        "cohort": COHORT_TAG,
        "charge_amount_aud": CHARGE_AMOUNT / 100,
        "dry_run": dry_run,
        "processed": 0,
        "succeeded": 0,
        "failed": 0,
        "skipped_no_mandate": 0,
        "total_revenue_aud": 0.0,
        "events": [],
    }

    for cust in customers:
        mandates = get_active_payto_mandates(cust.id)
        if not mandates:
            summary["skipped_no_mandate"] += 1
            continue

        pm = mandates[0]  # use first active mandate
        idem_key = f"revpipe-{cust.id}-{ts.strftime('%Y%m%d')}"
        description = f"IronVision Nexus industrial services — ABN {ABN}"

        result = issue_payto_charge(
            customer_id=cust.id,
            payment_method_id=pm.id,
            amount_cents=CHARGE_AMOUNT,
            description=description,
            idempotency_key=idem_key,
            dry_run=dry_run,
        )

        summary["processed"] += 1
        event: Dict[str, Any] = {
            "abn": ABN,
            "timestamp": ts.isoformat(),
            "customer_id": cust.id,
            "payment_method_id": pm.id,
            "amount_cents": CHARGE_AMOUNT,
            "currency": CURRENCY,
            "dry_run": dry_run,
        }

        if result and result.get("status") not in (None, "requires_payment_method", "canceled"):
            summary["succeeded"] += 1
            if not dry_run:
                summary["total_revenue_aud"] += CHARGE_AMOUNT / 100
            event["stripe_status"] = result.get("status", "unknown")
            event["intent_id"] = result.get("id", "dry_run")
            persist_revenue_event(event)
        else:
            summary["failed"] += 1
            event["stripe_status"] = "failed"

        summary["events"].append(event)

    log.info(
        "Pipeline complete: processed=%d succeeded=%d failed=%d revenue=AUD %.2f",
        summary["processed"],
        summary["succeeded"],
        summary["failed"],
        summary["total_revenue_aud"],
    )
    return summary


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="FractalMesh Stripe PayTo Revenue Pipeline")
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
    args = parser.parse_args()

    if not _init_stripe():
        sys.exit(1)

    if args.report_only:
        report = audit_mandates()
    else:
        dry = args.dry_run or DRY_RUN_ENV
        report = run_revenue_pipeline(dry_run=dry)

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
