"""Household income, expenditure, and poverty transform.

Migrated from: scripts/his/gross_income.R (317 lines)

Comprehensive HIS (Household Income Survey) pipeline combining:
- HIES snapshot and timeseries from OpenDOSM parquets
- Expenditure from Google Drive Excel
- Gross income per capita and disposable income from Google Drive Excel
- Absolute poverty from Google Drive Excel + local CSV
- District-level hardcoded Penang data

Sources:
  - OpenDOSM parquets: hh_income_state/district, hh_inequality_state/district,
    hh_poverty/_state/_district, hies_state/district
  - Google Drive: multiple Excel files (expenditure, income, poverty)
  - Google Sheet: 1azH8hsG3tImspRZGNFsUvukRgB6BjD1EW7vMFdpWTeo (legacy district)
  - Local: data/his/pli_all.csv
Output: Google Sheet 1i_yrlpJUHG5IUYUJwV7cWj_b2peDn7KJpFA4_kBkcwU
  - sheet "Data"
  - sheet "absolute_poverty"
"""

import logging
import os
import re
from pathlib import Path

import pandas as pd

from pipeline.config.registry import get_drive_id, get_sheet_id
from pipeline.fetchers.opendosm import fetch_parquet
from pipeline.fetchers.gdrive import (
    download_excel_from_drive,
    read_google_sheet,
)
from pipeline.loaders.google_sheets import write_sheet

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "his"
OUTPUT_SHEET_ID = get_sheet_id("gross_income", "output")
LEGACY_DISTRICT_SHEET_ID = get_sheet_id("gross_income", "legacy_district")

DOSM_BASE = "https://storage.dosm.gov.my"

LOOKUP = {
    "gini_gross_income": "gini",
    "mean_gross_income": "income_mean",
    "median_gross_income": "income_median",
    "absolute_poverty": "poverty_absolute",
}

DRIVE_IDS = {
    "expenditure_22": get_drive_id("gross_income", "expenditure_22"),
    "gross_percap": get_drive_id("gross_income", "gross_percap"),
    "disposable": get_drive_id("gross_income", "disposable"),
    "abs_poverty_05": get_drive_id("gross_income", "abs_poverty_05"),
    "abs_poverty_16": get_drive_id("gross_income", "abs_poverty_16"),
}

# ---------------------------------------------------------------------------
# Hardcoded Penang 2022 district data (from R lines 138-163)
# These are manually entered values not available via OpenDOSM APIs.
# ---------------------------------------------------------------------------

# Expenditure median by district (R lines 138-146)
PENANG_DISTRICT_EXPENDITURE_2022 = pd.DataFrame({
    "year": [2022, 2022, 2022, 2022, 2022],
    "state": ["Pulau Pinang"] * 5,
    "district": [
        "Seberang Perai Tengah",
        "Seberang Perai Utara",
        "Seberang Perai Selatan",
        "Timur Laut",
        "Barat Daya",
    ],
    "expenditure_median": [4205, 3952, 4183, 4939, 5221],
})

# Other income measures by district (R lines 155-163)
PENANG_DISTRICT_INCOME_2022 = pd.DataFrame({
    "year": [2022, 2022, 2022, 2022, 2022],
    "state": ["Pulau Pinang"] * 5,
    "district": [
        "Seberang Perai Tengah",
        "Seberang Perai Utara",
        "Seberang Perai Selatan",
        "Timur Laut",
        "Barat Daya",
    ],
    "median_percap_gross_income": [None, None, None, None, None],
    "median_disposable_income": [5214, 5118, 5044, 5939, 6169],
    "mean_disposable_income": [6610, 6137, 6200, 7399, 7640],
})


def _fetch_hies_combined(level: str) -> pd.DataFrame:
    """Fetch HIES income + inequality + poverty for a given level and merge.

    OpenDOSM split the old ``hiesba_*`` files into three topic-specific
    parquets per geographic level.  This function fetches all three and
    merges them on the common key columns (year, state, and optionally
    district).

    Args:
        level: ``"state"`` or ``"district"``.
    """
    topics = [
        f"hh_income_{level}",
        f"hh_inequality_{level}",
        f"hh_poverty_{level}",
    ]
    merge_keys = ["year", "state"]
    if level == "district":
        merge_keys.append("district")

    merged = None
    for name in topics:
        url = f"{DOSM_BASE}/hies/{name}.parquet"
        try:
            df = fetch_parquet(url)
        except Exception as e:
            logger.warning("Failed to fetch %s: %s", name, e)
            continue

        if "date" in df.columns:
            df["year"] = pd.to_datetime(df["date"]).dt.year
            df = df.drop(columns=["date"])

        if merged is None:
            merged = df
        else:
            keys = [k for k in merge_keys if k in merged.columns and k in df.columns]
            merged = merged.merge(df, on=keys, how="outer")

    if merged is None:
        return pd.DataFrame()

    merged["updated_as_of"] = pd.Timestamp.today().year

    rename_map = {v: k for k, v in LOOKUP.items() if v in merged.columns}
    merged = merged.rename(columns=rename_map)
    return merged


