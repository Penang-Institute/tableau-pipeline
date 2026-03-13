"""GDP per capita by state transform.

Migrated from: scripts/gdp/prep_gdp_capita_states_fixed.R (65 lines)

Downloads GDP per capita data from Google Drive Excel files, joins state
and Malaysia data, and writes to Google Sheets.

Sources:
  - Google Drive: 1lG6J8-bBxGYeD-pne_7CivjHW0phvxdd (state GDP per capita)
  - Google Drive: 1lL-DXiVODFquAj373iu2t70iKpJCeIzA (Malaysia GDP per capita)
Output: Google Sheet 1Ua9_28dpHeWlea9QfbkYrGSSuBtwL2pXOWobpX8A_1Q, sheet "data"
"""

import logging

import pandas as pd

from pipeline.config.registry import get_drive_id, get_sheet_id
from pipeline.fetchers.gdrive import download_excel_from_drive
from pipeline.loaders.google_sheets import write_sheet

logger = logging.getLogger(__name__)

DRIVE_IDS = {
    "state": get_drive_id("gdp_capita_states", "state"),
    "malaysia": get_drive_id("gdp_capita_states", "malaysia"),
}
OUTPUT_SHEET_ID = get_sheet_id("gdp_capita_states", "output")


def transform() -> pd.DataFrame:
    """Fetch and transform GDP per capita data."""
    # Download state GDP per capita
    try:
        state_xls = download_excel_from_drive(DRIVE_IDS["state"])
    except Exception as e:
        logger.warning("Failed to download state GDP per capita: %s", e)
        return pd.DataFrame()
    state_df = pd.read_excel(state_xls, sheet_name="dataset")

    # Download Malaysia GDP per capita
    msia_xls = download_excel_from_drive(DRIVE_IDS["malaysia"])
    msia_df = pd.read_excel(msia_xls, sheet_name="dataset", na_values="..")
    msia_df = msia_df[["Year", "GDP per capita (RM)"]].rename(
        columns={"GDP per capita (RM)": "GDP per capita (Malaysia)"}
    )

    # Save original Year strings BEFORE converting to int
    state_year_str = state_df["Year"].astype(str).str.strip()
    msia_year_str = msia_df["Year"].astype(str).str.strip()

    # Extract data status from original state Year strings (e.g. "2022e", "2023p")
    state_df["Data status"] = state_year_str.apply(
        lambda x: "estimate" if x.endswith("e")
        else ("preliminary" if x.endswith("p") else None)
    )

    # Convert Year to int for both DataFrames
    state_df["Year"] = state_year_str.str[:4].astype(int)
    msia_df["Year"] = msia_year_str.str[:4].astype(int)

    # Join state with Malaysia
    merged = state_df.merge(msia_df, on="Year", how="left")

    merged["Updated as of"] = pd.Timestamp.today().year

    # Filter out header rows
    merged = merged[merged["State"] != "GDP Per Capita at Current Prices"]

    # Keep latest base year per Year-State
    merged["Base Year"] = pd.to_numeric(merged["Base Year"], errors="coerce")
    merged = (
        merged.sort_values("Base Year", ascending=False)
        .groupby(["Year", "State"])
        .first()
        .reset_index()
    )

    result = merged[
        ["State", "Year", "Value RM Million", "GDP per capita (Malaysia)",
         "Data status", "Updated as of"]
    ].rename(columns={"Value RM Million": "GDP per capita (RM)"})

    logger.info("GDP per capita states transform: %d rows", len(result))
    return result


def load(df: pd.DataFrame) -> None:
    """Write GDP per capita data to Google Sheets."""
    write_sheet(df, OUTPUT_SHEET_ID, "data")


def main() -> pd.DataFrame:
    """Run full GDP per capita pipeline."""
    df = transform()
    load(df)
    return df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
