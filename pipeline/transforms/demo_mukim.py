"""Mukim-level demographics transform.

Migrated from: scripts/population/demo-mukim.R (116 lines)

Processes 2010 and 2020 census mukim-level demographics for Penang
from a multi-sheet Excel file, combining population, ethnicity,
and age group data.

Sources:
  - OpenDOSM CSV: population_district.csv
Output: Google Sheet 1lhV1_RkPMgZURF0G36Fk_EoaeXfGX7c5QQu-B878wj0
"""

import logging
import re

import numpy as np
import pandas as pd

from pipeline.config.registry import get_sheet_id
from pipeline.loaders.google_sheets import write_sheet

logger = logging.getLogger(__name__)

DISTRICT_URL = "https://storage.dosm.gov.my/population/population_district.csv"
OUTPUT_SHEET_ID = get_sheet_id("demo_mukim", "output")

YEARS = [2010, 2020]


def _read_sheets(xls: pd.ExcelFile, sheets: list[str],
                 na_values=("-", ""), col_types=None) -> pd.DataFrame:
    """Read and concatenate multiple Excel sheets, adding a 'sheet' column."""
    frames = []
    for sheet in sheets:
        try:
            kwargs = dict(sheet_name=sheet, header=None, skiprows=7,
                          na_values=na_values)
            if col_types is not None:
                kwargs["dtype"] = {i: t for i, t in enumerate(col_types)}
            df = pd.read_excel(xls, **kwargs)
            if col_types is not None:
                df = df.drop_duplicates()
            df.insert(0, "sheet", sheet)
            frames.append(df)
        except Exception as e:
            logger.warning("Failed to read sheet %s: %s", sheet, e)
            continue
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _name_point1_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Assign proper column names to Point 1 data.

    R assigns names by position (1-indexed):
      col 2 = area
      cols 3-4 = pop_total_{2010,2020}
      cols 6-7 = pop_male_{2010,2020}
      cols 9-10 = pop_female_{2010,2020}
      cols 12-13 = sex-ratio_{2010,2020}
      cols 15-16 = households_{2010,2020}
      cols 18-19 = household-size_{2010,2020}
      cols 21-22 = living-quarters_{2010,2020}
    Columns 5, 8, 11, 14, 17, 20 are unnamed separators (dropped later).
    """
    metrics = ["pop_total", "pop_male", "pop_female", "sex-ratio",
               "households", "household-size", "living-quarters"]

    # Build full column name list: sheet (0), area (1), then groups of 3
    # (metric_2010, metric_2020, separator) for each metric.
    # Last metric has no trailing separator.
    col_names = ["sheet", "area"]
    for i, metric in enumerate(metrics):
        for year in YEARS:
            col_names.append(f"{metric}_{year}")
        if i < len(metrics) - 1:
            col_names.append(f"_sep_{i}")

    # Assign names up to available columns
    n = min(len(col_names), len(df.columns))
    new_names = list(col_names[:n])
    # Any remaining columns get generic names
    for j in range(n, len(df.columns)):
        new_names.append(f"_extra_{j}")

    df.columns = new_names

    # Drop separator and extra columns
    keep = [c for c in df.columns if not c.startswith("_sep_")
            and not c.startswith("_extra_")]
    return df[keep].copy()


def _name_point2_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Assign proper column names to Point 2 (ethnicity) data."""
    ethnicity_groups = ["total", "citizens", "bumiputera", "malay",
                        "other-bumiputera", "chinese", "indian",
                        "other-citizen", "non-citizen"]
    col_names = ["sheet", "area"]
    for group in ethnicity_groups:
        for year in YEARS:
            col_names.append(f"{group}_{year}")

    n = min(len(col_names), len(df.columns))
    df.columns = list(col_names[:n]) + [f"_extra_{j}"
                                         for j in range(n, len(df.columns))]
    keep = [c for c in df.columns if not c.startswith("_extra_")]
    return df[keep].copy()


