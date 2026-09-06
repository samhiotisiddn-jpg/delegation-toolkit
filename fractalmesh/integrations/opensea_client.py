"""
OpenSea V2 API client — create listings, buy orders, cancel listings,
and poll collection/asset/listing state.

ENV:
  OPENSEA_API_KEY          OpenSea API key
  OPENSEA_CHAIN            ethereum | polygon | arbitrum | base | sepolia (default ethereum)
  ETH_PRIVATE_KEY          used for order signing; if absent, simulation mode is used
"""

import os
import json
import time
import logging
import urllib.request
import urllib.parse
from typing import Any

from integrations.web3_client import _lazy_init, get_address, assert_sim, HAS_WEB3
from integrations.metamask_proxy import sign_typed_data, get_account

log = logging.getLogger("opensea_client")

_API_KEY = os.getenv("OPENSEA_API_KEY", "")
_CHAIN = os.getenv("OPENSEA_CHAIN", "ethereum")
_BASE = f"https://api.opensea.io/api/v2/chain/{_CHAIN}"
_TESTNET_BASE = "https://testnets-api.opensea.io/api/v2"


def _api_base() -> str:
    return _TESTNET_BASE if _CHAIN in ("sepolia", "mumbai", "amoy") else "https://api.opensea.io/api/v2"


def _headers() -> dict:
    h = {"Accept": "application/json", "Content-Type": "application/json", "X-API-KEY": _API_KEY}
    return h


def _get(path: str) -> dict:
    url = f"{_api_base()}{path}"
    req = urllib.request.Request(url, headers=_headers())
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def _post(path: str, body: dict) -> dict:
    url = f"{_api_base()}{path}"
    payload = json.dumps(body).encode()
    req = urllib.request.Request(url, data=payload, headers=_headers(), method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def get_asset(contract_address: str, token_id: str) -> dict:
    return _get(f"/chain/{_CHAIN}/contract/{contract_address}/nfts/{token_id}")


def get_listings(contract_address: str, token_id: str) -> list[dict]:
    data = _get(f"/chain/{_CHAIN}/contract/{contract_address}/nfts/{token_id}/listings")
    return data.get("listings", [])


def get_collection_offers(slug: str) -> dict:
    return _get(f"/collections/{slug}/offers")


def build_order_signature(typed_data: dict, use_metamask: bool = True) -> str:
    """Sign an OpenSea order typed-data object."""
    assert_sim("build_order_signature")
    if use_metamask and os.getenv("METAMASK_SEED_PHRASE"):
        sig = sign_typed_data(typed_data)
        return sig["signature"]
    if HAS_WEB3:
        w3 = _lazy_init()
        from eth_account.messages import encode_typed_data
        acct = _lazy_init().__dict__.get("_account") or get_account()
        encoded = encode_typed_data(full_message=typed_data)
        return acct.sign_message(encoded).signature.hex()
    raise RuntimeError("No signer configured")


def create_listing(contract_address: str, token_id: str,
                   price_eth: float, expiration_hours: int = 72,
                   payment_token: str | None = None) -> dict:
    """Create a fixed-price listing on OpenSea. Simulation returns mock payload."""
    if not _API_KEY:
        return {"mode": "sim", "contract": contract_address, "token_id": token_id,
                "price_eth": price_eth, "note": "OPENSEA_API_KEY not configured"}
    assert_sim("create_listing")

    # Build offer / order via OpenSea order builder endpoint
    owner = get_address()
    body = {
        "parameters": {
            "offerer": owner,
            "offer": [{
                "itemType": 2,
                "token": contract_address,
                "identifierOrCriteria": token_id,
                "startAmount": "1",
                "endAmount": "1",
            }],
            "consideration": [{
                "itemType": 0 if not payment_token else 1,
                "token": payment_token or "0x0000000000000000000000000000000000000000",
                "identifierOrCriteria": "0",
                "startAmount": str(int(price_eth * 1e18)),
                "endAmount": str(int(price_eth * 1e18)),
                "recipient": owner,
            }],
            "startTime": str(int(time.time())),
            "endTime": str(int(time.time()) + expiration_hours * 3600),
            "orderType": 0,
            "zone": "0x0000000000000000000000000000000000000000",
            "zoneHash": "0x" + "0" * 64,
            "salt": str(int(time.time() * 1000)),
            "conduitKey": "0x" + "0" * 64,
            "totalOriginalConsiderationItems": "1",
        },
        "protocol_address": "0x0000000000000068F116a894984e2DB1123eB395",
    }

    try:
        response = _post(f"/chain/{_CHAIN}/listing", body)
        if "errors" in response:
            log.error("OpenSea listing error: %s", response["errors"])
        return response
    except Exception as exc:
        log.warning("OpenSea listing attempt failed: %s", exc)
        return {"mode": "fallback-sim", "body": body}


def fulfill_listing(order_hash: str) -> dict:
    """Fulfill (buy) an existing listing. Simulation returns mock tx hash."""
    if not _API_KEY:
        return {"mode": "sim", "order_hash": order_hash}
    assert_sim("fulfill_listing")
    try:
        return _post(f"/chain/{_CHAIN}/order/{order_hash}/fulfill", {"taker": get_address()})
    except Exception as exc:
        return {"mode": "fallback-sim", "order_hash": order_hash, "error": str(exc)}


def cancel_order(order_hash: str) -> dict:
    assert_sim("cancel_order")
    try:
        return _post(f"/chain/{_CHAIN}/orders/cancel", {"order_hashes": [order_hash]})
    except Exception as exc:
        return {"mode": "fallback-sim", "order_hash": order_hash, "error": str(exc)}
