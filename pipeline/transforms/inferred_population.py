"""Inferred population from GDP data.

Migrated from: scripts/gdp/inferred_population_fixed.R (121 lines)

Infers population by calculating population = GDP / GDP per capita, using
a Malaysia-level file from local data (MysIDC).

Sources:
  - Local: data/gdp/1.1.1.1 *.xlsx (MysIDC Malaysia GDP)
Output: DataFrame only (no Google Sheet output in the R script)
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "gdp"


def _mutate_period(df: pd.DataFrame, period_col: str = "period") -> pd.DataFrame:
    """Extract year and data status from period column."""
    df = df.copy()
    df["year"] = df[period_col].str[:4].astype(int)
    df["status"] = df[period_col].apply(
        lambda x: None if len(str(x)) == 4
        else ("preliminary" if str(x).endswith("p") else "estimate")
    )
    return df


def _extract_base_year(filename: str) -> str | None:
    """Extract base year from filename pattern like (2005=100)."""
    m = re.search(r"\((\d{4})=100\)", filename)
    return m.group(1) if m else None


def _extract_last_updated(filename: str) -> str | None:
    """Extract last year from filename pattern like 2005-2021."""
    m = re.search(r"\d{4}-(\d{4})", filename)
    return m.group(1) if m else None


def transform() -> pd.DataFrame:
    """Fetch and transform inferred population data from local MysIDC files."""
    frames = []

    # Malaysia-level data from MysIDC
    msia_files = list(DATA_DIR.glob("1.1.1.1*dataset.xlsx"))
    if msia_files:
        try:
            gdp_msia = pd.read_excel(
                msia_files[0],
                header=None,
                names=["price_type", "year", "gdp", "gni",
                       "gdp_per_capita", "gni_per_capita"],
                na_values="..",
                skiprows=1,
            )
            gdp_msia = gdp_msia[gdp_msia["year"] >= 2005]
            gdp_msia = gdp_msia[["year", "gdp", "gdp_per_capita"]].copy()
            gdp_msia["location"] = "Malaysia"
            gdp_msia["file_name"] = "mysidc_1_1_1_1"
            gdp_msia["last_updated"] = str(pd.Timestamp.today().year)
            frames.append(gdp_msia)
        except Exception as e:
            logger.warning("Failed to read Malaysia GDP: %s", e)

    if not frames:
        logger.warning("No GDP data available for population inference")
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    combined["population"] = combined["gdp"] / combined["gdp_per_capita"]

    # Keep latest update per location/year/base_year
    combined["last_updated_int"] = pd.to_numeric(
        combined["last_updated"], errors="coerce"
    )
    combined = (
        combined.sort_values("last_updated_int", ascending=False)
        .groupby(["location", "year", "base_year"], dropna=False)
        .first()
        .reset_index()
    )
    combined = combined.drop(columns=["last_updated_int"])

    logger.info("Inferred population transform: %d rows", len(combined))
    return combined


def main() -> pd.DataFrame:
    """Run inferred population pipeline (no loader — data only)."""
    return transform()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
