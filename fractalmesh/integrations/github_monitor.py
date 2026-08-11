"""
GitHub repo monitor — polls configured repos for new commits/releases
and fires Slack + Make.com alerts on activity.

Env vars:
  GITHUB_USERNAME   e.g. samhiotisiddn-jpg
  GITHUB_REPOS      comma-separated repo names
  GITHUB_TOKEN      personal access token (optional, raises rate limit)
"""

import os
import json
import urllib.request

from integrations import slack, make_webhooks
from integrations.supabase_client import insert

_BASE = "https://api.github.com"


def _headers() -> dict:
    h = {"Accept": "application/vnd.github+json", "User-Agent": "FractalMesh/1.0"}
    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _get(path: str) -> dict | list:
    req = urllib.request.Request(f"{_BASE}{path}", headers=_headers())
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def _repos() -> list[str]:
    user  = os.environ.get("GITHUB_USERNAME", "")
    names = os.environ.get("GITHUB_REPOS", "")
    return [f"{user}/{n.strip()}" for n in names.split(",") if n.strip()]


def check_commits(since_iso: str | None = None) -> list[dict]:
    """Return new commits across all watched repos since `since_iso`."""
    results = []
    for repo in _repos():
        try:
            path = f"/repos/{repo}/commits"
            if since_iso:
                path += f"?since={since_iso}"
            commits = _get(path)
            for c in (commits if isinstance(commits, list) else []):
                entry = {
                    "repo":    repo,
                    "sha":     c["sha"][:7],
                    "message": c["commit"]["message"].split("\n")[0][:120],
                    "author":  c["commit"]["author"]["name"],
                    "url":     c["html_url"],
                    "at":      c["commit"]["author"]["date"],
                }
                results.append(entry)
        except Exception as exc:
            print(f"[github] error fetching {repo}: {exc}")
    return results


def check_releases() -> list[dict]:
    """Return latest release for each watched repo."""
    results = []
    for repo in _repos():
        try:
            release = _get(f"/repos/{repo}/releases/latest")
            if "tag_name" in release:
                results.append({
                    "repo":       repo,
                    "tag":        release["tag_name"],
                    "name":       release.get("name", ""),
                    "url":        release["html_url"],
                    "published":  release.get("published_at", ""),
                })
        except Exception:
            pass
    return results


def alert_new_commits(since_iso: str) -> None:
    commits = check_commits(since_iso)
    for c in commits:
        insert("alerts", {
            "source": "github",
            "level":  "info",
            "title":  f"New commit: {c['repo']}",
            "body":   f"{c['sha']} — {c['message']} ({c['author']})",
            "raw":    c,
        })
        slack.send(
            title=f"GitHub: {c['repo']}",
            body=f"`{c['sha']}` {c['message']}",
            level="info",
            fields={"author": c["author"], "url": c["url"]},
        )
        make_webhooks.trigger("github.commit", c)
