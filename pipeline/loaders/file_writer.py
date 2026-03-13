"""Write DataFrames to local files (CSV, Parquet)."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "output"


def write_csv(df: pd.DataFrame, filename: str, output_dir: Path | None = None, date_tag: bool = False) -> Path:
    """Write a DataFrame to CSV in the output directory.

    If date_tag is True, writes into a YYYY-MM-DD subdirectory.
    """
    base = output_dir or OUTPUT_DIR
    if date_tag:
        from pipeline.loaders.datestamp import dated_output_dir
        out = dated_output_dir(base)
    else:
        out = base
        out.mkdir(parents=True, exist_ok=True)
    path = out / filename
    df.to_csv(path, index=False)
    logger.info("Wrote %d rows to %s", len(df), path)
    return path


def write_parquet(df: pd.DataFrame, filename: str, output_dir: Path | None = None, date_tag: bool = False) -> Path:
    """Write a DataFrame to Parquet in the output directory.

    If date_tag is True, writes into a YYYY-MM-DD subdirectory.
    """
    base = output_dir or OUTPUT_DIR
    if date_tag:
        from pipeline.loaders.datestamp import dated_output_dir
        out = dated_output_dir(base)
    else:
        out = base
        out.mkdir(parents=True, exist_ok=True)
    path = out / filename
    df.to_parquet(path, index=False)
    logger.info("Wrote %d rows to %s", len(df), path)
    return path
