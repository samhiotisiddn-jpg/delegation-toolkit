"""WiGLE RF data oracle + Copernicus satellite DEM routes."""
from fastapi import APIRouter, Query, HTTPException
import os

router = APIRouter(prefix="/oracle", tags=["oracle"])


@router.get("/rf")
async def extract_rf(radius_deg: float = Query(0.05, ge=0.01, le=0.5)):
    """Query WiGLE API for WiFi networks around HQ."""
    from integrations.wigle_oracle import extract_wigle_rf
    result = extract_wigle_rf(radius_deg)
    if "error" in result:
        raise HTTPException(502, result["error"])
    return result


@router.get("/dem")
async def extract_dem():
    """Generate Copernicus GLO-30 DEM metadata for HQ area."""
    from integrations.wigle_oracle import extract_satellite_dem
    return extract_satellite_dem()


@router.post("/package")
async def package_dataset(data_path: str, name: str | None = None):
    """Package a raw data file as a distributable zip archive."""
    from integrations.wigle_oracle import package_dataset
    if not os.path.exists(data_path):
        raise HTTPException(404, f"File not found: {data_path}")
    return package_dataset(data_path, name)


@router.get("/datasets")
async def list_datasets():
    """List all packaged data archives."""
    from integrations.wigle_oracle import list_datasets
    return {"datasets": list_datasets()}


@router.get("/raw-feeds")
async def list_raw_feeds():
    """List raw RF/DEM JSON extracts."""
    from integrations.wigle_oracle import list_raw_feeds
    return {"feeds": list_raw_feeds()}


@router.post("/run-cycle")
async def run_full_cycle():
    """Run full oracle cycle: RF extract + DEM + package both."""
    from integrations.wigle_oracle import extract_wigle_rf, extract_satellite_dem, package_dataset
    results = {}
    rf = extract_wigle_rf()
    results["rf"] = rf
    dem = extract_satellite_dem()
    results["dem"] = dem

    for label, r in [("rf", rf), ("dem", dem)]:
        if "path" in r and not r.get("error"):
            pack = package_dataset(r["path"])
            results[f"{label}_package"] = pack

    return results
