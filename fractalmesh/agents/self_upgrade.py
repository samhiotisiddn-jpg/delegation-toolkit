"""
Self-upgrade / self-healing agent.

1. Mirror configured GitHub repos into a local cache.
2. Fetch latest commits and inspect diff against baseline.
3. Use LLM gate to classify patch as SAFE / NEEDS_REVIEW / DANGEROUS.
4. Apply SAFE patches onto a working branch, update orchestrator registry diff.
5. Hot-reload orchestrator registry if supported.

ENV:
  UPGRADE_REPOS          comma-separated owner/repo list
  UPGRADE_BASELINE_SHA   commit SHA treated as baseline
  UPGRADE_WORK_BRANCH    branch to write patches (default claude/self-upgrade)
  GITHUB_TOKEN           for private repos and higher rate limits
"""

import os
import re
import json
import shutil
import logging
import subprocess
import urllib.request
from datetime import datetime
from pathlib import Path

from integrations.openrouter import complete, FREE_MODELS

log = logging.getLogger("self_upgrade")

_UPGRADE_DIR = Path(os.path.expanduser(os.getenv("UPGRADE_CACHE_DIR", "~/ai-mesh/upgrade_cache")))
_REPOS = [r.strip() for r in os.getenv("UPGRADE_REPOS", "").split(",") if r.strip()]
_WORK_BRANCH = os.getenv("UPGRADE_WORK_BRANCH", "claude/self-upgrade")
_BASELINE_SHA = os.getenv("UPGRADE_BASELINE_SHA", "")
_BASE = "https://api.github.com"


def _headers() -> dict:
    h = {"Accept": "application/vnd.github+json", "User-Agent": "FractalMesh/SelfUpgrade"}
    token = os.getenv("GITHUB_TOKEN", "")
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _get(path: str) -> dict | list:
    req = urllib.request.Request(f"{_BASE}{path}", headers=_headers())
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def _repo_dir(repo: str) -> Path:
    return _UPGRADE_DIR / repo.replace("/", "_")


def mirror_repo(repo: str, force: bool = False) -> Path:
    dest = _repo_dir(repo)
    url = f"https://github.com/{repo}.git"
    if force and dest.exists():
        shutil.rmtree(dest)
    if not dest.exists():
        _UPGRADE_DIR.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "--mirror", url, str(dest)], check=True)
        log.info("mirrored %s", repo)
    else:
        subprocess.run(["git", "-C", str(dest), "fetch", "origin"], check=False)
    return dest


def _safe_repo_name(repo: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", repo)


def get_commits_since(repo: str, since_sha: str) -> list[dict]:
    refs = _get(f"/repos/{repo}/commits?sha=main&per_page=20")
    commits = []
    for c in refs:
        commits.append(c)
        if c["sha"] == since_sha:
            break
    return commits


def llm_classify_patch(commit_message: str, diff_text: str) -> str:
    prompt = (
        "Classify this code patch for an autonomous system as one of:\n"
        "SAFE, NEEDS_REVIEW, DANGEROUS.\n"
        "Rules:\n"
        "- SAFE = bugfix/docs/requirements-version-bumps only, no credential changes.\n"
        "- NEEDS_REVIEW = new feature, changes to environment handling, or non-trivial logic.\n"
        "- DANGEROUS = deletes files, modifies secrets handling, adds remote downloads, obfuscated code.\n\n"
        f"Commit message: {commit_message}\n\n"
        f"Diff (truncated):\n{diff_text[:2000]}\n\n"
        "Reply ONLY with SAFE, NEEDS_REVIEW, or DANGEROUS."
    )
    try:
        result = complete(prompt, model=FREE_MODELS[0], max_tokens=10)
        label = result.strip().upper()
        if label in ("SAFE", "NEEDS_REVIEW", "DANGEROUS"):
            return label
    except Exception as exc:
        log.warning("LLM classify failed: %s", exc)
    return "NEEDS_REVIEW"


def apply_patch_to_working_repo(repo: str, commit_sha: str, work_tree: Path) -> dict:
    """Cherry-pick a single commit into the active checkout branch."""
    safe = _safe_repo_name(repo)
    mirror = mirror_repo(repo)
    if not work_tree.exists():
        subprocess.run(["git", "clone", str(mirror), str(work_tree)], check=True)
        subprocess.run(["git", "-C", str(work_tree), "checkout", "main"], check=False)
    try:
        subprocess.run(["git", "-C", str(work_tree), "fetch", str(mirror), f"{commit_sha}:refs/remotes/cache/{commit_sha}"], check=True)
        subprocess.run(["git", "-C", str(work_tree), "cherry-pick", commit_sha], check=True)
        return {"status": "applied", "repo": repo, "sha": commit_sha}
    except subprocess.CalledProcessError as exc:
        subprocess.run(["git", "-C", str(work_tree), "cherry-pick", "--abort"], check=False)
        return {"status": "conflict", "repo": repo, "sha": commit_sha, "error": str(exc)}


def upgrade_cycle() -> dict:
    """Run one full self-upgrade cycle."""
    summary = {"scanned": 0, "safe_patches": 0, "applied": 0, "review": 0, "dangerous": 0, "failures": []}
    for repo in _REPOS:
        try:
            mirror_repo(repo)
            baseline = _BASELINE_SHA
            if not baseline:
                baseline_data = _get(f"/repos/{repo}/commits?per_page=1&sha=main")
                baseline = baseline_data[0]["sha"] if baseline_data else ""
            commits = get_commits_since(repo, baseline)
            summary["scanned"] += len(commits)
            for c in commits:
                sha = c["sha"]
                if sha == baseline:
                    continue
                diff_data = _get(f"/repos/{repo}/commits/{sha}")
                diff_text = diff_data.get("files", [])
                diff_text = "\n".join(f['patch'] for f in diff_text if f.get('patch'))
                label = llm_classify_patch(c["commit"]["message"], diff_text)
                if label == "DANGEROUS":
                    summary["dangerous"] += 1
                    continue
                if label == "NEEDS_REVIEW":
                    summary["review"] += 1
                    continue
                work_tree = _UPGRADE_DIR / f"{_safe_repo_name(repo)}_work"
                applied = apply_patch_to_working_repo(repo, sha, work_tree)
                if applied["status"] == "applied":
                    summary["applied"] += 1
                else:
                    summary["failures"].append(applied)
        except Exception as exc:
            log.error("upgrade cycle repo %s: %s", repo, exc)
            summary["failures"].append({"repo": repo, "error": str(exc)})
    return summary
