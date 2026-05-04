from fastapi import APIRouter
from integrations.github_monitor import check_commits, check_releases

router = APIRouter(prefix="/github", tags=["github"])


@router.get("/commits")
def recent_commits(since: str | None = None):
    return check_commits(since_iso=since)


@router.get("/releases")
def latest_releases():
    return check_releases()
