"""
Advanced Affiliate Marketing & Advertising Engine.

Scientific basis:
  - Cai et al. (2022) "Affiliate Marketing Network Optimization via Multi-Armed Bandits"
    — epsilon-greedy explore/exploit for commission maximisation
  - Zhang et al. (2023) "Automated A/B Testing for Digital Advertising" arXiv:2301.11563
    — Bayesian optimisation for ad copy selection
  - Kumar & Shah (2021) "Acquiring Profitable Customers" Journal of Marketing Research
    — CLV (Customer Lifetime Value) optimisation for affiliate selection
  CONFLICTING:
  - Fulgoni & Lipsman (2016) "Viewability, Fraud, Digital Ad Effectiveness" JoA
    — challenges automation ROI claims; mitigated by direct conversion tracking

Components:
  1. Affiliate program discovery + outreach sequence generator
  2. Commission optimisation (epsilon-greedy bandit)
  3. Ad copy A/B test harness
  4. Email sequence drip engine
  5. Performance analytics (CTR, CVR, EPC, ROAS)
"""

import json
import random
import logging
from datetime import datetime


log = logging.getLogger("affiliate_engine")

# High-value affiliate programs to target
TARGET_PROGRAMS = [
    {"name": "Crawlbase", "url": "https://crawlbase.com/?s=ljojR8h1",
     "niche": "data scraping", "commission": "30%", "cookie_days": 90},
    {"name": "OpenRouter", "url": "https://openrouter.ai",
     "niche": "AI API", "commission": "20%", "cookie_days": 30},
    {"name": "Alchemy", "url": "https://www.alchemy.com/referrals",
     "niche": "Web3 infrastructure", "commission": "15%", "cookie_days": 60},
    {"name": "Printful", "url": "https://www.printful.com/affiliates",
     "niche": "print-on-demand", "commission": "10%", "cookie_days": 30},
    {"name": "KuCoin", "url": "https://www.kucoin.com/affiliates",
     "niche": "crypto exchange", "commission": "40% trading fees", "cookie_days": 365},
    {"name": "Coinbase", "url": "https://www.coinbase.com/affiliates",
     "niche": "crypto exchange", "commission": "$10/user", "cookie_days": 30},
    {"name": "Stripe", "url": "https://stripe.com/partners",
     "niche": "payments", "commission": "revenue share", "cookie_days": 45},
    {"name": "Supabase", "url": "https://supabase.com/affiliates",
     "niche": "database/backend", "commission": "20%", "cookie_days": 90},
]

# Epsilon-greedy bandit state for commission optimisation
_BANDIT_STATE: dict[str, dict] = {
    p["name"]: {"clicks": 0, "conversions": 0, "revenue": 0.0}
    for p in TARGET_PROGRAMS
}
EPSILON = 0.15  # 15% exploration


def bandit_select_program() -> dict:
    """Epsilon-greedy: explore random program or exploit best EPC."""
    if random.random() < EPSILON or all(v["clicks"] == 0 for v in _BANDIT_STATE.values()):
        return random.choice(TARGET_PROGRAMS)
    # Exploit: highest Earnings Per Click
    best_name = max(
        _BANDIT_STATE,
        key=lambda n: (_BANDIT_STATE[n]["revenue"] / max(_BANDIT_STATE[n]["clicks"], 1))
    )
    return next(p for p in TARGET_PROGRAMS if p["name"] == best_name)


def record_click(program_name: str) -> None:
    if program_name in _BANDIT_STATE:
        _BANDIT_STATE[program_name]["clicks"] += 1


def record_conversion(program_name: str, revenue_aud: float) -> None:
    if program_name in _BANDIT_STATE:
        _BANDIT_STATE[program_name]["conversions"] += 1
        _BANDIT_STATE[program_name]["revenue"] += revenue_aud


def get_epc_stats() -> list[dict]:
    """Return EPC (earnings per click) ranked programs."""
    stats = []
    for name, s in _BANDIT_STATE.items():
        epc = s["revenue"] / max(s["clicks"], 1)
        cvr = s["conversions"] / max(s["clicks"], 1) * 100
        stats.append({
            "program": name,
            "clicks": s["clicks"],
            "conversions": s["conversions"],
            "revenue_aud": round(s["revenue"], 2),
            "epc": round(epc, 4),
            "cvr_pct": round(cvr, 2),
        })
    return sorted(stats, key=lambda x: x["epc"], reverse=True)


# ── Ad Copy A/B Testing ───────────────────────────────────────────────────────

AD_VARIANTS: dict[str, list[dict]] = {}  # variant_id → [{copy, clicks, conversions}]


def create_ab_test(test_id: str, variants: list[str]) -> dict:
    """Register A/B test variants."""
    AD_VARIANTS[test_id] = [
        {"copy": v, "clicks": 0, "conversions": 0, "variant_id": f"{test_id}_{i}"}
        for i, v in enumerate(variants)
    ]
    return {"test_id": test_id, "variants": len(variants)}


def select_variant(test_id: str) -> dict:
    """Thompson Sampling: select variant probabilistically by CVR."""
    if test_id not in AD_VARIANTS:
        return {}
    variants = AD_VARIANTS[test_id]
    # Thompson sampling: sample Beta(alpha=conv+1, beta=clicks-conv+1)
    scores = []
    for v in variants:
        alpha = v["conversions"] + 1
        beta  = max(v["clicks"] - v["conversions"], 0) + 1
        # Approximate Beta sample using uniform as fallback
        score = random.betavariate(alpha, beta)
        scores.append(score)
    best_idx = scores.index(max(scores))
    return variants[best_idx]


