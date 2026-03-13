"""Labour force demographics by state and strata transform.

Migrated from: scripts/labour/prep_labour_demo_states_fixed.R (99 lines)

Previously read employment and labour force data from DOSM time series files
on a network drive. Network drive sources have been removed.

Output: Google Sheet 1aU1AEcPuKuc3NmFo2JAs2X84jPfrUxDb9fP0130lzJY
"""

from __future__ import annotations

import logging

import pandas as pd

from pipeline.config.registry import get_sheet_id
from pipeline.loaders.google_sheets import write_sheet

logger = logging.getLogger(__name__)

OUTPUT_SHEET_ID = get_sheet_id("labour_demographics", "output")


def _get_skip_rows(filename: str) -> int | None:
    """Determine skip rows based on file content type."""
    fn = filename.lower()
    if "age" in fn:
        return 4
    if "ethnic" in fn:
        return 7
    if "educational" in fn or "certificate" in fn:
        return 5
    if "marital" in fn:
        return 5
    return None


def _infer_strata(filename: str) -> str:
    """Infer the strata type from filename."""
    fn = filename.lower()
    if "age" in fn:
        return "age group"
    if "ethnic" in fn:
        return "ethnicity"
    if "educational" in fn or "certificate" in fn:
        return "highest certificate"
    if "marital" in fn:
        return "marital status"
    return "unknown"


def _infer_measure(filename: str) -> str:
    """Infer measure (Employed/Labour force) from filename."""
    fn = filename.lower()
    if fn.startswith("employed"):
        return "Employed persons"
    return "Labour force"


def transform() -> pd.DataFrame:
    """Labour demographics: network drive removed.

    The network drive time series files that this transform depended on
    are no longer available. Returns an empty DataFrame.
    """
    logger.info("Labour demographics: network drive removed")
    return pd.DataFrame()


def load(df: pd.DataFrame) -> None:
    """Write labour demographics to Google Sheets."""
    if not df.empty:
        write_sheet(
            df, OUTPUT_SHEET_ID,
            "Principal statistics by state and selected strata",
        )


def main() -> pd.DataFrame:
    """Run full labour demographics pipeline."""
    df = transform()
    load(df)
    return df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
