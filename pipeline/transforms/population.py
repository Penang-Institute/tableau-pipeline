"""Population by state transform.

Migrated from: scripts/population/pop_by_all_state.R (45 lines)

Combines historical population data (Excel files from Google Drive) with
current OpenDOSM parquet data. Historical data covers pre-2020; OpenDOSM
covers 2020 onward.

Sources:
  - Google Drive folder with .xlsx files (historical, pre-2020)
  - https://storage.dosm.gov.my/population/population_state.parquet (current)
Output: Google Sheet "population_by_state"
"""

from __future__ import annotations

import logging
import re
import tempfile
from pathlib import Path

import pandas as pd

from pipeline.fetchers.opendosm import fetch_parquet, get_parquet_url
from pipeline.loaders.google_sheets import write_to_main_workbook

logger = logging.getLogger(__name__)


def _process_xlsx(path: Path) -> pd.DataFrame:
    """Process a single historical population Excel file.

    Mirrors the R process_xlsx() function:
      - Finds the non-metadata sheet
      - Reads it with "-" as NA
      - Cleans column names to snake_case
    """
    sheets = pd.ExcelFile(path).sheet_names
    data_sheets = [s for s in sheets if "metadata" not in s.lower()]
    if len(data_sheets) != 1:
        raise ValueError(f"Expected 1 data sheet in {path.name}, got {len(data_sheets)}")

    df = pd.read_excel(path, sheet_name=data_sheets[0], na_values=["-"])
    # Clean column names: lowercase, replace spaces/special chars with underscore
    df.columns = [
        re.sub(r"[^a-z0-9]+", "_", col.lower()).strip("_")
        for col in df.columns
    ]
    return df


def transform_historical(excel_dir: Path) -> pd.DataFrame:
    """Process historical population data from Excel files.

    Args:
        excel_dir: Directory containing downloaded .xlsx files.
    """
    xlsx_files = sorted(excel_dir.glob("*.xlsx"))
    if not xlsx_files:
        logger.warning("No Excel files found in %s", excel_dir)
        return pd.DataFrame(columns=["state", "year", "population"])

    frames = [_process_xlsx(f) for f in xlsx_files]
    combined = pd.concat(frames, ignore_index=True)

    # Filter to totals only (matches R: if_all(c(sex, age_group, ethnic_group), ~ str_detect(., "Total")))
    for col in ["sex", "age_group", "ethnic_group"]:
        if col in combined.columns:
            combined = combined[combined[col].astype(str).str.contains("Total", case=False, na=False)]

    result = combined[["state", "year", "value_000_person"]].rename(
        columns={"value_000_person": "population"}
    )
    return result


def transform_current() -> pd.DataFrame:
    """Fetch current population data from OpenDOSM parquet."""
    url = get_parquet_url("population_state")
    df = fetch_parquet(url)

    # Filter to overall totals (matches R filter)
    mask = (
        (df["sex"] == "both")
        & (df["age"] == "overall")
        & (df["ethnicity"] == "overall")
    )
    filtered = df[mask].copy()
    filtered["year"] = pd.to_datetime(filtered["date"]).dt.year
    return filtered[["state", "year", "population"]]


def transform(excel_dir: Path | None = None) -> pd.DataFrame:
    """Combine historical and current population data.

    If excel_dir is None, only current OpenDOSM data is used.
    """
    current = transform_current()

    if excel_dir is not None:
        historical = transform_historical(excel_dir)
        # Historical covers pre-2020, current covers 2020+
        historical = historical[historical["year"] < 2020]
        combined = pd.concat([historical, current], ignore_index=True)
    else:
        combined = current

    # Clean state names: remove "W.P." prefix (matches R: str_remove(state, "W\\..*P\\..*\\s*"))
    combined["state"] = combined["state"].str.replace(
        r"W\.?P\.?\s*", "", regex=True
    )

    combined = combined.sort_values(["state", "year"]).reset_index(drop=True)
    logger.info("Population transform: %d rows", len(combined))
    return combined


def load(df: pd.DataFrame) -> None:
    """Write population data to Google Sheets."""
    write_to_main_workbook(df, "population_by_state")


def main(excel_dir: Path | None = None) -> pd.DataFrame:
    """Run full population pipeline."""
    df = transform(excel_dir)
    load(df)
    return df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
