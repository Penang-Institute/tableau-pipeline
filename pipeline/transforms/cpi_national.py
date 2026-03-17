"""National CPI (Consumer Price Index) transform.

Fetches national-level CPI data from OpenDOSM, filters to absolute series
and dates from January 2010 onward, formats date as dd/mm/yyyy.

Source: https://storage.dosm.gov.my/cpi/cpi_2d.parquet
Output: Google Drive folder (CPI) + output/cpi_2d.csv
Columns: date, division, index (3 columns)
"""

import logging

import pandas as pd

from pipeline.fetchers.opendosm import fetch_parquet, get_parquet_url
from pipeline.loaders.file_writer import write_csv
from pipeline.loaders.google_sheets import get_drive_folder_id, upload_to_drive

logger = logging.getLogger(__name__)

DATA_START_DATE = "2010-01-01"


def transform() -> pd.DataFrame:
    """Fetch national CPI data, filter to abs series from 2010, format date."""
    url = get_parquet_url("cpi_2d")
    cpi = fetch_parquet(url)

    # Filter to absolute index only (if series column exists)
    if "series" in cpi.columns:
        cpi = cpi[cpi["series"] == "abs"].copy()

    # Filter to data from January 2010 onward
    cpi["date"] = pd.to_datetime(cpi["date"])
    cpi = cpi[cpi["date"] >= DATA_START_DATE].copy()

    # Format date as dd/mm/yyyy per spec
    cpi["date"] = cpi["date"].dt.strftime("%d/%m/%Y")

    # Keep only required columns
    cpi = cpi[["date", "division", "index"]].reset_index(drop=True)

    logger.info("CPI national transform: %d rows", len(cpi))
    return cpi


def load(df: pd.DataFrame) -> None:
    """Write national CPI data to Drive folder and local CSV."""
    csv_path = write_csv(df, "cpi_2d.csv", date_tag=True)
    folder_id = get_drive_folder_id("cpi")
    upload_to_drive(csv_path, folder_id, "cpi_2d.csv", date_tag=True)


def main() -> pd.DataFrame:
    """Run full national CPI pipeline (fetch -> transform -> load)."""
    df = transform()
    load(df)
    return df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
