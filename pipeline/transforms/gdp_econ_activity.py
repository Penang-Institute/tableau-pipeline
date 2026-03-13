"""GDP by economic activity transform.

Migrated from: scripts/gdp/prep_gdp_econ_act_fixed.R (257 lines)

Downloads GDP data by state and kind of economic activity from Google Drive,
processes sub-sector aggregations, and writes to Google Sheets.

Sources:
  - Google Drive: 1lJGrKrHihJ_Mr7HRSlG12OwbZ2WxjKCE (state econ activity constant)
  - Google Drive: 1lFgtzcpuTfBzPNvIXJhvN0Qo5kfHckrv (state total GDP constant)
  - Google Drive: 1lMEMR8Z2Y32DBdj89wXUgWKucoqtZNa2 (Malaysia econ activity constant)
  - Google Sheet: 1jSk6_GqU4PawtlE1RtIidSZTH6Fya3eT9bbRJmYu2GQ (historical data)
Output:
  - Google Sheet 1jSk6_GqU4PawtlE1RtIidSZTH6Fya3eT9bbRJmYu2GQ:
    - sheet "data-by_econ_act"
    - sheet "data-by_subecon_act"
"""

from __future__ import annotations

import logging
import re

import pandas as pd

from pipeline.config.registry import get_drive_id, get_sheet_id
from pipeline.fetchers.gdrive import download_excel_from_drive, read_google_sheet
from pipeline.loaders.google_sheets import write_sheet

logger = logging.getLogger(__name__)

DRIVE_IDS = {
    "state_econact": get_drive_id("gdp_econ_activity", "state_econact"),
    "state_total": get_drive_id("gdp_econ_activity", "state_total"),
    "msia_econact": get_drive_id("gdp_econ_activity", "msia_econact"),
}
OUTPUT_SHEET_ID = get_sheet_id("gdp_econ_activity", "output")

ECON_ACTIVITY_FIXES = {
    "Mining and quarrying": "Mining and Quarrying",
    "plus: Import Duties": "Import Duties",
    "Plus: Import duties": "Import Duties",
    "Import duties": "Import Duties",
}

SUB_SECTOR_FIXES = {
    "plus: Import Duties": "Import Duties",
    "Plus: Import duties": "Import Duties",
    "Mining and quarrying": "Mining and Quarrying",
    "Finance and Insurance, Real Estate and Business Services":
        "Finance and insurance, real estate and business services",
    "Utilities, transportation and storage, information and communication":
        "Utilities, transportation & storage and information & communication",
    "Other services": "Other Services",
    "Government services": "Government Services",
}

MALAYSIA_ACTIVITIES = [
    "Agriculture", "Mining and Quarrying", "Construction",
    "Manufacturing", "Services", "Import Duties",
]


def _fix_econ_activity(val: str) -> str:
    """Standardize economic activity names."""
    return ECON_ACTIVITY_FIXES.get(val, val)


def _fix_sub_sector(val: str) -> str:
    """Standardize sub-sector names."""
    return SUB_SECTOR_FIXES.get(val, val)


def _extract_data_status(year_str: str) -> str | None:
    """Extract 'estimate' or 'preliminary' from year suffixes."""
    s = str(year_str)
    if s.endswith("e"):
        return "estimate"
    if s.endswith("p"):
        return "preliminary"
    return None


