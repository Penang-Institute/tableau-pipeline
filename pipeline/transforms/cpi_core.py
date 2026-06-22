"""Core CPI (Consumer Price Index) transform.

Fetches national-level core CPI data from OpenDOSM, filters dates
from January 2018 onward, formats date as dd/mm/yyyy.

Source: https://storage.dosm.gov.my/cpi/cpi_2d_core.parquet
Output: Google Drive folder (CPI) + output/cpi_2d_core.csv
Columns: date, division, index (3 columns)
"""

import logging

import pandas as pd

from pipeline.fetchers.opendosm import fetch_parquet, get_parquet_url
from pipeline.loaders.file_writer import write_csv
from pipeline.loaders.google_sheets import get_drive_folder_id
from pipeline.loaders.drive_merge import append_periods_to_drive_csv

logger = logging.getLogger(__name__)

DATA_START_DATE = "2018-01-01"


def transform() -> pd.DataFrame:
    """Fetch core CPI data, filter dates from 2018, format date."""
    url = get_parquet_url("cpi_2d_core")
    cpi = fetch_parquet(url)

    # Filter to absolute index only (if series column exists)
    if "series" in cpi.columns:
        cpi = cpi[cpi["series"] == "abs"].copy()

    # Filter to data from January 2018 onward
    cpi["date"] = pd.to_datetime(cpi["date"])
    cpi = cpi[cpi["date"] >= DATA_START_DATE].copy()

    # Format date as dd/mm/yyyy per spec
    cpi["date"] = cpi["date"].dt.strftime("%d/%m/%Y")

    # Keep only required columns
    cpi = cpi[["date", "division", "index"]].reset_index(drop=True)

    logger.info("CPI core transform: %d rows", len(cpi))
    return cpi


def load(df: pd.DataFrame) -> None:
    """Write core CPI data to Drive folder and local CSV."""
    write_csv(df, "cpi_2d_core.csv", date_tag=True)  # local dated history
    append_periods_to_drive_csv(df, get_drive_folder_id("cpi"), "cpi_2d_core.csv")


def main() -> pd.DataFrame:
    """Run full core CPI pipeline (fetch -> transform -> load)."""
    df = transform()
    load(df)
    return df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