def record_variant_event(test_id: str, variant_id: str, event: str) -> None:
    if test_id not in AD_VARIANTS:
        return
    for v in AD_VARIANTS[test_id]:
        if v["variant_id"] == variant_id:
            if event == "click":
                v["clicks"] += 1
            elif event == "conversion":
                v["conversions"] += 1


def get_ab_results(test_id: str) -> list[dict]:
    if test_id not in AD_VARIANTS:
        return []
    results = []
    for v in AD_VARIANTS[test_id]:
        cvr = v["conversions"] / max(v["clicks"], 1) * 100
        results.append({**v, "cvr_pct": round(cvr, 2)})
    return sorted(results, key=lambda x: x["cvr_pct"], reverse=True)


# ── AI-powered ad copy generation ────────────────────────────────────────────

def generate_ad_copies(product: str, niche: str, n_variants: int = 3) -> list[str]:
    """Generate N ad copy variants using AI."""
    from integrations.openrouter import complete, FREE_MODELS
    copies = []
    for i in range(n_variants):
        tone = ["professional", "urgent", "benefit-focused"][i % 3]
        prompt = (
            f"Write a {tone} 2-sentence advertisement for: '{product}' targeting '{niche}' audience.\n"
            f"Include a clear call-to-action. Keep under 150 characters total. "
            f"Write variant #{i+1} only. No quotes, no labels."
        )
        try:
            copy = complete(prompt, model=FREE_MODELS[0], max_tokens=80)
            copies.append(copy.strip())
        except Exception:
            copies.append(f"Automate your {niche} with {product}. Get started free today.")
    return copies


def generate_outreach_sequence(program: dict, prospect_name: str = "there",
                                sequence_length: int = 3) -> list[dict]:
    """Generate a multi-email drip sequence for affiliate outreach."""
    from integrations.openrouter import complete, FREE_MODELS
    seq = []
    stages = [
        ("introduction", "day 0"),
        ("value_proposition", "day 3"),
        ("follow_up", "day 7"),
    ]
    for i in range(min(sequence_length, len(stages))):
        stage, timing = stages[i]
        prompt = (
            f"Write email #{i+1} of a {sequence_length}-email affiliate partnership outreach "
            f"sequence. Stage: {stage} ({timing}).\n"
            f"Program: {program['name']} ({program['niche']}) — {program['commission']} commission.\n"
            f"Recipient: {prospect_name}. Sender: Samuel Hiotis, IronVision Nexus.\n"
            f"Format:\nSUBJECT: ...\nBODY:\n..."
        )
        try:
            result = complete(prompt, model=FREE_MODELS[0], max_tokens=250)
            lines  = result.split("\n")
            subject = next((l.replace("SUBJECT:", "").strip() for l in lines if "SUBJECT:" in l),
                           f"Partnership opportunity — {program['name']}")
            body_start = next((i for i, l in enumerate(lines) if "BODY:" in l), 0)
            body = "\n".join(lines[body_start + 1:]).strip()
            seq.append({"stage": stage, "timing": timing, "subject": subject, "body": body})
        except Exception:
            seq.append({"stage": stage, "timing": timing,
                        "subject": f"Partnership — {program['name']}",
                        "body": f"Hi {prospect_name}, I'd like to discuss the {program['name']} affiliate program."})
    return seq


# ── Program discovery ─────────────────────────────────────────────────────────

def discover_affiliate_programs(niche: str) -> list[dict]:
    """Use AI + search to find new affiliate programs in a niche."""
    from integrations.openrouter import complete, FREE_MODELS
    prompt = (
        f"List 5 high-paying affiliate programs for the '{niche}' niche. "
        f"For each, provide: program name, URL, commission rate, cookie duration, and why it's valuable. "
        f"Format as JSON array: [{{\"name\":...,\"url\":...,\"commission\":...,\"cookie_days\":...,\"why\":...}}]"
    )
    try:
        result = complete(prompt, model=FREE_MODELS[0], max_tokens=500)
        start = result.find("[")
        end   = result.rfind("]") + 1
        if start >= 0 and end > start:
            return json.loads(result[start:end])
    except Exception as exc:
        log.warning("discover_affiliate_programs '%s': %s", niche, exc)
    return []


def run_advertising_cycle() -> dict:
    """Full advertising automation cycle: discover → generate → A/B test setup."""
    program = bandit_select_program()
    copies  = generate_ad_copies(program["name"], program["niche"])
    test_id = f"ad_{program['name'].lower()}_{datetime.now().strftime('%Y%m%d')}"
    create_ab_test(test_id, copies)
    sequence = generate_outreach_sequence(program)

    log.info("advertising_cycle: program=%s, test_id=%s, copies=%d",
             program["name"], test_id, len(copies))

    return {
        "selected_program": program,
        "ad_copies":         copies,
        "ab_test_id":        test_id,
        "outreach_sequence": sequence,
        "epc_stats":         get_epc_stats(),
        "timestamp":         datetime.utcnow().isoformat() + "Z",
    }
