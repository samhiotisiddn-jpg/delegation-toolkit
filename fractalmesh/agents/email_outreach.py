"""
Gmail email outreach agent — sends personalised bulk email via Gmail SMTP
using an App Password (no OAuth needed).

ENV:
  GMAIL_ADDRESS      your Gmail address
  GMAIL_APP_PASSWORD 16-char app password from Google Account settings
"""

import os
import time
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from integrations.supabase_client import query, update, insert
from integrations import slack

log = logging.getLogger("email_outreach")

_SMTP_HOST = "smtp.gmail.com"
_SMTP_PORT = 587
_DELAY_SECS = 3  # between sends to avoid spam flags


def _connection():
    addr = os.environ["GMAIL_ADDRESS"]
    pwd  = os.environ["GMAIL_APP_PASSWORD"]
    conn = smtplib.SMTP(_SMTP_HOST, _SMTP_PORT, timeout=15)
    conn.starttls()
    conn.login(addr, pwd)
    return conn, addr


def send_campaign(campaign_id: str) -> dict:
    """Send an email campaign to all opted-in contacts not yet emailed."""
    campaigns = query("email_campaigns", {"id": campaign_id}, limit=1)
    if not campaigns:
        return {"error": "campaign not found"}

    campaign = campaigns[0]
    if campaign["status"] == "sent":
        return {"error": "already sent"}

    contacts = query("email_contacts", {"is_opted_out": False}, limit=1000)
    contacts = [c for c in contacts if not c.get("last_emailed")]

    if not contacts:
        return {"sent": 0, "message": "no eligible contacts"}

    update("email_campaigns", campaign_id, {"status": "sending"})

    conn, sender = _connection()
    sent = 0
    failed = 0

    for contact in contacts:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = campaign["subject"]
            msg["From"]    = sender
            msg["To"]      = contact["email"]
            msg["Reply-To"] = sender

            # Personalise body
            body = campaign["body_text"].replace("{{name}}", contact.get("name") or "there")
            msg.attach(MIMEText(body, "plain"))
            if campaign.get("body_html"):
                html = campaign["body_html"].replace("{{name}}", contact.get("name") or "there")
                msg.attach(MIMEText(html, "html"))

            conn.sendmail(sender, contact["email"], msg.as_string())
            update("email_contacts", contact["id"], {
                "last_emailed": "now()",
            })
            sent += 1
            time.sleep(_DELAY_SECS)

        except Exception as exc:
            log.warning("failed to send to %s: %s", contact["email"], exc)
            failed += 1

    conn.quit()
    update("email_campaigns", campaign_id, {
        "status": "sent",
        "total_sent": sent,
    })

    insert("alerts", {
        "source": "email_outreach",
        "level":  "info",
        "title":  f"Campaign sent: {campaign['name']}",
        "body":   f"{sent} sent, {failed} failed",
    })
    slack.send(f"Email campaign complete: {campaign['name']}", level="info",
               fields={"sent": str(sent), "failed": str(failed)})

    return {"sent": sent, "failed": failed}


def add_contact(email: str, name: str = "", source: str = "", tags: list | None = None) -> dict:
    from integrations.supabase_client import insert
    return insert("email_contacts", {
        "email":  email,
        "name":   name,
        "source": source,
        "tags":   tags or [],
    })
