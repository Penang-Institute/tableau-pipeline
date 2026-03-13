"""Penang population by state and ethnicity from OpenDOSM.

Migrated from: scripts/population/prep_pop_state_ethnicity.R (512 lines)

Reads OpenDOSM population_state parquet, applies ethnicity/sex/age mappings,
filters for Penang, combines with legacy data from Google Sheets, and
writes to a Penang-specific Google Sheet. Also processes Malaysia-level data,
district-level data, and fertility rates.

Sources:
  - OpenDOSM parquet: population_state.parquet
  - Local CSV: data/population/ (legacy Tableau data)
  - Local Excel: data/population/8.4.7_Fertility rate by age group...
Output:
  - Google Sheet: 1153Rt9d-evlO_q-FLbPRqX7v-_SGCaJWZmgB2W1cr4E (data_opendosm)
  - Local CSV: output/ (fertility, district ethnicity/sex)
"""

import logging
import re
from pathlib import Path

import pandas as pd

from pipeline.config.registry import get_sheet_id
from pipeline.fetchers.opendosm import fetch_parquet
from pipeline.loaders.google_sheets import write_sheet
from pipeline.loaders.file_writer import write_csv
from pipeline.utils.opendosm_helpers import (
    clean_opendosm,
    recode_ethnicity_for_district,
)

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "population"
DOSM_BASE = "https://storage.dosm.gov.my/population"

OUTPUT_SHEET_ID = get_sheet_id("population_ethnicity", "output")


def _clean_opendosm(df: pd.DataFrame) -> pd.DataFrame:
    """Apply standard ethnicity/sex/age cleanup for population data.

    Delegates to shared clean_opendosm with include_nationality=True.
    """
    return clean_opendosm(df, include_nationality=True)


def transform_penang() -> pd.DataFrame:
    """Transform Penang state population from OpenDOSM."""
    try:
        pop_state = fetch_parquet(f"{DOSM_BASE}/population_state.parquet")
    except Exception as e:
        logger.warning("Failed to fetch population_state: %s", e)
        return pd.DataFrame()

    cleaned = _clean_opendosm(pop_state)
    penang = cleaned[cleaned["state"] == "Pulau Pinang"].copy()

    logger.info("Penang population transform: %d rows", len(penang))
    return penang


def transform_malaysia() -> pd.DataFrame:
    """Transform Malaysia-level population from OpenDOSM + legacy CSV."""
    try:
        pop_msia = fetch_parquet(f"{DOSM_BASE}/population_malaysia.parquet")
    except Exception as e:
        logger.warning("Failed to fetch population_malaysia: %s", e)
        return pd.DataFrame()

    cleaned = _clean_opendosm(pop_msia)

    # Legacy pre-2020 data
    legacy_file = DATA_DIR / "by sex, age & ethnic (Population_byAgeEthnicGender_MAS.xlsx)_by sex, age & ethnic.csv"
    if legacy_file.exists():
        try:
            legacy = pd.read_csv(legacy_file)
            if "Year" in legacy.columns:
                legacy["Year"] = pd.to_datetime(
                    legacy["Year"], dayfirst=True, errors="coerce"
                ).dt.year
            if "Status" in legacy.columns:
                legacy = legacy[legacy["Status"].isna() | (legacy["Status"] != "forecast")]
                legacy["Status"] = legacy["Status"].replace("confirmed", None)
            if "Population" in legacy.columns:
                legacy["Population ('000)"] = legacy["Population"] / 1000
                legacy = legacy.drop(columns=["Population"])
            if "Age" in legacy.columns:
                legacy["Age"] = legacy["Age"].str.replace(r"\s+", "", regex=True)
            legacy = legacy[legacy["Year"] < 2020]
            cleaned = pd.concat([cleaned, legacy], ignore_index=True)
        except Exception as e:
            logger.warning("Failed to read Malaysia legacy CSV: %s", e)

    logger.info("Malaysia population transform: %d rows", len(cleaned))
    return cleaned


