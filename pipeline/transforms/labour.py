"""Labour force statistics transform.

Migrated from: scripts/labour/prep_labour_fixed.R (873 lines)

Processes principal labour statistics (LFPR, employed, unemployed) and
detailed demographics (age, highest cert, marital status, occupation, sector)
from local CSV historical data.

Network drive sources have been removed. The transform functions that
depended on network drive Excel files are no longer available. Only
historical CSV loading and Google Sheets output remain.

Sources:
  - Local CSV: data/labour/*.csv (historical Tableau data)
Output: Multiple Google Sheets (one per demographic category)
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from pipeline.config.registry import get_sheet_id
from pipeline.loaders.google_sheets import write_sheet

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "labour"

STATE_MAP = {
    "N.SEMBILAN": "Negeri Sembilan",
    "P.PINANG": "Pulau Pinang",
    "W.P.KUALA LUMPUR": "W.P. Kuala Lumpur",
    "W.P.LABUAN": "W.P. Labuan",
    "W.P.PUTRAJAYA": "W.P. Putrajaya",
}

OUTPUT_SHEETS = {
    "principal": get_sheet_id("labour", "principal"),
    "lfpr": get_sheet_id("labour", "lfpr"),
    "age": get_sheet_id("labour", "age"),
    "highest_cert": get_sheet_id("labour", "highest_cert"),
    "marital": get_sheet_id("labour", "marital"),
    "occupation": get_sheet_id("labour", "occupation"),
    "sector": get_sheet_id("labour", "sector"),
    "occupation_all_states": get_sheet_id("labour", "occupation_all_states"),
}


def _map_state(name: str) -> str:
    """Map abbreviated state names to full names."""
    if name in STATE_MAP:
        return STATE_MAP[name]
    return name.title()


def _load_historical_csv(filename: str) -> pd.DataFrame:
    """Load a historical Tableau CSV from the data/labour directory.

    Returns empty DataFrame if file does not exist.
    """
    path = DATA_DIR / filename
    if not path.exists():
        logger.info("Historical CSV not found: %s", path)
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception as e:
        logger.warning("Error reading %s: %s", path, e)
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def transform() -> dict[str, pd.DataFrame | None]:
    """Run all labour transforms.

    Network drive sources have been removed. All transform sub-functions
    that depended on network drive Excel files are no longer available.
    Returns None for all output sheets.
    """
    return {k: None for k in OUTPUT_SHEETS}


def load(dfs: dict[str, pd.DataFrame | None]) -> None:
    """Write labour data to Google Sheets."""
    for key, df in dfs.items():
        if df is not None and not df.empty and key in OUTPUT_SHEETS:
            write_sheet(df, OUTPUT_SHEETS[key], "data")


def main() -> dict[str, pd.DataFrame | None]:
    """Run full labour pipeline."""
    dfs = transform()
    load(dfs)
    return dfs


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
