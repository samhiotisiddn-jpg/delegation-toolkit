import secrets
from fastapi import APIRouter, Body, Header, HTTPException
from integrations.supabase_client import query, insert, update
from integrations import slack

router = APIRouter(prefix="/affiliate", tags=["affiliate"])


def _get_affiliate(token: str | None):
    if not token or not token.startswith("Bearer "):
        return None
    tok = token.replace("Bearer ", "")
    rows = query("affiliates", {"api_token": tok, "is_active": True}, limit=1)
    return rows[0] if rows else None


@router.post("/register")
def register_affiliate(
    name:            str   = Body(...),
    email:           str   = Body(...),
    commission_rate: float = Body(0.20),
):
    code  = secrets.token_hex(6).upper()
    token = secrets.token_urlsafe(32)
    aff = insert("affiliates", {
        "name":            name,
        "email":           email,
        "affiliate_code":  code,
        "api_token":       token,
        "commission_rate": commission_rate,
    })
    slack.send("New affiliate registered", level="info",
               fields={"name": name, "code": code, "rate": f"{commission_rate*100:.0f}%"})
    return {"affiliate_code": code, "api_token": token, "commission_rate": commission_rate}


@router.get("/dashboard")
def dashboard(authorization: str | None = Header(None)):
    aff = _get_affiliate(authorization)
    if not aff:
        raise HTTPException(status_code=401, detail="Invalid affiliate token")

    referrals = query("affiliate_referrals", {"affiliate_id": aff["id"]}, limit=500)
    total_commission = sum(float(r.get("commission_aud", 0)) for r in referrals)

    return {
        "affiliate_code":   aff["affiliate_code"],
        "commission_rate":  aff["commission_rate"],
        "total_referrals":  len(referrals),
        "total_commission_aud": total_commission,
        "referral_link":    f"https://yourdomain.com/?ref={aff['affiliate_code']}",
        "recent_referrals": referrals[:10],
    }


@router.get("/leaderboard")
def leaderboard():
    affs = query("affiliates", limit=20)
    ranked = sorted(affs, key=lambda x: x.get("total_revenue", 0), reverse=True)
    return [{"name": a["name"], "code": a["affiliate_code"],
             "referrals": a["total_referrals"],
             "revenue_aud": a["total_revenue"]} for a in ranked]
