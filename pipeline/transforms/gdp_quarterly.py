"""GDP Quarterly transform.

Migrated from: scripts/gdp/gdp-msia-qtr.R (63 lines)

Fetches 6 quarterly GDP parquet files (nominal/real/real_sa × demand/supply),
combines them with a lookup table for sector descriptions, and uploads
the result as a CSV to Google Drive.

Output columns: date, code, nominal, real, real_sa, lvl1, lvl2, lvl3,
               lvl1_desc, lvl2_desc, lvl3_desc, desc
Output: Google Drive folder → gdp_qtr.csv
"""

import itertools
import logging
import tempfile

import pandas as pd

from pipeline.fetchers.opendosm import fetch_parquet
from pipeline.loaders.file_writer import write_csv
from pipeline.loaders.google_sheets import get_drive_folder_id, upload_to_drive

logger = logging.getLogger(__name__)

GDP_QTR_TEMPLATE = "https://storage.dosm.gov.my/gdp/gdp_qtr_{catalogue_id}.parquet"
GDP_LOOKUP_URL = "https://storage.dosm.gov.my/gdp/gdp_lookup.parquet"

# Expenditure sub-codes with no seasonally adjusted data (PDF spec section real_sa)
REAL_SA_UNAVAILABLE_CODES = frozenset([
    "e1.1.01", "e1.1.03", "e1.1.04", "e1.1.05", "e1.1.07",
    "e1.1.08", "e1.1.09", "e1.1.11", "e1.1.12",
    "e3.1", "e3.1.1", "e3.1.2", "e3.1.3",
    "e3.2", "e3.2.1", "e3.2.2",
    "e4", "e5.1", "e5.2", "e6.1", "e6.2",
])


def _build_paths() -> pd.DataFrame:
    """Build the GDP quarterly file paths.

    Mirrors the R expand_grid + mutate logic:
      - For non-real_sa series, demand → demand_sub in the URL
      - catalogue_id removes the _sub suffix for the final column label
    """
    rows = []
    for v1, v2 in itertools.product(
        ["nominal", "real", "real_sa"],
        ["demand", "supply"],
    ):
        url_v2 = "demand_sub" if v1 != "real_sa" and v2 == "demand" else v2
        catalogue_id = f"{v1}_{url_v2}"
        url = GDP_QTR_TEMPLATE.format(catalogue_id=catalogue_id)
        # The catalogue_id used for naming strips _sub
        clean_id = f"{v1}_{v2}"
        rows.append({"series_type": v1, "url": url, "catalogue_id": clean_id})
    return pd.DataFrame(rows)


def transform() -> pd.DataFrame:
    """Fetch and transform quarterly GDP data. Returns the output DataFrame."""
    paths = _build_paths()

    # Fetch lookup table
    gdp_lookup = fetch_parquet(GDP_LOOKUP_URL)[["code", "desc_en"]].rename(
        columns={"desc_en": "desc"}
    )
    # Keep a clean copy for the flat desc column before level lookups modify it
    flat_desc_lookup = gdp_lookup[["code", "desc"]].copy()

    # Fetch all parquet files and combine
    frames = []
    for _, row in paths.iterrows():
        df = fetch_parquet(row["url"])
        # Normalize column name: some files use "type", others use "sector"
        if "type" in df.columns:
            df = df.rename(columns={"type": "code"})
        elif "sector" in df.columns:
            df = df.rename(columns={"sector": "code"})
        df["series_type"] = row["series_type"]
        frames.append(df)

    combined = pd.concat(frames, ignore_index=True)

    # Filter to absolute values only, pivot series_type into columns
    combined = combined[combined["series"] == "abs"].drop(columns=["series"])
    pivoted = combined.pivot_table(
        index=["date", "code"],
        columns="series_type",
        values="value",
        aggfunc="first",
    ).reset_index()
    pivoted.columns.name = None

    # Build hierarchical level columns (matches R str_sub logic)
    pivoted["lvl1"] = pivoted["code"].str[:2]
    # Production codes (p-prefix) have no hierarchy — lvl1 must be NA per spec
    pivoted.loc[pivoted["code"].str.startswith("p"), "lvl1"] = pd.NA
    pivoted["lvl2"] = pivoted["code"].where(pivoted["code"].str.len() > 2).str[:4]
    pivoted["lvl3"] = pivoted["code"].where(pivoted["code"].str.len() > 4)

    # Join lookup descriptions at each level
    lvl1_lookup = gdp_lookup[~gdp_lookup["code"].str.contains(r"\.", regex=True)].rename(
        columns={"desc": "lvl1_desc", "code": "lvl1"}
    )
    lvl2_lookup = gdp_lookup[gdp_lookup["code"].str.count(r"\.") == 1].rename(
        columns={"desc": "lvl2_desc", "code": "lvl2"}
    )
    lvl3_lookup = gdp_lookup[gdp_lookup["code"].str.count(r"\.") == 2].rename(
        columns={"desc": "lvl3_desc", "code": "lvl3"}
    )

    result = pivoted.merge(lvl1_lookup, on="lvl1", how="left")
    result = result.merge(lvl2_lookup, on="lvl2", how="left")
    result = result.merge(lvl3_lookup, on="lvl3", how="left")

    # Add flat 'desc' column — direct code-to-description mapping for all codes
    result = result.merge(flat_desc_lookup, on="code", how="left")

    # Reorder columns to match PDF spec
    series_cols = [c for c in ["nominal", "real", "real_sa"] if c in result.columns]
    level_cols = ["lvl1", "lvl2", "lvl3", "lvl1_desc", "lvl2_desc", "lvl3_desc"]
    result = result[["date", "code"] + series_cols + level_cols + ["desc"]]

    # Set real_sa to NA for codes without seasonally adjusted data (per PDF spec)
    if "real_sa" in result.columns:
        result.loc[result["code"].isin(REAL_SA_UNAVAILABLE_CODES), "real_sa"] = pd.NA

    # Format date as dd/mm/yyyy per PDF spec
    result["date"] = pd.to_datetime(result["date"]).dt.strftime("%d/%m/%Y")

    logger.info("GDP quarterly transform: %d rows", len(result))
    return result


def load(df: pd.DataFrame) -> None:
    """Write GDP quarterly data to Google Drive."""
    csv_path = write_csv(df, "gdp_qtr.csv", date_tag=True)
    folder_id = get_drive_folder_id("gdp_quarterly")
    upload_to_drive(csv_path, folder_id, "gdp_qtr.csv", date_tag=True)


def main() -> pd.DataFrame:
    """Run full GDP quarterly pipeline."""
    df = transform()
    load(df)
    return df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
