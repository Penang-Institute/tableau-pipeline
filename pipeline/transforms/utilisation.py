"""Hospital bed utilisation by state transform.

Migrated from: scripts/health/utilisation_bystate_fixed.R (23 lines)

Fetches hospital bed utilisation data from OpenDOSM parquet, reads manual
utilisation data from a Google Sheet, and writes processed outputs to
Google Sheets for Tableau consumption.

The R script performs three tasks:
  1. Reads manual data from the "Utilisation_bystate" Google Sheet tab and
     filters for Sector=="Public", Sub-sector=="Hospital".
  2. Reads OpenDOSM parquet data and aggregates admitted beds by state & year.
  3. Writes the raw OpenDOSM dataset to the "utilisation_opendosm" Sheet tab.

Source: https://storage.data.gov.my/healthcare/hospital_bed_utlisation_state.parquet
Manual: Google Sheet main workbook, tab "Utilisation_bystate"
Output:
  - Google Sheet "utilisation_opendosm" (raw OpenDOSM data)

The "Utilisation_bystate" manual tab is INPUT ONLY — never written back
(a prior write-back cleared it via clear-then-failed-update).
"""

from __future__ import annotations

import logging

import pandas as pd

from pipeline.fetchers.opendosm import fetch_parquet, get_parquet_url
from pipeline.loaders.google_sheets import write_to_main_workbook

logger = logging.getLogger(__name__)

# Main workbook Sheet ID (from google_sheets_registry.yaml)
_MAIN_WORKBOOK_ID = "1cJe-flqOiDEA9Q9MFe2LCIcY8PmmEc_M3mt-TD7eKQM"
_MANUAL_SHEET_TAB = "Utilisation_bystate"


def transform() -> pd.DataFrame:
    """Fetch hospital bed utilisation data from OpenDOSM parquet.

    Returns the raw DataFrame (unchanged from source).
    """
    url = get_parquet_url("hospital_bed_utilisation")
    ds = fetch_parquet(url)
    logger.info("Utilisation transform: %d rows", len(ds))
    return ds


def transform_manual() -> pd.DataFrame | None:
    """Read manual utilisation data from Google Sheet and filter.

    Reads the "Utilisation_bystate" tab from the main workbook, then filters
    for Sector == "Public" and Sub-sector == "Hospital".

    Returns the filtered DataFrame, or None if the Sheet cannot be read
    (graceful degradation when credentials are unavailable).
    """
    try:
        from pipeline.fetchers.gdrive import read_google_sheet
    except ImportError:
        logger.warning(
            "Could not import read_google_sheet; skipping manual data read"
        )
        return None

    try:
        manual = read_google_sheet(_MAIN_WORKBOOK_ID, _MANUAL_SHEET_TAB)
    except Exception:
        logger.warning(
            "Failed to read manual sheet '%s'; skipping manual data",
            _MANUAL_SHEET_TAB,
            exc_info=True,
        )
        return None

    # Guard against an empty/malformed manual tab (e.g. cleared by a prior
    # failed write) — degrade gracefully instead of KeyError on 'Sector'.
    if manual.empty or "Sector" not in manual.columns:
        logger.warning(
            "Manual sheet '%s' is empty or missing 'Sector' — skipping manual data",
            _MANUAL_SHEET_TAB,
        )
        return None

    # Replace dash/N/A sentinels with NaN (mirrors R: na = c("-", "N/A"))
    manual = manual.replace({"-": pd.NA, "N/A": pd.NA})

    # Filter: Sector == "Public" and Sub-sector == "Hospital"
    mask = (manual["Sector"] == "Public") & (manual["Sub-sector"] == "Hospital")
    filtered = manual[mask].copy().reset_index(drop=True)
    logger.info(
        "Manual utilisation: %d rows after Public/Hospital filter (from %d)",
        len(filtered),
        len(manual),
    )
    return filtered


def transform_aggregated(ds: pd.DataFrame) -> pd.DataFrame:
    """Aggregate OpenDOSM utilisation data by state and year.

    Groups by state and year (extracted from date column), then sums the
    ``admitted`` column.  Mirrors the R code::

        ds |>
          group_by(state, lubridate::year(date)) |>
          summarize(total_admitted = sum(admitted), .groups = "drop")

    Args:
        ds: Raw OpenDOSM utilisation DataFrame (output of ``transform()``).

    Returns:
        Aggregated DataFrame with columns: state, year, total_admitted.
    """
    df = ds.copy()
    df["year"] = pd.to_datetime(df["date"]).dt.year
    aggregated = (
        df.groupby(["state", "year"], as_index=False)["admitted"]
        .sum()
        .rename(columns={"admitted": "total_admitted"})
    )
    logger.info("Aggregated utilisation: %d rows", len(aggregated))
    return aggregated


def load(
    df: pd.DataFrame,
    manual_df: pd.DataFrame | None = None,
) -> None:
    """Write utilisation data to Google Sheets.

    Only the raw OpenDOSM dataset is written, to "utilisation_opendosm" —
    matching the R original (utilisation_bystate_fixed.R). The manual
    "Utilisation_bystate" tab is INPUT ONLY: the prior port wrote a filtered
    copy back onto it, and clear-then-failed-update wiped the manual data.
    manual_df is kept in the signature for compatibility but never persisted.

    Args:
        df: Raw OpenDOSM data written to "utilisation_opendosm".
        manual_df: Read but not written back (see above).
    """
    write_to_main_workbook(df, "utilisation_opendosm")


def main() -> pd.DataFrame:
    """Run full utilisation pipeline.

    Steps:
      1. Fetch raw OpenDOSM parquet data.
      2. Read and filter manual Google Sheet data (Public/Hospital).
      3. Aggregate OpenDOSM data by state and year.
      4. Write raw data and filtered manual data to Google Sheets.

    Returns the raw OpenDOSM DataFrame (for orchestrator compatibility).
    """
    # Step 1: Fetch raw OpenDOSM data
    ds = transform()

    # Step 2: Read and filter manual data (graceful degradation)
    manual_df = transform_manual()

    # Step 3: Aggregate by state and year
    aggregated = transform_aggregated(ds)
    logger.info(
        "Aggregated utilisation summary: %d state-year combinations",
        len(aggregated),
    )

    # Step 4: Write outputs
    load(ds, manual_df=manual_df)

    return ds


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
