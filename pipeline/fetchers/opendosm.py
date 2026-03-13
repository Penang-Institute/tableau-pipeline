"""Fetch data from OpenDOSM storage (parquet/CSV) and data.gov.my APIs."""

from __future__ import annotations

import io
import logging
from pathlib import Path

import pandas as pd
import requests
import yaml

logger = logging.getLogger(__name__)

_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def _load_config():
    with open(_CONFIG_DIR / "data_sources.yaml") as f:
        return yaml.safe_load(f)


def fetch_parquet(url: str, retries: int = 3, timeout: int = 60) -> pd.DataFrame:
    """Download a parquet file from a URL into a DataFrame.

    Downloads the full content into memory first to avoid PyArrow streaming
    errors on flaky connections (same approach as keyPenangMetrics/metrics.py).
    """
    for attempt in range(retries):
        try:
            resp = requests.get(url, timeout=timeout)
            resp.raise_for_status()
            df = pd.read_parquet(io.BytesIO(resp.content))
            logger.info("Fetched %s (%d rows)", url.split("/")[-1], len(df))
            return df
        except Exception as e:
            if attempt == retries - 1:
                raise
            logger.warning("Attempt %d failed for %s: %s", attempt + 1, url, e)
    raise RuntimeError(f"Failed to fetch {url} after {retries} retries")


def fetch_csv(url: str, timeout: int = 60, **kwargs) -> pd.DataFrame:
    """Download a CSV file from a URL into a DataFrame."""
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text), **kwargs)
    logger.info("Fetched %s (%d rows)", url.split("/")[-1], len(df))
    return df


def get_parquet_url(key: str) -> str:
    """Look up a named parquet URL from data_sources.yaml."""
    cfg = _load_config()
    return cfg["opendosm"]["parquet"][key]


def build_source_url(source1: str, source2: str) -> str:
    """Build a full download URL from opendosm.tsv row values.

    Mirrors the R logic in copy_opendosm.R:
      - If source1 is NA/empty, source2 is already a full URL
      - Otherwise: https://storage.{source1}.gov.my/{source2}
    """
    if pd.isna(source1) or source1.strip() == "":
        return source2.strip()
    return f"https://storage.{source1.strip()}.gov.my/{source2.strip()}"


def load_manifest(repo_root: Path | None = None) -> pd.DataFrame:
    """Load the opendosm.tsv manifest from the repo root."""
    if repo_root is None:
        repo_root = Path(__file__).resolve().parent.parent.parent
    tsv_path = repo_root / "opendosm.tsv"
    df = pd.read_csv(tsv_path, sep="\t")
    df.columns = df.columns.str.strip()
    # Strip whitespace from string columns (the TSV has trailing spaces)
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].str.strip()
    return df