def _name_point3_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Assign proper column names to Point 3 (age groups) data."""
    age_groups = ["under-14", "15-64", "65-plus"]
    col_names = ["sheet", "area"]
    # total columns
    for year in YEARS:
        col_names.append(f"total {year}")
    # age-group columns
    for ag in age_groups:
        for year in YEARS:
            col_names.append(f"age-group_{ag}_{year}")
    # blank separator
    col_names.append("blank")
    # dependency-ratio columns
    for ratio_type in ["total", "young", "old"]:
        for year in YEARS:
            col_names.append(f"dependency-ratio_{ratio_type}_{year}")

    n = min(len(col_names), len(df.columns))
    df.columns = list(col_names[:n]) + [f"_extra_{j}"
                                         for j in range(n, len(df.columns))]
    keep = [c for c in df.columns if not c.startswith("_extra_")]
    return df[keep].copy()


def _process_and_pivot(df: pd.DataFrame,
                       districts: pd.DataFrame) -> pd.DataFrame:
    """Clean area names, fill state/district, and pivot to long format.

    Mirrors the R process_and_pivot() function.
    """
    # Get unique state names (uppercased) from district reference
    state_names_upper = set(
        districts["state"].dropna().unique().tolist()
    )
    state_names_upper = {s.upper() for s in state_names_upper}

    # Clean area names: remove parenthetical text, strip whitespace
    df["area"] = df["area"].astype(str).str.replace(
        r"\(.{2,}\)", "", regex=True
    ).str.strip()

    # Identify state rows: area matches an uppercase state name
    df["state"] = df["area"].where(df["area"].isin(state_names_upper))
    df["state"] = df["state"].ffill()

    # Identify district rows: area != state AND all data columns are NA
    data_cols = [c for c in df.columns
                 if c not in ("sheet", "area", "state")]
    all_na = df[data_cols].isna().all(axis=1)
    df["district"] = np.where(
        (df["state"] != df["area"]) & all_na,
        df["area"], np.nan
    )
    df["district"] = df["district"].ffill()

    # Reorder columns
    id_cols = ["sheet", "state", "district", "area"]
    value_cols = [c for c in df.columns if c not in id_cols]
    df = df[id_cols + value_cols]

    # Filter out rows where ALL data columns are NA
    data_cols_final = [c for c in df.columns if c not in id_cols]
    df = df[~df[data_cols_final].isna().all(axis=1)]

    # Pivot to long format using names_pattern: ([^_]+)_([^_]*)_*(\d{4})
    # This separates e.g. "pop_total_2010" -> name1="pop", name2="total", year="2010"
    # and "total_2010" -> name1="total", name2="", year="2010"
    records = []
    pattern = re.compile(r"^([^_]+)_([^_]*)_*(\d{4})$")
    for col in data_cols_final:
        m = pattern.match(col)
        if not m:
            continue
        name1, name2, year = m.groups()
        # Clean name2: empty or "total" -> None
        if name2 in ("", "total"):
            name2 = None
        for _, row in df.iterrows():
            records.append({
                "sheet": row["sheet"],
                "state": row["state"],
                "district": row["district"],
                "area": row["area"],
                "year": year,
                "name2": name2,
                "name1": name1,
                "value": row[col],
            })

    if not records:
        return pd.DataFrame()

    long_df = pd.DataFrame(records)

    # Pivot wider: name1 becomes columns
    pivoted = long_df.pivot_table(
        index=["sheet", "state", "district", "area", "year", "name2"],
        columns="name1",
        values="value",
        aggfunc="first",
        dropna=False,
    ).reset_index()
    pivoted.columns.name = None

    return pivoted


def transform() -> pd.DataFrame:
    """Fetch and transform mukim demographics."""
    logger.info("Mukim demographics: census file removed")
    return pd.DataFrame()


def load(df: pd.DataFrame) -> None:
    """Write mukim demographics to Google Sheets."""
    if not df.empty:
        write_sheet(df, OUTPUT_SHEET_ID, "data")


def main() -> pd.DataFrame:
    """Run full mukim demographics pipeline."""
    df = transform()
    load(df)
    return df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
