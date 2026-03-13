"""Graduate employment statistics transform.

Migrated from: scripts/highered/graduan.R (105 lines)

Processes graduate employment and sector data from Penang education census
Excel file, pivots into tidy format, and writes to Google Sheets.

Source: data/education/GRADUAN BERMASTAUTIN DI PULAU PINANG TAHUN 2013_2021.xls
Output: Google Sheet 1nF7xCn68s21QLtG9DTH8ug6jXxQphkec3whz_RcJZ80
  - sheet "sektor_ekonomi"
  - sheet "status_pekerjaan"
"""

import logging
import re
from pathlib import Path

import pandas as pd

from pipeline.config.registry import get_sheet_id
from pipeline.loaders.google_sheets import write_sheet

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "education"
EXCEL_FILE = "GRADUAN BERMASTAUTIN DI PULAU PINANG TAHUN 2013_2021.xls"
OUTPUT_SHEET_ID = get_sheet_id("graduates", "output")


def _make_clean_name(s: str) -> str:
    """Convert a string to snake_case (like R's janitor::make_clean_names)."""
    s = re.sub(r"[^a-zA-Z0-9]", "_", str(s).lower())
    s = re.sub(r"_+", "_", s).strip("_")
    return s


def _build_paired_colnames(headers: list[str]) -> list[str]:
    """Build column pairs (bil, pct) for each header plus 'jumlah'."""
    all_headers = list(headers) + ["jumlah"]
    result = []
    for h in all_headers:
        clean = _make_clean_name(h)
        result.append(f"{clean}_bil")
        result.append(f"{clean}_pct")
    return result


def transform_sektor_ekonomi() -> pd.DataFrame:
    """Transform graduate employment by economic sector."""
    file_path = DATA_DIR / EXCEL_FILE
    if not file_path.exists():
        logger.warning("Graduate file not found: %s", file_path)
        return pd.DataFrame()

    # Read sector headers
    headers_df = pd.read_excel(
        file_path, sheet_name="SEKTOR EKONOMI", skiprows=3, nrows=0
    )
    sector_headers = [
        c for c in headers_df.columns if not c.startswith("Unnamed")
    ]
    colnames = _build_paired_colnames(sector_headers)

    # Read data
    df = pd.read_excel(
        file_path, sheet_name="SEKTOR EKONOMI", skiprows=4,
        na_values=["-", ""],
    )
    df.columns = ["tahun", "sektor_bekerja"] + colnames[:len(df.columns) - 2]

    # Forward-fill year
    df["tahun"] = df["tahun"].ffill()

    # Convert numeric columns
    for col in df.columns[2:]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Pivot to long format
    melted = df.melt(
        id_vars=["tahun", "sektor_bekerja"],
        var_name="name",
        value_name="value",
    )

    # Split name into field_of_study and measure (bil/pct)
    melted["bidang_pengajian"] = melted["name"].str.replace(
        r"_(bil|pct)$", "", regex=True
    )
    melted["measure"] = melted["name"].str.extract(r"_(bil|pct)$")[0]
    melted = melted.drop(columns=["name"])

    # Pivot wider on measure
    pivoted = melted.pivot_table(
        index=["tahun", "sektor_bekerja", "bidang_pengajian"],
        columns="measure",
        values="value",
        aggfunc="first",
    ).reset_index()
    pivoted.columns.name = None

    # Clean names
    pivoted["bidang_pengajian"] = (
        pivoted["bidang_pengajian"]
        .str.replace("_", " ")
        .str.capitalize()
    )
    pivoted["sektor_bekerja"] = pivoted["sektor_bekerja"].str.strip().str.replace(
        r"\s+", " ", regex=True
    )

    pivoted = pivoted.sort_values(
        ["tahun", "bidang_pengajian", "sektor_bekerja"]
    )

    logger.info("Sektor ekonomi transform: %d rows", len(pivoted))
    return pivoted


def transform_status_pekerjaan() -> pd.DataFrame:
    """Transform graduate employment status."""
    file_path = DATA_DIR / EXCEL_FILE
    if not file_path.exists():
        return pd.DataFrame()

    # Read status headers
    headers_df = pd.read_excel(
        file_path, sheet_name="STATUS PEKERJAAN", skiprows=3, nrows=0
    )
    status_headers = [
        c for c in headers_df.columns if not c.startswith("Unnamed")
    ]
    colnames = _build_paired_colnames(status_headers)

    # Read data
    df = pd.read_excel(
        file_path, sheet_name="STATUS PEKERJAAN", skiprows=4,
        na_values=["-", ""],
    )
    df.columns = ["tahun", "sektor"] + colnames[:len(df.columns) - 2]

    # Forward-fill year
    df["tahun"] = df["tahun"].ffill()

    # Convert numeric columns
    for col in df.columns[2:]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Filter out empty sectors
    df = df.dropna(subset=["sektor"])

    # Pivot to long
    melted = df.melt(
        id_vars=["tahun", "sektor"],
        var_name="name",
        value_name="value",
    )
    melted["status"] = melted["name"].str.replace(
        r"_(bil|pct)$", "", regex=True
    )
    melted["measure"] = melted["name"].str.extract(r"_(bil|pct)$")[0]
    melted = melted.drop(columns=["name"])

    pivoted = melted.pivot_table(
        index=["tahun", "sektor", "status"],
        columns="measure",
        values="value",
        aggfunc="first",
    ).reset_index()
    pivoted.columns.name = None

    pivoted["status"] = (
        pivoted["status"]
        .str.replace("_", " ")
        .str.capitalize()
    )

    logger.info("Status pekerjaan transform: %d rows", len(pivoted))
    return pivoted


def transform() -> dict[str, pd.DataFrame]:
    """Run both graduate transforms."""
    return {
        "sektor_ekonomi": transform_sektor_ekonomi(),
        "status_pekerjaan": transform_status_pekerjaan(),
    }


def load(dfs: dict[str, pd.DataFrame]) -> None:
    """Write graduate data to Google Sheets."""
    for key, df in dfs.items():
        if not df.empty:
            write_sheet(df, OUTPUT_SHEET_ID, key)


def main() -> dict[str, pd.DataFrame]:
    """Run full graduates pipeline."""
    dfs = transform()
    load(dfs)
    return dfs


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
