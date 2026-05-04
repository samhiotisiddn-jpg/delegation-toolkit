import os
from supabase import create_client, Client

_client: Client | None = None

def get_client() -> Client:
    global _client
    if _client is None:
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
        _client = create_client(url, key)
    return _client


def insert(table: str, data: dict) -> dict:
    return get_client().table(table).insert(data).execute().data[0]


def query(table: str, filters: dict | None = None, limit: int = 100) -> list:
    q = get_client().table(table).select("*").order("created_at", desc=True).limit(limit)
    for col, val in (filters or {}).items():
        q = q.eq(col, val)
    return q.execute().data


def update(table: str, row_id: str, data: dict) -> dict:
    return get_client().table(table).update(data).eq("id", row_id).execute().data[0]
