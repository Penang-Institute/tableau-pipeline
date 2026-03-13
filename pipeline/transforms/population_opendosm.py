"""Population by state, age, sex, and ethnicity from OpenDOSM.

Migrated from: scripts/population/prep_pop_opendosm.R (287 lines)

Combines OpenDOSM population parquets (state + Malaysia + district) with
legacy Tableau CSVs. Produces multiple outputs for Tableau dashboards.

Sources:
  - OpenDOSM parquets: population_state, population_malaysia, population_district
  - Local CSV: data/population/ (various legacy Tableau exports)
Output:
  - Google Drive file: 1BMxNmnlH7lhNn2T2gK3QEpxySXn3uQMF (state by age/sex/ethnicity)
  - Google Sheet: 1iKZnD78AubC--HFKiBsSFSCxQB7l2M15SbNsQW22hUw (multiple tabs)
"""

import logging
from pathlib import Path

import pandas as pd

from pipeline.config.registry import get_drive_id, get_sheet_id
from pipeline.fetchers.opendosm import fetch_parquet
from pipeline.loaders.google_sheets import write_sheet, upload_to_drive
from pipeline.loaders.file_writer import write_csv
from pipeline.utils.opendosm_helpers import (
    clean_opendosm as _clean_opendosm,
    recode_ethnicity_for_district,
)

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "population"
DOSM_BASE = "https://storage.dosm.gov.my/population"

OUTPUT_SHEET_ID = get_sheet_id("population_opendosm", "output")
DRIVE_FILE_ID = get_drive_id("population_opendosm", "state_csv")


def transform_state() -> pd.DataFrame:
    """Transform population by state from OpenDOSM."""
    try:
        pop_state = fetch_parquet(f"{DOSM_BASE}/population_state.parquet")
    except Exception as e:
        logger.warning("Failed to fetch population_state: %s", e)
        return pd.DataFrame()

    cleaned = _clean_opendosm(pop_state)

    logger.info("Population state transform: %d rows", len(cleaned))
    return cleaned


def transform_malaysia() -> pd.DataFrame:
    """Transform Malaysia-level population from OpenDOSM + legacy CSV."""
    try:
        pop_msia = fetch_parquet(f"{DOSM_BASE}/population_malaysia.parquet")
    except Exception as e:
        logger.warning("Failed to fetch population_malaysia: %s", e)
        return pd.DataFrame()

    cleaned = _clean_opendosm(pop_msia)

    # Legacy data (pre-2020)
    legacy_file = DATA_DIR / "by sex, age & ethnic (Population_byAgeEthnicGender_MAS.xlsx)_by sex, age & ethnic.csv"
    if legacy_file.exists():
        try:
            legacy = pd.read_csv(legacy_file)
            if "Year" in legacy.columns:
                legacy["Year"] = pd.to_datetime(legacy["Year"], dayfirst=True, errors="coerce").dt.year
            if "Status" in legacy.columns:
                legacy = legacy[legacy["Status"].isna() | (legacy["Status"] != "forecast")]
                legacy["Status"] = legacy["Status"].replace("confirmed", None)
            if "Population" in legacy.columns:
                legacy = legacy.rename(columns={"Population": "Population ('000)"})
                legacy["Population ('000)"] = legacy["Population ('000)"] / 1000
            if "Age" in legacy.columns:
                legacy["Age"] = legacy["Age"].str.replace(r"\s+", "", regex=True)
            legacy = legacy[legacy["Year"] < 2020]
            cleaned = pd.concat([cleaned, legacy], ignore_index=True)
        except Exception as e:
            logger.warning("Failed to read Malaysia legacy CSV: %s", e)

    logger.info("Population Malaysia transform: %d rows", len(cleaned))
    return cleaned


