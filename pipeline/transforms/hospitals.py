"""Hospitals and bed utilisation transform.

Migrated from: scripts/health/hospitals.R (133 lines)

Two-part pipeline:
  1. Historical facility data from local Excel files → Google Sheet
  2. KKMNow bed utilisation time series reconstructed from MoH GitHub
     commit history → Google Drive CSV

Sources:
  - data/health/*.xlsx (government + private hospital Excel files)
  - data/health/facilities_by_state.csv (supplementary TSV)
  - GitHub MoH-Malaysia/data-resources-public commit history for bedutil_facility.csv
Output:
  - Google Sheet "facilities_by_state"
  - Google Drive → bedutil_facility_timeseries.csv
"""

import logging
import re
from pathlib import Path

import pandas as pd

from pipeline.fetchers.github_api import get_commit_shas, get_file_at_commit
from pipeline.loaders.file_writer import write_csv
from pipeline.loaders.google_sheets import (
    get_drive_folder_id,
    upload_to_drive,
    write_to_main_workbook,
)

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "health"


def transform_facilities() -> pd.DataFrame:
    """Transform historical facility data from Excel files.

    Combines government and private hospital data, pivots to long format,
    classifies by sector and metric type, then appends supplementary data.
    """
    gov_path = DATA_DIR / "Number of Government Hospitals Special Medical Institutions And Beds By State Malaysia 2000 - 2021_dataset.xlsx"
    private_path = DATA_DIR / "Number of Private Hospitals Nursing And Maternity Homes And Beds By State Malaysia 2000 - 2021_dataset.xlsx"

    if not gov_path.exists() or not private_path.exists():
        logger.warning("Hospital Excel files not found in %s — skipping facilities transform", DATA_DIR)
        return pd.DataFrame()

    gov = pd.read_excel(gov_path)
    private = pd.read_excel(private_path)

    gov["Year"] = pd.to_numeric(gov["Year"], errors="coerce")
    merged = gov.merge(private, on=["Year", "State"], suffixes=("_public", "_private"))

    # Pivot to long format
    id_cols = ["Year", "State"]
    value_cols = [c for c in merged.columns if c not in id_cols]
    long = merged.melt(id_vars=id_cols, value_vars=value_cols, var_name="name", value_name="value")

    # Classify columns
    long["colname"] = long["name"].apply(
        lambda x: "Number of beds" if "Beds" in str(x) or "beds" in str(x)
        else ("Number of facilities" if "Hospitals" in str(x) or "hospitals" in str(x) else None)
    )
    long["Sector"] = long["name"].apply(
        lambda x: "Public" if re.search(r"Government|public", str(x)) else
        ("Private" if re.search(r"[Pp]rivate", str(x)) else None)
    )

    long = long.drop(columns=["name"])
    pivoted = long.pivot_table(
        index=["Year", "State", "Sector"],
        columns="colname",
        values="value",
        aggfunc="first",
    ).reset_index()
    pivoted.columns.name = None

    # Append supplementary facilities data if available
    supp_path = DATA_DIR / "facilities_by_state.csv"
    if supp_path.exists():
        supp = pd.read_csv(supp_path, sep="\t")
        pivoted = pd.concat([pivoted, supp], ignore_index=True)

    logger.info("Facilities transform: %d rows", len(pivoted))
    return pivoted


def transform_bedutil_timeseries() -> pd.DataFrame:
    """Reconstruct bed utilisation time series from GitHub commit history.

    Fetches the bedutil_facility.csv at each commit to build a historical
    time series — the same approach as the R script's GitHub API calls.
    """
    repo = "MoH-Malaysia/data-resources-public"
    path = "bedutil_facility.csv"

    commits = get_commit_shas(repo, path)
    if not commits:
        logger.warning("No commits found for %s/%s", repo, path)
        return pd.DataFrame()

    frames = []
    for commit in commits:
        sha = commit["sha"]
        # Extract date from commit message (format: "data as of YYYY-MM-DD")
        msg = commit.get("commit", {}).get("message", "")
        date_match = re.search(r"\d{4}-\d{2}-\d{2}", msg)
        if not date_match:
            continue
        date_str = date_match.group()

        try:
            df = get_file_at_commit(repo, path, sha)
            df["date"] = date_str
            frames.append(df)
        except Exception as e:
            logger.warning("Failed to fetch %s at %s: %s", path, sha[:8], e)

    if not frames:
        return pd.DataFrame()

    result = pd.concat(frames, ignore_index=True)
    logger.info("Bed utilisation timeseries: %d rows from %d commits", len(result), len(frames))
    return result


def transform() -> dict[str, pd.DataFrame]:
    """Run all hospital transforms and return results (no side effects)."""
    return {
        "facilities": transform_facilities(),
        "bedutil": transform_bedutil_timeseries(),
    }


def load_facilities(df: pd.DataFrame) -> None:
    """Write facilities data to Google Sheets."""
    if df.empty:
        return
    write_to_main_workbook(df, "facilities_by_state")


def load_bedutil_timeseries(df: pd.DataFrame) -> None:
    """Write bed utilisation timeseries to local CSV and Google Drive."""
    if df.empty:
        return
    csv_path = write_csv(df, "bedutil_facility_timeseries.csv", date_tag=True)
    folder_id = get_drive_folder_id("bed_utilisation")
    upload_to_drive(csv_path, folder_id, "bedutil_facility_timeseries.csv", date_tag=True)


def main() -> dict[str, pd.DataFrame]:
    """Run both hospital pipelines."""
    results = transform()
    load_facilities(results["facilities"])
    load_bedutil_timeseries(results["bedutil"])
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
