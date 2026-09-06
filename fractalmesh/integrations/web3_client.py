"""
Web3 client — EVM RPC abstraction, account management, tx simulation/execution.

ENV:
  WEB3_RPC_URL         HTTP(S) endpoint (Alchemy, Infura, QuickNode, local)
  ETH_PRIVATE_KEY      64-char hex private key (server-side hot wallet)
  WEB3_MODE            sim | live  (default sim — no real transactions)
  REQUIRED_CONFIRMS    default block confirmations (default 1)
"""

import os
import json
import logging
import urllib.request
from decimal import Decimal
from typing import Any

log = logging.getLogger("web3_client")

# ── Optional web3.py ──────────────────────────────────────────────────────────
try:
    from web3 import Web3
    from eth_account import Account
    HAS_WEB3 = True
except Exception as exc:  # pragma: no cover
    log.warning("web3.py not available: %s", exc)
    Web3 = None
    Account = None
    HAS_WEB3 = False

_MODE = os.getenv("WEB3_MODE", "sim").lower()
_LIVE = _MODE == "live"
_RPC_URL = os.getenv("WEB3_RPC_URL", "")
_PRIVATE_KEY = os.getenv("ETH_PRIVATE_KEY", "")
_REQUIRED_CONFIRMS = int(os.getenv("REQUIRED_CONFIRMS", "1"))

_w3: Any = None
_account: Any = None


def _lazy_init() -> Any:
    """Return a connected Web3 instance; raise RuntimeError in live without config."""
    global _w3, _account
    if _w3:
        return _w3
    if not HAS_WEB3:
        raise RuntimeError("web3.py is not installed")
    if not _RPC_URL:
        raise RuntimeError("WEB3_RPC_URL not configured")
    _w3 = Web3(Web3.HTTPProvider(_RPC_URL, request_kwargs={"timeout": 30}))
    if _PRIVATE_KEY:
        _account = Account.from_key(_PRIVATE_KEY)
    return _w3


def get_address() -> str:
    """Return the hot-wallet address."""
    if _PRIVATE_KEY:
        _lazy_init()
        return _account.address
    return os.getenv("ETH_ADDRESS", "")


def is_live() -> bool:
    return _LIVE


def assert_sim(label: str) -> None:
    if not _LIVE:
        raise RuntimeError(
            f"{label} requires WEB3_MODE=live and a configured private key/RPC"
        )


def to_wei(amount: float | Decimal, unit: str = "ether") -> int:
    if not HAS_WEB3:
        return int(amount * 1e18)
    w3 = _lazy_init()
    return w3.to_wei(str(amount), unit)


def from_wei(wei: int, unit: str = "ether") -> float:
    if not HAS_WEB3:
        return wei / 1e18
    w3 = _lazy_init()
    return float(w3.from_wei(wei, unit))


def estimate_gas(tx_dict: dict) -> int | None:
    """Estimate gas for a tx dict; non-live returns a placeholder."""
    if not _LIVE:
        return 21000
    w3 = _lazy_init()
    try:
        return w3.eth.estimate_gas(tx_dict)
    except Exception as exc:
        log.warning("gas estimation failed: %s", exc)
        return None


def build_base_tx(to: str, value_wei: int = 0, data: str = "0x") -> dict:
    """Build a base transaction dict from the hot wallet."""
    assert_sim("build_base_tx live execution")
    w3 = _lazy_init()
    if not _account:
        raise RuntimeError("ETH_PRIVATE_KEY not configured")
    tx = {
        "from": _account.address,
        "to": Web3.to_checksum_address(to),
        "value": value_wei,
        "data": data,
        "nonce": w3.eth.get_transaction_count(_account.address),
        "chainId": w3.eth.chain_id,
    }
    # EIP-1559 if available
    try:
        base_fee = w3.eth.get_block("latest")["baseFeePerGas"]
        tip = w3.to_wei("1", "gwei")
        tx["maxPriorityFeePerGas"] = tip
        tx["maxFeePerGas"] = base_fee + (tip * 2)
    except Exception:
        tx["gasPrice"] = w3.eth.gas_price
    tx["gas"] = estimate_gas(tx) or 300000
    return tx


def send_transaction(tx_dict: dict) -> dict:
    """Sign and broadcast a transaction; return receipt summary."""
    assert_sim("send_transaction")
    w3 = _lazy_init()
    signed = _account.sign_transaction(tx_dict)
    tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    return {
        "tx_hash": tx_hash.hex(),
        "status": receipt.status,
        "gas_used": receipt.gasUsed,
        "block_number": receipt.blockNumber,
        "confirmations": _REQUIRED_CONFIRMS,
    }


def call_contract(contract_address: str, abi: list, fn_name: str, *args) -> Any:
    """Call a read-only contract function."""
    assert_sim("call_contract live read")
    w3 = _lazy_init()
    contract = w3.eth.contract(address=Web3.to_checksum_address(contract_address), abi=abi)
    return getattr(contract.functions, fn_name)(*args).call()


def transact_contract(contract_address: str, abi: list, fn_name: str,
                      *args, value_wei: int = 0) -> dict:
    """Execute a state-changing contract function."""
    assert_sim("transact_contract")
    w3 = _lazy_init()
    contract = w3.eth.contract(address=Web3.to_checksum_address(contract_address), abi=abi)
    fn = getattr(contract.functions, fn_name)(*args)
    tx = fn.build_transaction({
        "from": _account.address,
        "value": value_wei,
        "nonce": w3.eth.get_transaction_count(_account.address),
    })
    return send_transaction(tx)


def get_balance(address: str | None = None) -> dict:
    """Return native balance for an address."""
    if not _LIVE:
        return {"address": address or get_address(), "balance_eth": 0.0, "mode": "sim"}
    w3 = _lazy_init()
    addr = Web3.to_checksum_address(address or _account.address)
    return {
        "address": addr,
        "balance_eth": from_wei(w3.eth.get_balance(addr)),
        "mode": "live",
    }


def rpc_call(method: str, params: list | None = None) -> Any:
    """Generic JSON-RPC over HTTP (used for fallback / custom methods)."""
    if not _RPC_URL:
        raise RuntimeError("WEB3_RPC_URL not set")
    payload = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": method, "params": params or []
    }).encode()
    req = urllib.request.Request(
        _RPC_URL, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    if "error" in data:
        raise RuntimeError(data["error"])
    return data.get("result")