def transform_district() -> dict[str, pd.DataFrame]:
    """Transform district-level population for Penang (ethnicity + sex).

    Returns dict with keys 'district_ethnicity' and 'district_sex'.
    """
    try:
        pop_district = fetch_parquet(f"{DOSM_BASE}/population_district.parquet")
        pop_state = fetch_parquet(f"{DOSM_BASE}/population_state.parquet")
    except Exception as e:
        logger.warning("Failed to fetch population district/state: %s", e)
        return {"district_ethnicity": pd.DataFrame(), "district_sex": pd.DataFrame()}

    district_cleaned = _clean_opendosm(pop_district)
    state_cleaned = _clean_opendosm(pop_state)

    # --- District by Ethnicity ---
    district_ethnic = district_cleaned[
        (district_cleaned["Age"].isin(["overall", "Total", "overall_age"])) &
        (district_cleaned["Gender"].isin(["Overall", "Total"])) &
        (district_cleaned["Ethnic"] != "Total") &
        (district_cleaned.get("state", "") == "Pulau Pinang")
    ].copy()

    if "district" in district_ethnic.columns:
        district_ethnic = district_ethnic.rename(columns={"district": "District"})
    district_ethnic = district_ethnic.drop(
        columns=[c for c in ["state", "Age", "Gender"] if c in district_ethnic.columns],
        errors="ignore",
    )
    district_ethnic["Ethnic"] = district_ethnic["Ethnic"].apply(recode_ethnicity_for_district)

    # Legacy Tableau district ethnicity
    legacy_ethnic_file = DATA_DIR / "byDistrict&Ethnic (3 - Annual_population_byDistrictEthnic_PEN.xlsx)_byDistrict&Ethnic.csv"
    if legacy_ethnic_file.exists():
        try:
            legacy = pd.read_csv(legacy_ethnic_file)
            if "Population" in legacy.columns:
                legacy = legacy.drop(columns=["Population"])
            if "Year" in legacy.columns:
                legacy["Year"] = pd.to_datetime(legacy["Year"], dayfirst=True, errors="coerce").dt.year
                legacy = legacy[legacy["Year"] != 2020]
            district_ethnic = pd.concat([district_ethnic, legacy], ignore_index=True)
        except Exception as e:
            logger.warning("Failed to read legacy district ethnicity: %s", e)

    # --- District by Sex ---
    district_sex = district_cleaned[
        (district_cleaned["Age"].isin(["overall", "Total", "overall_age"])) &
        (district_cleaned["Gender"] != "Total") &
        (district_cleaned["Ethnic"] == "Total") &
        (district_cleaned.get("state", "") == "Pulau Pinang")
    ].copy()

    if "district" in district_sex.columns:
        district_sex = district_sex.rename(columns={"district": "District"})
    district_sex = district_sex.drop(
        columns=[c for c in ["state", "Age", "Ethnic"] if c in district_sex.columns],
        errors="ignore",
    )

    # Also include state-level sex data
    state_sex = state_cleaned[
        (state_cleaned["Age"].isin(["overall", "Total", "overall_age"])) &
        (state_cleaned["Gender"] != "Total") &
        (state_cleaned["Ethnic"] == "Total") &
        (state_cleaned.get("state", "") == "Pulau Pinang")
    ].copy()
    if "state" in state_sex.columns:
        state_sex = state_sex.rename(columns={"state": "District"})
    state_sex = state_sex.drop(
        columns=[c for c in ["Age", "Ethnic"] if c in state_sex.columns],
        errors="ignore",
    )
    district_sex = pd.concat([district_sex, state_sex], ignore_index=True)

    # Legacy Tableau district sex
    legacy_sex_file = DATA_DIR / "byDistrict&Gender (2 - Annual_population_byDistrictSex_PEN.xlsx)_byDistrict&Gender.csv"
    if legacy_sex_file.exists():
        try:
            legacy = pd.read_csv(legacy_sex_file)
            for drop_col in ["Population", "Number of Records"]:
                if drop_col in legacy.columns:
                    legacy = legacy.drop(columns=[drop_col])
            if "Year" in legacy.columns:
                legacy["Year"] = pd.to_datetime(legacy["Year"], dayfirst=True, errors="coerce").dt.year
                legacy = legacy[legacy["Year"] != 2020]
            district_sex = pd.concat([district_sex, legacy], ignore_index=True)
        except Exception as e:
            logger.warning("Failed to read legacy district sex: %s", e)

    logger.info(
        "District transforms: ethnicity=%d rows, sex=%d rows",
        len(district_ethnic), len(district_sex),
    )
    return {
        "district_ethnicity": district_ethnic,
        "district_sex": district_sex,
    }


def transform() -> dict[str, pd.DataFrame]:
    """Run all population OpenDOSM transforms."""
    districts = transform_district()
    return {
        "state": transform_state(),
        "malaysia": transform_malaysia(),
        **districts,
    }


def load(dfs: dict[str, pd.DataFrame]) -> None:
    """Write population data to Google Sheets."""
    if "state" in dfs and not dfs["state"].empty:
        # Write to Drive as CSV (equivalent to R's drive_update)
        tmp_path = write_csv(dfs["state"], "population_by_state_age_ethnicity_sex.csv", date_tag=True)
        try:
            upload_to_drive(tmp_path, "", file_name="population_by_state_age_ethnicity_sex.csv", date_tag=True)
        except Exception as e:
            logger.warning("Failed to upload state CSV to Drive: %s", e)

    sheet_map = {
        "malaysia": "pop-msia-age_sex_ethnicity",
        "district_ethnicity": "pop-district-ethnicity",
        "district_sex": "pop-district-sex",
    }
    for key, sheet_name in sheet_map.items():
        if key in dfs and not dfs[key].empty:
            write_sheet(dfs[key], OUTPUT_SHEET_ID, sheet_name)


def main() -> dict[str, pd.DataFrame]:
    """Run full population OpenDOSM pipeline."""
    dfs = transform()
    load(dfs)
    return dfs


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
