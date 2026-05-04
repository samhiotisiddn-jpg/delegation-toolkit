"""
Ledger import — reads a local SQLite income database and syncs
records into the Supabase `orders` table as income entries.
"""

import os
import sqlite3
from integrations.supabase_client import insert
from integrations import slack


def import_ledger(db_path: str) -> list[dict]:
    if not os.path.exists(db_path):
        raise FileNotFoundError(db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT id, amount, type, ts FROM income").fetchall()
    conn.close()

    imported = []
    for row in rows:
        record = dict(row)
        try:
            insert("orders", {
                "stripe_session_id": f"ledger_{record['id']}",
                "amount_aud":        record["amount"],
                "customer_email":    "ledger@local",
                "status":            "paid",
                "raw":               record,
            })
            imported.append(record)
        except Exception:
            pass  # skip duplicates (unique constraint on stripe_session_id)

    if imported:
        slack.send(
            title=f"Ledger imported: {len(imported)} records",
            level="info",
            fields={"source": db_path, "count": str(len(imported))},
        )
    return imported
