"""CPI (Consumer Price Index) transform.

Fetches CPI data from OpenDOSM's public parquet file and saves as CSV.
Per the data spec, the raw OpenDOSM format is used directly without
changing any formatting.

Source: https://storage.dosm.gov.my/cpi/cpi_2d_state.parquet
Output: Google Drive folder (CPI) + output/cpi_2d_state.csv
Columns: state, date, division, index (4 columns, raw OpenDOSM)
"""

import logging

import pandas as pd

from pipeline.fetchers.opendosm import fetch_parquet, get_parquet_url
from pipeline.loaders.file_writer import write_csv
from pipeline.loaders.google_sheets import get_drive_folder_id, upload_to_drive

logger = logging.getLogger(__name__)


def transform() -> pd.DataFrame:
    """Fetch CPI data from OpenDOSM. Returns raw 4-column DataFrame."""
    url = get_parquet_url("cpi_2d_state")
    cpi = fetch_parquet(url)

    # Keep only the 4 required columns in raw OpenDOSM format
    cpi = cpi[["state", "date", "division", "index"]]

    logger.info("CPI transform: %d rows (%d states)", len(cpi), cpi["state"].nunique())
    return cpi


def load(df: pd.DataFrame) -> None:
    """Write CPI data to Drive folder and local CSV."""
    csv_path = write_csv(df, "cpi_2d_state.csv", date_tag=True)
    folder_id = get_drive_folder_id("cpi")
    upload_to_drive(csv_path, folder_id, "cpi_2d_state.csv", date_tag=True)


def main() -> pd.DataFrame:
    """Run full CPI pipeline (fetch → transform → load)."""
    df = transform()
    load(df)
    return df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