def transform_district() -> dict[str, pd.DataFrame]:
    """Transform Penang district population by ethnicity and sex."""
    try:
        pop_district = fetch_parquet(f"{DOSM_BASE}/population_district.parquet")
        pop_state = fetch_parquet(f"{DOSM_BASE}/population_state.parquet")
    except Exception as e:
        logger.warning("Failed to fetch district/state data: %s", e)
        return {"ethnicity": pd.DataFrame(), "sex": pd.DataFrame()}

    district_cleaned = _clean_opendosm(pop_district)
    state_cleaned = _clean_opendosm(pop_state)

    # --- By ethnicity ---
    ethnic = district_cleaned[
        (district_cleaned["Age"].isin(["overall_age", "Total"])) &
        (district_cleaned["Gender"] == "Total") &
        (district_cleaned["Ethnic"] != "Total") &
        (district_cleaned.get("state", "") == "Pulau Pinang")
    ].copy()

    if "district" in ethnic.columns:
        ethnic = ethnic.rename(columns={"district": "District"})
    ethnic = ethnic.drop(
        columns=[c for c in ["state", "Age", "Nationality", "Gender"]
                 if c in ethnic.columns],
        errors="ignore",
    )
    ethnic["Ethnic"] = ethnic["Ethnic"].apply(recode_ethnicity_for_district)

    # Legacy ethnicity
    legacy_ethnic_file = DATA_DIR / "byDistrict&Ethnic (3 - Annual_population_byDistrictEthnic_PEN.xlsx)_byDistrict&Ethnic.csv"
    if legacy_ethnic_file.exists():
        try:
            leg = pd.read_csv(legacy_ethnic_file)
            if "Population" in leg.columns:
                leg = leg.drop(columns=["Population"])
            if "Year" in leg.columns:
                leg["Year"] = pd.to_datetime(leg["Year"], dayfirst=True, errors="coerce").dt.year
                leg = leg[leg["Year"] != 2020]
            ethnic = pd.concat([ethnic, leg], ignore_index=True)
        except Exception as e:
            logger.warning("Failed to read legacy district ethnicity: %s", e)

    # --- By sex ---
    def _clean_gender(data, label):
        subset = data[
            (data["Age"].isin(["overall_age", "Total"])) &
            (data["Gender"] != "Total") &
            (data["Ethnic"] == "Total") &
            (data.get("state", "") == "Pulau Pinang")
        ].copy()
        subset = subset.drop(
            columns=[c for c in ["Age", "Nationality", "Ethnic"]
                     if c in subset.columns],
            errors="ignore",
        )
        return subset

    sex_district = _clean_gender(district_cleaned, "district")
    if "district" in sex_district.columns:
        sex_district = sex_district.rename(columns={"district": "District"})
    sex_district = sex_district.drop(columns=["state"], errors="ignore")

    sex_state = _clean_gender(state_cleaned, "state")
    if "state" in sex_state.columns:
        sex_state = sex_state.rename(columns={"state": "District"})

    sex_combined = pd.concat([sex_district, sex_state], ignore_index=True)

    # Legacy sex
    legacy_sex_file = DATA_DIR / "byDistrict&Gender (2 - Annual_population_byDistrictSex_PEN.xlsx)_byDistrict&Gender.csv"
    if legacy_sex_file.exists():
        try:
            leg = pd.read_csv(legacy_sex_file)
            for drop_col in ["Population", "Number of Records"]:
                if drop_col in leg.columns:
                    leg = leg.drop(columns=[drop_col])
            if "Year" in leg.columns:
                leg["Year"] = pd.to_datetime(leg["Year"], dayfirst=True, errors="coerce").dt.year
                leg = leg[leg["Year"] != 2020]
            sex_combined = pd.concat([sex_combined, leg], ignore_index=True)
        except Exception as e:
            logger.warning("Failed to read legacy district sex: %s", e)

    logger.info("District ethnicity=%d rows, sex=%d rows", len(ethnic), len(sex_combined))
    return {"ethnicity": ethnic, "sex": sex_combined}


def transform_fertility() -> pd.DataFrame:
    """Transform fertility rate data from local Excel."""
    fertility_file = DATA_DIR / "8.4.7_Fertility rate by age group and state Malaysia 2001 - 2021_dataset.xlsx"
    if not fertility_file.exists():
        logger.info("Fertility file not found — skipping")
        return pd.DataFrame()

    try:
        df = pd.read_excel(fertility_file)
        df = df[df["Age-specific Fertility Rate"] == "Total Fertility Rate"]
        result = df[["Country/State", "Year", "Fertility rate"]].copy()
        result = result.rename(columns={"Country/State": "State"})
        logger.info("Fertility transform: %d rows", len(result))
        return result
    except Exception as e:
        logger.warning("Failed to read fertility data: %s", e)
        return pd.DataFrame()


def transform() -> dict[str, pd.DataFrame]:
    """Run all population ethnicity transforms."""
    districts = transform_district()
    return {
        "penang": transform_penang(),
        "malaysia": transform_malaysia(),
        "district_ethnicity": districts["ethnicity"],
        "district_sex": districts["sex"],
        "fertility": transform_fertility(),
    }


def load(dfs: dict[str, pd.DataFrame]) -> None:
    """Write population ethnicity data to Google Sheets and local files."""
    if "penang" in dfs and not dfs["penang"].empty:
        write_sheet(dfs["penang"], OUTPUT_SHEET_ID, "data_opendosm")

    if "district_ethnicity" in dfs and not dfs["district_ethnicity"].empty:
        write_csv(dfs["district_ethnicity"], "population_district_ethnicity.csv", date_tag=True)

    if "district_sex" in dfs and not dfs["district_sex"].empty:
        write_csv(dfs["district_sex"], "population_district_sex.csv", date_tag=True)

    if "fertility" in dfs and not dfs["fertility"].empty:
        write_csv(dfs["fertility"], "fertility.csv", date_tag=True)


def main() -> dict[str, pd.DataFrame]:
    """Run full population ethnicity pipeline."""
    dfs = transform()
    load(dfs)
    return dfs


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
