"""Trade by exit-entry point transform.

Migrated from: scripts/trade/prep_trade.R (216 lines)

Reads legacy Tableau CSV data for trade by exit-entry point and writes
to Google Sheets.

Sources:
  - Local CSV: data/trade/ (legacy Tableau export)
Output: Google Sheet 1zw1vHUE3wkKNEs-A9FZvxfmkXAxxrmSJLuVntxCQ2lc
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from pipeline.config.registry import get_sheet_id
from pipeline.loaders.google_sheets import write_sheet

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "trade"
OUTPUT_SHEET_ID = get_sheet_id("trade", "output")


def transform() -> pd.DataFrame:
    """Fetch and transform trade by exit-entry point."""
    return _read_legacy_csv()


def _read_legacy_csv() -> pd.DataFrame:
    """Read legacy Tableau trade CSV."""
    legacy_file = DATA_DIR / "Export_Channel+ (ExportsImports_byExitEntry_byState_monthly.xlsx)_Export_Channel.csv"
    if not legacy_file.exists():
        return pd.DataFrame()

    try:
        df = pd.read_csv(legacy_file)
        if "Updated as of" in df.columns:
            df["Updated as of"] = pd.to_datetime(df["Updated as of"], dayfirst=True, errors="coerce")
        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
        keep = ["State", "Date", "Type of trade", "Exit-entry point",
                "Value (RM mil)", "Updated as of"]
        df = df[[c for c in keep if c in df.columns]]
        return df
    except Exception as e:
        logger.warning("Failed to read legacy trade CSV: %s", e)
        return pd.DataFrame()


def load(df: pd.DataFrame) -> None:
    """Write trade data to Google Sheets."""
    if not df.empty:
        write_sheet(df, OUTPUT_SHEET_ID, "data")


def main() -> pd.DataFrame:
    """Run full trade pipeline."""
    df = transform()
    load(df)
    return df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
