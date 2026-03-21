#!/usr/bin/env python3
"""
fractalmesh/agents/rf_correlator.py
====================================
Dual-Bite RF Correlator
-----------------------
Cross-references WiGLE SSID temporal-drop events against Sentinel-2
NDVI/structural-subsidence proxy data for a defined AOI (Area of Interest).

A "Dual-Bite" correlation fires when:
  1. WiGLE records a significant drop in observed SSIDs at a location cluster
     within the analysis window  (RF Bite)
  2. Sentinel-2 shows a concurrent negative NDVI delta or surface-change
     anomaly in the same spatial cell  (Structural Bite)

Both signals together indicate potential infrastructure stress or building
envelope change worth escalating.

Environment variables (never hardcode credentials):
    WIGLE_API_NAME          — WiGLE encoded credential name
    WIGLE_API_TOKEN         — WiGLE encoded credential token
    SENTINELHUB_CLIENT_ID   — Copernicus Sentinel Hub OAuth2 client ID
    SENTINELHUB_CLIENT_SECRET — Sentinel Hub OAuth2 secret
    SUPABASE_URL            — Supabase project URL
    SUPABASE_SERVICE_KEY    — Supabase service-role key
    ABN                     — Operator ABN for watermarking (default: 56628117363)
    CORRELATOR_AOI          — JSON: {"lat_min":...,"lat_max":...,"lng_min":...,"lng_max":...}
    CORRELATOR_WINDOW_DAYS  — look-back window in days (default: 30)
    CORRELATOR_SSID_DROP_PCT — SSID count drop threshold % (default: 25)
    CORRELATOR_NDVI_DELTA   — NDVI drop threshold (default: -0.08)

Output: structured JSON report written to stdout; also persisted to Supabase
        table `rf_correlations` if credentials are available.

Usage:
    python3 rf_correlator.py
    python3 rf_correlator.py --dry-run       # no Supabase writes
    python3 rf_correlator.py --aoi '{"lat_min":-36.12,"lat_max":-36.05,"lng_min":146.88,"lng_max":146.96}'
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

# ── graceful optional imports ─────────────────────────────────────────────────
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    import math
    HAS_MATH = True
except ImportError:
    HAS_MATH = False

# ── logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [rf_correlator] %(levelname)s %(message)s",
)
log = logging.getLogger("rf_correlator")


# ── constants / config ────────────────────────────────────────────────────────
ABN = os.getenv("ABN", "56628117363")

_DEFAULT_AOI = {
    "lat_min": -36.12,
    "lat_max": -36.05,
    "lng_min": 146.88,
    "lng_max": 146.96,
}

WINDOW_DAYS = int(os.getenv("CORRELATOR_WINDOW_DAYS", "30"))
SSID_DROP_PCT = float(os.getenv("CORRELATOR_SSID_DROP_PCT", "25"))
NDVI_DELTA_THRESHOLD = float(os.getenv("CORRELATOR_NDVI_DELTA", "-0.08"))

SENTINELHUB_TOKEN_URL = "https://services.sentinel-hub.com/oauth/token"
SENTINELHUB_PROCESS_URL = "https://services.sentinel-hub.com/api/v1/process"
WIGLE_SEARCH_URL = "https://api.wigle.net/api/v2/network/search"
WIGLE_STATS_URL = "https://api.wigle.net/api/v2/stats/country"


# ── WiGLE ─────────────────────────────────────────────────────────────────────

def _wigle_auth_header() -> Optional[str]:
    name = os.getenv("WIGLE_API_NAME")
    token = os.getenv("WIGLE_API_TOKEN")
    if not name or not token:
        log.warning("WIGLE_API_NAME / WIGLE_API_TOKEN not set")
        return None
    cred = base64.b64encode(f"{name}:{token}".encode()).decode()
    return f"Basic {cred}"


def fetch_wigle_networks(aoi: Dict[str, float], since_days: int = 30) -> List[Dict[str, Any]]:
    """Return WiGLE network observations within the AOI for the last *since_days* days."""
    if not HAS_REQUESTS:
        log.error("requests not installed")
        return []

    auth = _wigle_auth_header()
    if not auth:
        return []

    since_ts = int((datetime.now(timezone.utc) - timedelta(days=since_days)).timestamp() * 1000)

    params = {
        "latrange1": aoi["lat_min"],
        "latrange2": aoi["lat_max"],
        "longrange1": aoi["lng_min"],
        "longrange2": aoi["lng_max"],
        "lasttime": since_ts,
        "resultcount": 1000,
    }

    try:
        resp = requests.get(
            WIGLE_SEARCH_URL,
            headers={"Authorization": auth, "Accept": "application/json"},
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        networks = data.get("results", [])
        log.info("WiGLE returned %d networks in AOI", len(networks))
        return networks
    except Exception as exc:
        log.error("WiGLE fetch failed: %s", exc)
        return []


def compute_ssid_temporal_drop(
    networks: List[Dict[str, Any]],
    cell_size_deg: float = 0.005,
) -> List[Dict[str, Any]]:
    """
    Bucket networks into spatial grid cells; compare first-half vs second-half
    observation counts within the window to detect SSID count drops.

    Returns list of cells where the drop exceeds SSID_DROP_PCT.
    """
    if not networks:
        return []

    cells: Dict[Tuple[int, int], List[Dict]] = {}
    for net in networks:
        lat = net.get("trilat") or net.get("lat", 0.0)
        lng = net.get("trilong") or net.get("lon", 0.0)
        ci = int(lat / cell_size_deg)
        cj = int(lng / cell_size_deg)
        cells.setdefault((ci, cj), []).append(net)

    drops = []
    for (ci, cj), members in cells.items():
        if len(members) < 4:
            continue
        # Approximate temporal split by lastupdt field
        members_sorted = sorted(
            members,
            key=lambda n: n.get("lastupdt", "") or "",
        )
        mid = len(members_sorted) // 2
        early_count = len(members_sorted[:mid])
        late_count = len(members_sorted[mid:])
        if early_count == 0:
            continue
        drop_pct = (early_count - late_count) / early_count * 100
        if drop_pct >= SSID_DROP_PCT:
            drops.append({
                "cell_lat": ci * cell_size_deg,
                "cell_lng": cj * cell_size_deg,
                "early_ssid_count": early_count,
                "late_ssid_count": late_count,
                "drop_pct": round(drop_pct, 2),
                "members": len(members),
            })
    log.info("RF bite cells with ≥%.0f%% SSID drop: %d", SSID_DROP_PCT, len(drops))
    return drops


# ── Sentinel Hub ──────────────────────────────────────────────────────────────

def _sentinelhub_token() -> Optional[str]:
    client_id = os.getenv("SENTINELHUB_CLIENT_ID")
    client_secret = os.getenv("SENTINELHUB_CLIENT_SECRET")
    if not client_id or not client_secret:
        log.warning("SENTINELHUB_CLIENT_ID / SENTINELHUB_CLIENT_SECRET not set")
        return None
    if not HAS_REQUESTS:
        return None
    try:
        resp = requests.post(
            SENTINELHUB_TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            },
            timeout=30,
        )
        resp.raise_for_status()
        token = resp.json().get("access_token")
        log.info("Sentinel Hub token acquired")
        return token
    except Exception as exc:
        log.error("Sentinel Hub auth failed: %s", exc)
        return None


def _evalscript_ndvi_delta() -> str:
    """
    Sentinel Hub evalscript: returns mean NDVI for two date ranges so the
    caller can compute delta without downloading imagery.
    """
    return """