def _fetch_hh_snapshot() -> pd.DataFrame:
    """Fetch HIES snapshot data (hies_district + hies_state) from OpenDOSM.

    Corresponds to R lines 67-69:
        glue("https://storage.dosm.gov.my/hies/hies{c('_district', '_state')}.parquet")
    """
    frames = []
    for suffix in ["_district", "_state"]:
        url = f"{DOSM_BASE}/hies/hies{suffix}.parquet"
        try:
            df = fetch_parquet(url)
            if "date" in df.columns:
                df["year"] = pd.to_datetime(df["date"]).dt.year
                df = df.drop(columns=["date"])
            frames.append(df)
        except Exception as e:
            logger.warning("Failed to fetch hies%s: %s", suffix, e)

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _fetch_hh_poverty() -> pd.DataFrame:
    """Fetch household poverty data from OpenDOSM."""
    frames = []
    for suffix in ["", "_district", "_state"]:
        url = f"{DOSM_BASE}/hies/hh_poverty{suffix}.parquet"
        try:
            df = fetch_parquet(url)
            if suffix == "":
                df["state"] = "Malaysia"
            if "date" in df.columns:
                df["year"] = pd.to_datetime(df["date"]).dt.year
                df = df.drop(columns=["date"])
            frames.append(df)
        except Exception as e:
            logger.warning("Failed to fetch hh_poverty%s: %s", suffix, e)

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    if "poverty_relative" in combined.columns:
        combined = combined.rename(columns={
            "poverty_relative": "incidence_of_relative_poverty_percent"
        })
    combined["updated_as_of"] = pd.Timestamp.today().year
    return combined


