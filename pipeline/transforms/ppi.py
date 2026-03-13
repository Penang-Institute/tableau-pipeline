"""PPI (Producer Price Index) transform.

Fetches PPI data from OpenDOSM, filters to 'abs' series only, and
formats date as dd/mm/yyyy per the data spec.

Source: https://storage.dosm.gov.my/ppi/ppi.parquet
Output: Google Drive folder (CPI) + output/ppi.csv
Columns: date, index (2 columns)
"""

import logging

import pandas as pd

from pipeline.fetchers.opendosm import fetch_parquet, get_parquet_url
from pipeline.loaders.file_writer import write_csv
from pipeline.loaders.google_sheets import get_drive_folder_id, upload_to_drive

logger = logging.getLogger(__name__)


def transform() -> pd.DataFrame:
    """Fetch PPI data from OpenDOSM, filter to abs series, format date."""
    url = get_parquet_url("ppi")
    ppi = fetch_parquet(url)

    # Filter to absolute index only (exclude growth_yoy, growth_mom)
    ppi = ppi[ppi["series"] == "abs"].copy()

    # Format date as dd/mm/yyyy per spec
    ppi["date"] = pd.to_datetime(ppi["date"]).dt.strftime("%d/%m/%Y")

    # Keep only required columns
    ppi = ppi[["date", "index"]].reset_index(drop=True)

    logger.info("PPI transform: %d rows", len(ppi))
    return ppi


def load(df: pd.DataFrame) -> None:
    """Write PPI data to Drive folder and local CSV."""
    csv_path = write_csv(df, "ppi.csv", date_tag=True)
    folder_id = get_drive_folder_id("cpi")
    upload_to_drive(csv_path, folder_id, "ppi.csv", date_tag=True)


def main() -> pd.DataFrame:
    """Run full PPI pipeline (fetch → transform → load)."""
    df = transform()
    load(df)
    return df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