//VERSION=3
function setup() {
  return {
    input: [{bands:["B04","B08","dataMask"]}],
    output: {bands:1, sampleType:"FLOAT32"}
  };
}
function evaluatePixel(s) {
  if (!s.dataMask) return [NaN];
  var ndvi = (s.B08 - s.B04) / (s.B08 + s.B04 + 1e-9);
  return [ndvi];
}
"""


def fetch_sentinel2_ndvi(
    aoi: Dict[str, float],
    date_from: str,
    date_to: str,
    token: str,
) -> Optional[float]:
    """
    Return mean NDVI float for the AOI between date_from and date_to (YYYY-MM-DD).
    Uses Sentinel Hub statistical API (lighter than full tile download).
    """
    if not HAS_REQUESTS:
        return None

    bbox = [aoi["lng_min"], aoi["lat_min"], aoi["lng_max"], aoi["lat_max"]]
    body = {
        "input": {
            "bounds": {
                "bbox": bbox,
                "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"},
            },
            "data": [
                {
                    "type": "sentinel-2-l2a",
                    "dataFilter": {
                        "timeRange": {"from": f"{date_from}T00:00:00Z", "to": f"{date_to}T23:59:59Z"},
                        "maxCloudCoverage": 30,
                    },
                }
            ],
        },
        "aggregation": {
            "timeRange": {"from": f"{date_from}T00:00:00Z", "to": f"{date_to}T23:59:59Z"},
            "aggregationInterval": {"of": "P1D"},
            "evalscript": _evalscript_ndvi_delta(),
            "resx": 10,
            "resy": 10,
        },
        "calculations": {
            "default": {
                "statistics": {
                    "default": {
                        "percentiles": {"k": [50]},
                    }
                }
            }
        },
    }

    try:
        resp = requests.post(
            "https://services.sentinel-hub.com/api/v1/statistics",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=body,
            timeout=60,
        )
        resp.raise_for_status()
        intervals = resp.json().get("data", [])
        values = []
        for interval in intervals:
            try:
                median = interval["outputs"]["default"]["bands"]["B0"]["stats"]["percentile_50"]
                if median is not None:
                    values.append(float(median))
            except (KeyError, TypeError):
                continue
        if not values:
            return None
        mean_ndvi = sum(values) / len(values)
        log.info("S2 NDVI (%s → %s): %.4f", date_from, date_to, mean_ndvi)
        return mean_ndvi
    except Exception as exc:
        log.error("Sentinel-2 NDVI fetch failed: %s", exc)
        return None


def compute_ndvi_delta(aoi: Dict[str, float], window_days: int) -> Optional[float]:
    """
    Compute NDVI delta between the early half and late half of the look-back window.
    Returns negative float when vegetation/structure health has declined.
    """
    token = _sentinelhub_token()
    if not token:
        return None

    now = datetime.now(timezone.utc).date()
    mid = now - timedelta(days=window_days // 2)
    start = now - timedelta(days=window_days)

    ndvi_early = fetch_sentinel2_ndvi(aoi, str(start), str(mid), token)
    ndvi_late = fetch_sentinel2_ndvi(aoi, str(mid), str(now), token)

    if ndvi_early is None or ndvi_late is None:
        return None

    delta = ndvi_late - ndvi_early
    log.info("NDVI delta: %.4f  (early=%.4f  late=%.4f)", delta, ndvi_early, ndvi_late)
    return delta


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


def persist_report(report: Dict[str, Any]) -> bool:
    """Insert correlation report into Supabase `rf_correlations` table."""
    if not HAS_REQUESTS:
        return False
    base_url = os.getenv("SUPABASE_URL")
    headers = _supabase_headers()
    if not base_url or not headers:
        log.warning("Supabase credentials not set — skipping persist")
        return False
    try:
        resp = requests.post(
            f"{base_url}/rest/v1/rf_correlations",
            headers=headers,
            json=report,
            timeout=20,
        )
        resp.raise_for_status()
        log.info("Report persisted to Supabase")
        return True
    except Exception as exc:
        log.error("Supabase persist failed: %s", exc)
        return False


# ── correlation engine ────────────────────────────────────────────────────────

def run_dual_bite(
    aoi: Dict[str, float],
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Execute the full Dual-Bite correlation pipeline and return the report.
    """
    ts = datetime.now(timezone.utc).isoformat()
    log.info("Dual-Bite correlation started — AOI=%s window=%dd", aoi, WINDOW_DAYS)

    # ── RF Bite ───────────────────────────────────────────────────────────────
    networks = fetch_wigle_networks(aoi, since_days=WINDOW_DAYS)
    rf_drops = compute_ssid_temporal_drop(networks)

    # ── Structural Bite ───────────────────────────────────────────────────────
    ndvi_delta = compute_ndvi_delta(aoi, WINDOW_DAYS)

    structural_bite = (
        ndvi_delta is not None and ndvi_delta <= NDVI_DELTA_THRESHOLD
    )
    rf_bite = len(rf_drops) > 0

    dual_bite_fired = rf_bite and structural_bite
    confidence = "HIGH" if dual_bite_fired else ("MEDIUM" if (rf_bite or structural_bite) else "LOW")

    report: Dict[str, Any] = {
        "abn": ABN,
        "generated_at": ts,
        "aoi": aoi,
        "window_days": WINDOW_DAYS,
        "dual_bite_fired": dual_bite_fired,
        "confidence": confidence,
        "rf_bite": {
            "fired": rf_bite,
            "ssid_drop_threshold_pct": SSID_DROP_PCT,
            "affected_cells": rf_drops,
            "total_networks_observed": len(networks),
        },
        "structural_bite": {
            "fired": structural_bite,
            "ndvi_delta": ndvi_delta,
            "ndvi_delta_threshold": NDVI_DELTA_THRESHOLD,
        },
        "escalation_required": dual_bite_fired,
        "summary": (
            f"DUAL-BITE FIRED: {len(rf_drops)} RF anomaly cells + NDVI delta {ndvi_delta:.4f}"
            if dual_bite_fired
            else (
                f"SINGLE SIGNAL — RF={'FIRED' if rf_bite else 'CLEAR'} "
                f"NDVI={'FIRED' if structural_bite else 'CLEAR'}"
            )
        ),
    }

    log.info("Correlation complete: %s | confidence=%s", report["summary"], confidence)

    if not dry_run:
        persist_report(report)

    return report


# ── CLI entry ─────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="FractalMesh Dual-Bite RF Correlator")
    parser.add_argument(
        "--aoi",
        default=os.getenv("CORRELATOR_AOI"),
        help="JSON AOI dict with lat_min/lat_max/lng_min/lng_max",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not write to Supabase",
    )
    args = parser.parse_args()

    aoi = _DEFAULT_AOI
    if args.aoi:
        try:
            aoi = json.loads(args.aoi)
        except json.JSONDecodeError as exc:
            log.error("Invalid --aoi JSON: %s", exc)
            sys.exit(1)

    report = run_dual_bite(aoi, dry_run=args.dry_run)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