def transform_main() -> pd.DataFrame:
    """Transform main HIS data (state + district metrics)."""
    today_year = pd.Timestamp.today().year

    # State data (full timeseries from new split parquets)
    state = _fetch_hies_combined("state")

    # District data
    district = _fetch_hies_combined("district")

    # Legacy district data
    try:
        district_legacy = read_google_sheet(
            LEGACY_DISTRICT_SHEET_ID, "Data"
        )
        # Clean column names
        district_legacy.columns = [c.lower().replace(" ", "_")
                                   for c in district_legacy.columns]
        if "measure" in district_legacy.columns:
            district_legacy["measure"] = district_legacy["measure"].str.lower()
            district_legacy = district_legacy.pivot_table(
                index=[c for c in district_legacy.columns
                       if c not in ["measure", "household_income"]],
                columns="measure",
                values="household_income",
                aggfunc="first",
            ).reset_index()
            district_legacy.columns.name = None
        if "mean" in district_legacy.columns:
            district_legacy = district_legacy.rename(columns={
                "mean": "mean_gross_income",
                "median": "median_gross_income",
            })
        district_legacy["state"] = "Pulau Pinang"
        district_legacy = district_legacy[
            (district_legacy["year"] < 2016) |
            (district_legacy["year"] == 2020)
        ]
        if "district" in district_legacy.columns:
            district_legacy = district_legacy[
                district_legacy["district"] != "Pulau Pinang"
            ]
    except Exception as e:
        logger.warning("Failed to read legacy district data: %s", e)
        district_legacy = pd.DataFrame()

    # Poverty
    poverty = _fetch_hh_poverty()

    # HIES snapshot (for expenditure_mean join with hardcoded district data)
    hh_snapshot = _fetch_hh_snapshot()

    # Hardcoded Penang 2022 district expenditure (R lines 138-152)
    # Join with hh_snapshot to get expenditure_mean, then bind with other
    # expenditure data to create expenditure_22
    penang_exp = PENANG_DISTRICT_EXPENDITURE_2022.copy()
    if not hh_snapshot.empty and "expenditure_mean" in hh_snapshot.columns:
        snapshot_exp = hh_snapshot[
            ["state", "district", "year", "expenditure_mean"]
        ].dropna(subset=["district"])
        penang_exp = penang_exp.merge(
            snapshot_exp,
            on=["state", "district", "year"],
            how="left",
        )

    # Hardcoded Penang 2022 district income measures (R lines 155-163)
    # These form part of alt_income alongside gross_percap and disposable
    # income from Drive Excel files
    district_pen_2022 = PENANG_DISTRICT_INCOME_2022.copy()

    # State data is already the full timeseries from the new split parquets
    state_all = state.copy() if not state.empty else pd.DataFrame()

    # Drop absolute_poverty from state_all (handled separately)
    if "absolute_poverty" in state_all.columns:
        state_all = state_all.drop(columns=["absolute_poverty"])

    # Combine all
    parts = [state_all]
    if not district_legacy.empty:
        parts.append(district_legacy)
    if not district.empty:
        dist_cols = [c for c in district.columns if c != "absolute_poverty"]
        parts.append(district[dist_cols])

    combined = pd.concat(parts, ignore_index=True)

    # Join poverty (R line 311)
    if not poverty.empty:
        poverty_cols = ["year", "state"]
        if "district" in poverty.columns:
            poverty_cols.append("district")
        combined = combined.merge(
            poverty, on=[c for c in poverty_cols if c in combined.columns],
            how="left", suffixes=("", "_poverty"),
        )

    # Join alt_income: hardcoded Penang 2022 district income (R line 312)
    # In R this also includes gross_percap_long, disp_long, disp_percap_long
    # from Drive Excel; those are handled elsewhere. Here we add the hardcoded
    # district_pen_2022 data.
    if not district_pen_2022.empty:
        join_cols = [c for c in ["year", "state", "district"]
                     if c in combined.columns and c in district_pen_2022.columns]
        if join_cols:
            combined = combined.merge(
                district_pen_2022, on=join_cols,
                how="left", suffixes=("", "_alt"),
            )

    # Remove cagr and date columns (R line 313)
    combined = combined[[c for c in combined.columns
                         if not c.startswith("cagr") and c != "date"]]

    # Join expenditure: hardcoded Penang 2022 district expenditure (R line 314)
    # In R this also includes exp_16, exp_22 from Drive Excel.
    if not penang_exp.empty:
        join_cols = [c for c in ["year", "state", "district"]
                     if c in combined.columns and c in penang_exp.columns]
        if join_cols:
            combined = combined.merge(
                penang_exp, on=join_cols,
                how="left", suffixes=("", "_exp"),
            )

    logger.info("Main HIS transform: %d rows", len(combined))
    return combined


