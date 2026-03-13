"""Penang HS-level trade data transform.

Migrated from: scripts/trade/prep_hs.R (79 lines)

Reads monthly trade data by HS code, country, and type (exports/imports),
pivots to long format, and writes output files.

Output:
  - Local parquet/CSV copies
"""

import logging
import re

import pandas as pd

from pipeline.loaders.file_writer import write_csv, write_parquet

logger = logging.getLogger(__name__)


def _make_clean_names(raw_names: list[str]) -> list[str]:
    """Convert header row strings to snake_case (like R's janitor::make_clean_names)."""
    result = []
    for name in raw_names:
        clean = re.sub(r"[^a-zA-Z0-9]", "_", str(name).lower())
        clean = re.sub(r"_+", "_", clean).strip("_")
        result.append(clean)
    return result


def transform() -> pd.DataFrame:
    """Fetch and transform HS trade data."""
    logger.info("Trade HS: network drive removed")
    return pd.DataFrame()


def load(df: pd.DataFrame) -> None:
    """Write trade HS data to output files."""
    if df.empty:
        return

    write_csv(df, "penang_monthly_exim_hs_country.csv", date_tag=True)
    write_parquet(df, "penang_monthly_exim_hs_country.parquet", date_tag=True)


def main() -> pd.DataFrame:
    """Run full trade HS pipeline."""
    df = transform()
    load(df)
    return df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
