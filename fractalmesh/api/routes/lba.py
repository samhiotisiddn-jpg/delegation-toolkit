"""LBA Firewall routes — sovereign identity, payload validation, request signing."""
import os
import hmac
import hashlib
import json
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/lba", tags=["lba"])

_PROTECTED_FIELDS = {"TFN", "ETH_PRIVATE_KEY", "BANKWEST_PASS", "BANKWEST_ACCOUNT", "PRIVATE_KEY"}


def _sovereign_identity() -> dict:
    return {
        "abn":      os.getenv("ABN", "56628117363"),
        "entity":   os.getenv("ENTITY", "IronVision Nexus"),
        "director": os.getenv("DIRECTOR", "Samuel James Hiotis"),
        "email":    os.getenv("EMAIL", "sam.hiotis@gmail.com"),
        "address":  "Unit 9/520 Crisp Street, Albury, NSW 2640",
        "eth_address": os.getenv("ETH_ADDRESS", ""),
    }


def _sign(payload: dict, secret: str) -> str:
    body = json.dumps(payload, sort_keys=True).encode()
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _validate(payload: dict) -> tuple[bool, str]:
    payload_str = json.dumps(payload).upper()
    for field in _PROTECTED_FIELDS:
        if field in payload_str:
            return False, f"Protected field detected: {field}"
    return True, "ok"


class ValidateRequest(BaseModel):
    payload: dict


class SignRequest(BaseModel):
    payload: dict
    secret: str


@router.get("/identity")
async def get_identity():
    """Return sovereign ABN/entity metadata."""
    return _sovereign_identity()


@router.post("/validate")
async def validate_payload(req: ValidateRequest):
    """Check if a payload is safe to transmit (no protected fields)."""
    ok, reason = _validate(req.payload)
    return {"safe": ok, "reason": reason}


@router.post("/sign")
async def sign_payload(req: SignRequest):
    """HMAC-SHA256 sign a payload with provided secret."""
    sig = _sign(req.payload, req.secret)
    return {"signature": sig, "algorithm": "hmac-sha256"}


@router.get("/headers")
async def sovereign_headers():
    """Return recommended X-IronVision-* headers to inject in outbound requests."""
    ident = _sovereign_identity()
    return {
        "X-IronVision-ABN":    ident["abn"],
        "X-IronVision-Entity": ident["entity"],
        "X-IronVision-Email":  ident["email"],
    }


@router.get("/health")
async def lba_health():
    return {"status": "online", "entity": os.getenv("ENTITY", "IronVision Nexus")}