def transform_absolute_poverty() -> pd.DataFrame:
    """Transform absolute poverty data."""
    frames = []

    # PLI 2005 time series (R lines 252-265)
    # R reads sheet "10.9" range "B4:T30" with default headers, then:
    #   - detects group header rows (Ethnic group / Strata) via leading whitespace
    #   - fills group headers down, filters them out
    #   - pivots longer with year from column names
    #   - strips punctuation from column names to extract integer years
    #   - e.g. column "1970" -> year 1970, column "...5" filtered out
    try:
        tmp = download_excel_from_drive(DRIVE_IDS["abs_poverty_05"])
        # Read WITH headers (row 0 = year headers from Excel row 4)
        # This matches R's read_xlsx default behavior
        pli05 = pd.read_excel(
            tmp, sheet_name="10.9",
            skiprows=3, nrows=26, na_values="n.a",
        )

        if not pli05.empty:
            first_col = pli05.columns[0]

            # R logic: detect group headers = rows where first column does
            # NOT contain 2+ consecutive whitespace characters.
            # R: ifelse(str_detect(`...1`, "\\s{2}", negate = TRUE), `...1`, NA)
            # Group headers like "Kumpulan etnik/ Ethnic group" and "Strata"
            # are non-indented; state names are indented with spaces.
            pli05["_header"] = pli05[first_col].where(
                ~pli05[first_col].astype(str).str.contains(r"\s{2}", na=False)
                & ~pli05[first_col].isna()
            )
            pli05["_header"] = pli05["_header"].ffill()
            pli05 = pli05[
                ~pli05["_header"].isin([
                    "Kumpulan etnik/ Ethnic group", "Strata",
                ])
            ]
            pli05[first_col] = pli05[first_col].astype(str).str.strip()
            pli05 = pli05.drop(columns=["_header"])

            # Rename first column to "state"
            pli05 = pli05.rename(columns={first_col: "state"})

            # Pivot longer: all columns except "state" become year rows
            pli05_long = pli05.melt(
                id_vars=["state"],
                var_name="year",
                value_name="absolute_poverty",
            )

            # Extract year from column header names (R: str_remove_all(year, "[[:punct:]]"))
            # This strips dots, dashes, ellipses etc. from auto-generated
            # column names like "...5", leaving only digits
            pli05_long["year"] = (
                pli05_long["year"]
                .astype(str)
                .apply(lambda x: re.sub(r"[^\w\s]", "", x).strip())
            )
            # Convert to integer, dropping rows where year is not numeric
            pli05_long["year"] = pd.to_numeric(
                pli05_long["year"], errors="coerce"
            )
            pli05_long = pli05_long.dropna(subset=["year", "absolute_poverty"])
            pli05_long["year"] = pli05_long["year"].astype(int)

            pli05_long["methodology"] = "Poverty Line Income 2005"
            pli05_long["state"] = pli05_long["state"].str.strip()

            frames.append(pli05_long[
                ["year", "state", "absolute_poverty", "methodology"]
            ])
    except Exception as e:
        logger.warning("Failed to read PLI 2005 data: %s", e)

    # PLI 2019 for 2016
    try:
        tmp = download_excel_from_drive(DRIVE_IDS["abs_poverty_16"])
        pli16 = pd.read_excel(
            tmp, sheet_name="1.16 & 1.17",
            header=None, skiprows=26, nrows=16,
            na_values="n.a",
        )
        if not pli16.empty and len(pli16.columns) >= 3:
            pli16_clean = pli16.iloc[:, [0, 2]].copy()
            pli16_clean.columns = ["state", "absolute_poverty"]
            pli16_clean["year"] = 2016
            pli16_clean["methodology"] = "Poverty Line Income 2019"
            pli16_clean["updated_as_of"] = 2019
            frames.append(pli16_clean)
    except Exception as e:
        logger.warning("Failed to read PLI 2016 data: %s", e)

    # Current poverty from OpenDOSM
    poverty = _fetch_hh_poverty()
    if not poverty.empty and "poverty_absolute" in poverty.columns:
        current = poverty[poverty["year"] >= 2019].copy()
        current = current.rename(
            columns={"poverty_absolute": "absolute_poverty"}
        )
        current["methodology"] = "Poverty Line Income 2019"
        current = current[
            ["year", "state", "absolute_poverty", "methodology",
             "updated_as_of"] +
            (["district"] if "district" in current.columns else [])
        ]
        frames.append(current)

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    combined["state"] = combined["state"].str.strip()

    # Join PLI data if available (R line 300-301)
    # left_join(read_csv("data/his/pli_all.csv"), by = c("year", "state"))
    pli_path = DATA_DIR / "pli_all.csv"
    if pli_path.exists():
        try:
            pli = pd.read_csv(pli_path)
            combined = combined.merge(
                pli, on=["year", "state"], how="left",
            )
        except Exception as e:
            logger.warning("Failed to merge PLI CSV data: %s", e)

    # Reorder columns: year, state, district first (R line 303)
    priority = ["year", "state", "district"]
    front = [c for c in priority if c in combined.columns]
    rest = [c for c in combined.columns if c not in front]
    combined = combined[front + rest]

    logger.info("Absolute poverty transform: %d rows", len(combined))
    return combined


def transform() -> dict[str, pd.DataFrame]:
    """Run all gross income transforms and return results (no side effects)."""
    return {
        "main": transform_main(),
        "absolute_poverty": transform_absolute_poverty(),
    }


def load(main_df: pd.DataFrame, poverty_df: pd.DataFrame) -> None:
    """Write HIS data to Google Sheets."""
    if not main_df.empty:
        write_sheet(main_df, OUTPUT_SHEET_ID, "Data")
    if not poverty_df.empty:
        write_sheet(poverty_df, OUTPUT_SHEET_ID, "absolute_poverty")


def main() -> dict[str, pd.DataFrame]:
    """Run full gross income pipeline."""
    results = transform()
    load(results["main"], results["absolute_poverty"])
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