def transform() -> dict[str, pd.DataFrame]:
    """Fetch and transform GDP by economic activity data.

    Returns dict with keys 'by_econ_act' and 'by_subecon_act'.
    """
    today_year = pd.Timestamp.today().year

    # 1. State economic activity at constant prices
    try:
        state_econact_xls = download_excel_from_drive(DRIVE_IDS["state_econact"])
    except Exception as e:
        logger.warning("Failed to download state econ activity: %s", e)
        return {"by_econ_act": pd.DataFrame(), "by_subecon_act": pd.DataFrame()}
    state_econact_raw = pd.read_excel(state_econact_xls, sheet_name="Dataset")

    state_econ_act = state_econact_raw.copy()
    state_econ_act["Status of data"] = (
        state_econ_act["Year"].astype(str).apply(_extract_data_status)
    )
    state_econ_act["Year"] = (
        state_econ_act["Year"].astype(str).str[:4].astype(int)
    )
    state_econ_act["State"] = (
        state_econ_act["State"].str.replace(r"^W\.P(?!\.)", "W.P.", regex=True)
    )
    state_econ_act["Updated as of"] = today_year

    # Fix activity names
    for col in ["Kind of Economic Activity", "Sub Kind of Economic Activity"]:
        if col in state_econ_act.columns:
            fix_map = ECON_ACTIVITY_FIXES if "Sub" not in col else SUB_SECTOR_FIXES
            state_econ_act[col] = state_econ_act[col].map(
                lambda x, fm=fix_map: fm.get(x, x)
            )

    state_econ_act = state_econ_act.rename(columns={
        "Base Year": "Base year",
        "Kind of Economic Activity": "Economic activity",
        "Sub Kind of Economic Activity": "Sub-sectors",
        "Value RM Million": "GDP (RM mil)",
    })
    state_econ_act = state_econ_act[
        ["Updated as of", "Status of data", "Base year", "Year", "State",
         "Economic activity", "Sub-sectors", "GDP (RM mil)"]
    ]

    # 2. State total GDP at constant prices
    state_total_xls = download_excel_from_drive(DRIVE_IDS["state_total"])
    state_total_raw = pd.read_excel(state_total_xls)

    total_states = state_total_raw.copy()
    total_states["Economic activity"] = "Total"
    total_states["Base year"] = (
        total_states["Base Year"].astype(str).str[:4].astype(float)
    )
    total_states["State"] = total_states["State"].str.replace(
        r"^WP", "W.P.", regex=True
    )
    total_states["Updated as of"] = today_year
    total_states["Year"] = pd.to_numeric(total_states["Year"], errors="coerce")
    total_states = total_states.rename(columns={"Value RM Million": "GDP (RM mil)"})
    total_states = total_states.drop(columns=["Base Year"], errors="ignore")

    # 3. Historical data from Google Sheet (for base year < 2015 / base year 2000)
    try:
        historical = read_google_sheet(OUTPUT_SHEET_ID, "Data-byEconAct")
        historical = historical[
            ((historical["Base year"].astype(float) < 2015) &
             (historical["State"] == "Malaysia")) |
            (historical["Base year"].astype(float) == 2000)
        ]
        # Standardize names
        historical["Economic activity"] = (
            historical["Economic activity"].apply(_fix_econ_activity)
        )
        historical = historical[
            ["State", "Year", "Base year", "Economic activity",
             "GDP (RM mil)", "Updated as of"]
        ]
    except Exception as e:
        logger.warning("Could not read historical data: %s", e)
        historical = pd.DataFrame()

    # 4. Malaysia GDP by economic activity at constant prices
    msia_xls = download_excel_from_drive(DRIVE_IDS["msia_econact"])
    sheet_names = msia_xls.sheet_names
    data_sheets = [s for s in sheet_names if "metadata" not in s.lower()]

    msia_frames = []
    for sheet in data_sheets:
        try:
            df = pd.read_excel(msia_xls, sheet_name=sheet, na_values="n.a",
                               usecols="A:F")
            msia_frames.append(df)
        except Exception as e:
            logger.warning("Failed to read Malaysia econact sheet %s: %s", sheet, e)
            continue

    if msia_frames:
        msia_combined = pd.concat(msia_frames, ignore_index=True)
    else:
        msia_combined = pd.DataFrame()

    if not msia_combined.empty:
        # Fix activity names
        activity_col = [c for c in msia_combined.columns
                        if "economic activity" in c.lower()]
        if activity_col:
            act_col = activity_col[0]
            msia_combined[act_col] = msia_combined[act_col].apply(
                lambda x: "Mining and Quarrying"
                if x == "Mining and quarrying" else
                ("Import Duties" if isinstance(x, str) and "Import" in x else x)
            )
            msia_combined = msia_combined[
                msia_combined[act_col].isin(MALAYSIA_ACTIVITIES)
            ]

        # Rename columns
        col_map = {}
        for c in msia_combined.columns:
            if "Year" in c and "Base" not in c:
                col_map[c] = "Year"
            elif "Base" in c:
                col_map[c] = "Base year"
            elif "Value" in c:
                col_map[c] = "GDP (RM mil)"
            elif "economic" in c.lower():
                col_map[c] = "Economic activity"
        msia_combined = msia_combined.rename(columns=col_map)

        for c in ["Year", "Base year"]:
            if c in msia_combined.columns:
                msia_combined[c] = pd.to_numeric(
                    msia_combined[c], errors="coerce"
                )

        msia_combined["State"] = "Malaysia"
        msia_combined["Updated as of"] = today_year

        gdp_msia = (
            msia_combined
            .groupby(["State", "Year", "Base year", "Economic activity",
                       "Updated as of"], dropna=False)
            .agg({"GDP (RM mil)": "sum"})
            .reset_index()
        )
    else:
        gdp_msia = pd.DataFrame()

    # 5. Build aggregated economic activity output
    # Recapitalize for matching
    recapped = state_econ_act.copy()
    for col in ["Economic activity", "Sub-sectors"]:
        recapped[col] = recapped[col].str.capitalize()

    # Identify activities with summation records
    with_sums = recapped[
        (recapped["Economic activity"] == recapped["Sub-sectors"]) |
        (recapped["Economic activity"] == "Import duties")
    ][["Year", "Base year", "State", "Economic activity"]].drop_duplicates()

    # Activities without sums: calculate from sub-sectors
    all_combos = recapped[
        ["Year", "Base year", "State", "Economic activity"]
    ].drop_duplicates()
    without_sums = pd.merge(
        all_combos, with_sums, how="left", indicator=True
    )
    without_sums = without_sums[without_sums["_merge"] == "left_only"].drop(
        columns=["_merge"]
    )

    gdp_unsummed = (
        recapped.merge(without_sums, on=["Year", "Base year", "State",
                                          "Economic activity"])
        .groupby(["Year", "Base year", "State", "Economic activity"])
        .agg({"GDP (RM mil)": "sum"})
        .reset_index()
    )
    gdp_unsummed["Status of data"] = "calculated"

    # Get records with direct sums
    direct_sums = recapped[
        (recapped["Economic activity"] == recapped["Sub-sectors"]) |
        recapped["Economic activity"].isin(
            ["Agriculture", "Mining and quarrying", "Import duties"]
        )
    ].drop(columns=["Sub-sectors"], errors="ignore")

    # Combine all: direct sums + calculated sums + Malaysia + totals
    parts = [direct_sums, gdp_unsummed]
    if not gdp_msia.empty:
        parts.append(gdp_msia)
    parts.append(total_states)

    by_econ_act = pd.concat(parts, ignore_index=True)
    by_econ_act = by_econ_act.sort_values(
        ["Year", "Base year", "State", "Economic activity"]
    )

    # 6. Build sub-sector output
    by_subecon_act = state_econ_act.copy()
    # Fix names back
    by_subecon_act["Economic activity"] = (
        by_subecon_act["Economic activity"].apply(_fix_econ_activity)
    )
    # Filter: for year >= 2015, exclude rows where activity == sub-sector
    # (except Agriculture, Mining and Quarrying, Import Duties)
    exempt = ["Agriculture", "Mining and Quarrying", "Import Duties"]
    mask = (
        (by_subecon_act["Year"] < 2015) |
        (by_subecon_act["Economic activity"] != by_subecon_act["Sub-sectors"]) |
        by_subecon_act["Economic activity"].isin(exempt)
    )
    by_subecon_act = by_subecon_act[mask]

    logger.info(
        "GDP econ activity transform: %d by_econ_act, %d by_subecon_act",
        len(by_econ_act), len(by_subecon_act),
    )
    return {"by_econ_act": by_econ_act, "by_subecon_act": by_subecon_act}


def load(dfs: dict[str, pd.DataFrame]) -> None:
    """Write GDP economic activity data to Google Sheets."""
    if not dfs["by_econ_act"].empty:
        write_sheet(dfs["by_econ_act"], OUTPUT_SHEET_ID, "data-by_econ_act")
    if not dfs["by_subecon_act"].empty:
        write_sheet(dfs["by_subecon_act"], OUTPUT_SHEET_ID, "data-by_subecon_act")


def main() -> dict[str, pd.DataFrame]:
    """Run full GDP economic activity pipeline."""
    dfs = transform()
    load(dfs)
    return dfs


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
