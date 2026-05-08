"""Printful print-on-demand integration."""
import os
import urllib.request
import json
import logging

log = logging.getLogger("printful")

_BASE = "https://api.printful.com"
_KEY = os.getenv("PRINTFUL_API_KEY", "")


def _headers() -> dict:
    if not _KEY:
        raise ValueError("PRINTFUL_API_KEY not set")
    return {
        "Authorization": f"Bearer {_KEY}",
        "Content-Type": "application/json",
    }


def _get(path: str) -> dict:
    req = urllib.request.Request(f"{_BASE}{path}", headers=_headers())
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def _post(path: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{_BASE}{path}",
        data=data,
        headers=_headers(),
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def get_store_info() -> dict:
    try:
        return _get("/store")
    except Exception as exc:
        log.warning("printful get_store_info: %s", exc)
        return {}


def list_products() -> list[dict]:
    try:
        data = _get("/store/products?limit=100")
        return data.get("result", [])
    except Exception as exc:
        log.warning("printful list_products: %s", exc)
        return []


def get_product(product_id: int) -> dict:
    try:
        return _get(f"/store/products/{product_id}").get("result", {})
    except Exception as exc:
        log.warning("printful get_product %d: %s", product_id, exc)
        return {}


def list_catalog_products(category_id: int | None = None) -> list[dict]:
    path = "/products"
    if category_id:
        path += f"?category_id={category_id}"
    try:
        data = _get(path)
        return data.get("result", [])
    except Exception as exc:
        log.warning("printful list_catalog_products: %s", exc)
        return []


def create_order(recipient: dict, items: list[dict]) -> dict:
    """Create a Printful order.
    recipient: {name, address1, city, country_code, zip, email}
    items: [{sync_variant_id, quantity}]
    """
    try:
        return _post("/orders", {"recipient": recipient, "items": items})
    except Exception as exc:
        log.warning("printful create_order: %s", exc)
        return {"error": str(exc)}


def get_shipping_rates(recipient: dict, items: list[dict]) -> list[dict]:
    try:
        data = _post("/shipping/rates", {"recipient": recipient, "items": items})
        return data.get("result", [])
    except Exception as exc:
        log.warning("printful get_shipping_rates: %s", exc)
        return []
