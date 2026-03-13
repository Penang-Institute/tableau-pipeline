"""Fetch data from GitHub APIs (MoH-Malaysia repositories)."""

import io
import logging
import os

import pandas as pd
import requests

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"


def _github_headers(accept: str = "application/vnd.github+json") -> dict:
    """Build GitHub API headers, using GITHUB_TOKEN if available."""
    headers = {"Accept": accept}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def get_commit_shas(
    repo: str,
    path: str,
    branch: str = "main",
    per_page: int = 30,
) -> list[dict]:
    """Fetch commit history for a specific file in a GitHub repo.

    Returns a flat list of commit objects (paginated via Link headers).
    Mirrors the R httr2 req_perform_iterative(iterate_with_link_url()) pattern.
    """
    url = f"{GITHUB_API}/repos/{repo}/commits"
    params = {"sha": branch, "path": path, "per_page": per_page}
    headers = _github_headers()

    all_commits = []
    while url:
        resp = requests.get(url, params=params, headers=headers, timeout=30)
        resp.raise_for_status()
        all_commits.extend(resp.json())
        # Follow Link: <next_url>; rel="next" pagination
        url = resp.links.get("next", {}).get("url")
        params = {}  # params already encoded in the next URL
    logger.info("Fetched %d commits for %s/%s", len(all_commits), repo, path)
    return all_commits


def get_file_at_commit(
    repo: str,
    path: str,
    sha: str,
) -> pd.DataFrame:
    """Fetch a CSV file's content at a specific commit SHA.

    Mirrors the R req_file_content_single() pattern from hospitals.R.
    """
    url = f"{GITHUB_API}/repos/{repo}/contents/{path}"
    headers = _github_headers(accept="application/vnd.github.raw+json")
    resp = requests.get(url, params={"ref": sha}, headers=headers, timeout=30)
    resp.raise_for_status()
    return pd.read_csv(io.StringIO(resp.text))
