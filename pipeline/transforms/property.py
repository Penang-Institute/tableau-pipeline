"""Property market statistics transform.

Migrated from: scripts/property/property.R (444 lines)

Processes NAPIC (National Property Information Centre) data for Penang:
- Property sales transactions (count + value) by price range and sector
- Residential house prices by state and quantile
- Unsold property status (overhang, under construction, not constructed)
- Newly launched residential units and sales performance

Sources:
  - Google Sheets: legacy data for each category
Output:
  - Google Sheet 1U2myOOIdtLoFnbNkENOvgcvOIXkWfzc6JfGxA7_GuZ8 (transactions)
  - Google Sheet 1NlDArTSUDBGTnJ8H9t6e1AJbdFIQU99dyYTTUW6dWa0 (house prices)
  - Google Sheet 1IE2m_JUXVM2CQuXzh0L9eCvPqivr6nQq1Gvmj_0GLkw (unsold)
  - Google Sheet 1560AqfA5UJRVa3N5y29su3xDRy9sQxWu0ehA-AktOfA (newly launched)
"""

from __future__ import annotations

import logging

import pandas as pd

from pipeline.config.registry import get_sheet_id
from pipeline.fetchers.gdrive import read_google_sheet
from pipeline.loaders.google_sheets import write_sheet

logger = logging.getLogger(__name__)

OUTPUT_SHEETS = {
    "transactions": get_sheet_id("property", "transactions"),
    "house_prices": get_sheet_id("property", "house_prices"),
    "unsold": get_sheet_id("property", "unsold"),
    "newly_launched": get_sheet_id("property", "newly_launched"),
}


def transform_transactions() -> pd.DataFrame:
    """Transform property sales transactions from legacy Google Sheet.

    Mirrors R script lines 17-133 (legacy data path only).
    """
    try:
        legacy = read_google_sheet(
            OUTPUT_SHEETS["transactions"],
            "byPrice&Sector",
        )
        if not legacy.empty:
            if "Sub-sector" in legacy.columns:
                legacy["Sub-sector"] = legacy["Sub-sector"].replace(
                    "Development land", "Development"
                )
            if "Date" in legacy.columns:
                legacy["Date"] = pd.to_datetime(legacy["Date"], errors="coerce")
                legacy["Date"] = legacy["Date"].dt.to_period("Q").dt.to_timestamp()

        output_cols = ["Date", "Sub-sector", "Updated as of", "Price range", "Number", "Value (RM)"]
        available_cols = [c for c in output_cols if c in legacy.columns]
        if "Date" in legacy.columns:
            legacy["Date"] = pd.to_datetime(legacy["Date"], errors="coerce")
        result = legacy[available_cols].copy()

        logger.info("Property transactions: %d rows", len(result))
        return result
    except Exception as e:
        logger.warning("Could not read legacy transaction sheet: %s", e)
        return pd.DataFrame()


def transform_house_prices() -> pd.DataFrame:
    """Transform residential house prices from legacy Google Sheet.

    Mirrors R script lines 136-186 (legacy data path only).
    """
    try:
        legacy = read_google_sheet(
            OUTPUT_SHEETS["house_prices"],
            "House price",
        )
        if not legacy.empty:
            if "House price (RM/unit)" in legacy.columns:
                legacy = legacy.rename(columns={"House price (RM/unit)": "House price"})

        logger.info("House prices: %d rows", len(legacy))
        return legacy
    except Exception as e:
        logger.warning("Could not read legacy house price sheet: %s", e)
        return pd.DataFrame()


def transform_unsold() -> pd.DataFrame:
    """Transform unsold property status from legacy Google Sheet.

    Mirrors R script lines 188-306 (legacy data path only).
    """
    try:
        legacy = read_google_sheet(
            OUTPUT_SHEETS["unsold"],
            "Unsold",
        )
        if not legacy.empty:
            output_cols = [
                "Date", "Status of property", "Price range", "Type",
                "Number of units launched", "Number of unsold units",
                "Unsold value (RM mil)",
            ]
            available = [c for c in output_cols if c in legacy.columns]
            legacy = legacy[available].copy()
            if "Date" in legacy.columns:
                legacy["Date"] = pd.to_datetime(legacy["Date"], errors="coerce")
                legacy["Date"] = legacy["Date"].dt.to_period("Q").dt.to_timestamp()

        logger.info("Unsold property: %d rows", len(legacy))
        return legacy
    except Exception as e:
        logger.warning("Could not read legacy unsold sheet: %s", e)
        return pd.DataFrame()


def transform_newly_launched() -> pd.DataFrame:
    """Transform newly launched residential units from legacy Google Sheet.

    Mirrors R script lines 308-440 (legacy data path only).
    """
    try:
        legacy = read_google_sheet(
            OUTPUT_SHEETS["newly_launched"],
            "Newly launch",
        )
        if not legacy.empty:
            bound_cols = [c for c in legacy.columns if c.endswith("bound")]
            if bound_cols:
                legacy = legacy.drop(columns=bound_cols)
            if "Updated as of" in legacy.columns:
                legacy["Updated as of"] = pd.to_datetime(legacy["Updated as of"], errors="coerce")
            if "Date" in legacy.columns:
                legacy["Date"] = pd.to_datetime(legacy["Date"], errors="coerce")

        logger.info("Newly launched: %d rows", len(legacy))
        return legacy
    except Exception as e:
        logger.warning("Could not read legacy newly launched sheet: %s", e)
        return pd.DataFrame()


def transform() -> dict[str, pd.DataFrame]:
    """Run all property transforms."""
    return {
        "transactions": transform_transactions(),
        "house_prices": transform_house_prices(),
        "unsold": transform_unsold(),
        "newly_launched": transform_newly_launched(),
    }


def load(dfs: dict[str, pd.DataFrame]) -> None:
    """Write property data to Google Sheets."""
    sheet_map = {
        "transactions": ("transactions", "data"),
        "house_prices": ("house_prices", "data"),
        "unsold": ("unsold", "data"),
        "newly_launched": ("newly_launched", "data"),
    }
    for key, (sheet_key, tab) in sheet_map.items():
        if key in dfs and not dfs[key].empty:
            write_sheet(dfs[key], OUTPUT_SHEETS[sheet_key], tab)


def main() -> dict[str, pd.DataFrame]:
    """Run full property pipeline."""
    dfs = transform()
    load(dfs)
    return dfs


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
