"""Penang HS-level trade data transform (METS Online).

Ported from: tableau_data_prep/scripts/trade/prep_hs.R (79 lines).

Semi-automated flow: Hajar downloads the monthly Penang "Trade by Channel" HS
export from METS Online (one CSV for exports, one for imports) and drops them in
a shared Google Drive "inbox" folder. This transform lists that folder, melts
each wide month-matrix into long format, and writes the combined CSV/Parquet.

Raw input  : METS "Trade by Channel" CSV — two header rows; metadata columns
             (state, HS chapter, partner country) followed by one column per
             month; one CSV per trade direction.
Target form: state | type_of_trade | hs | country | month | trade_values
             (see "2. External Trade dashboard.pdf").

NOTE: METS column wording can drift between releases. The metadata-column
detection below is deliberately forgiving (keyword match), and month columns are
detected by parseable month/year names. Confirm the mapping against a real METS
export during verification (a file that yields zero month columns logs a warning
and is skipped rather than crashing the run).

Sources:
  - Google Drive inbox folder: registry trade_hs.drive_files.inbox
Output:
  - penang_monthly_exim_hs_country.csv / .parquet (date-tagged output dir)
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pandas as pd

from pipeline.config.registry import get_drive_id
from pipeline.fetchers.gdrive import download_file_from_drive, list_drive_folder
from pipeline.loaders.file_writer import write_csv, write_parquet

logger = logging.getLogger(__name__)

_PLACEHOLDER_PREFIX = "REPLACE_WITH"
OUTPUT_COLUMNS = ["state", "type_of_trade", "hs", "country", "month", "trade_values"]

_MALAY_MONTHS = {
    "januari": 1, "februari": 2, "mac": 3, "april": 4, "mei": 5, "jun": 6,
    "julai": 7, "ogos": 8, "september": 9, "oktober": 10, "november": 11,
    "disember": 12,
}
_ENGLISH_MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9, "october": 10,
    "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}


def _is_placeholder(value: str) -> bool:
    return (not value) or value.startswith(_PLACEHOLDER_PREFIX)


def _make_clean_names(raw_names: list[str]) -> list[str]:
    """Convert header strings to snake_case (like R's janitor::make_clean_names)."""
    result = []
    for name in raw_names:
        clean = re.sub(r"[^a-zA-Z0-9]", "_", str(name).lower())
        clean = re.sub(r"_+", "_", clean).strip("_")
        result.append(clean)
    return result


def _extract_trade_type(filename: str) -> str | None:
    """Infer 'exports' / 'imports' from the raw file name."""
    low = filename.lower()
    if "export" in low:
        return "exports"
    if "import" in low:
        return "imports"
    return None


def _parse_month_token(token: str) -> pd.Timestamp | None:
    """Parse a (cleaned) column name into a 1st-of-month Timestamp, else None."""
    t = token.lower()
    m = re.search(r"(20\d{2})[_\-\s]?(0[1-9]|1[0-2])(?!\d)", t)
    if m:
        return pd.Timestamp(year=int(m.group(1)), month=int(m.group(2)), day=1)
    m = re.search(r"(?<!\d)(0[1-9]|1[0-2])[_\-\s](20\d{2})", t)
    if m:
        return pd.Timestamp(year=int(m.group(2)), month=int(m.group(1)), day=1)
    year_m = re.search(r"(20\d{2})", t)
    if year_m:
        for name, num in {**_MALAY_MONTHS, **_ENGLISH_MONTHS}.items():
            if re.search(rf"(?<![a-z]){name}(?![a-z])", t):
                return pd.Timestamp(year=int(year_m.group(1)), month=num, day=1)
    return None


def _find_col(cols: list[str], *keywords: str) -> str | None:
    for kw in keywords:
        for c in cols:
            if kw in c:
                return c
    return None


def _normalise_hs(series: pd.Series) -> pd.Series:
    """HS chapter as a 2-digit string code (zero-pad single digits)."""
    s = series.astype("string").str.strip()
    is_digit = s.str.fullmatch(r"\d+").fillna(False)
    return s.mask(is_digit, s.str.zfill(2))


def _read_mets_csv(path: Path) -> pd.DataFrame:
    """Read a METS CSV whose first two rows form a (collapsed) header."""
    header = pd.read_csv(path, header=None, nrows=2, dtype=str)
    raw_names = []
    for col in range(header.shape[1]):
        parts = [
            str(header.iloc[row, col]).strip()
            for row in range(header.shape[0])
            if pd.notna(header.iloc[row, col]) and str(header.iloc[row, col]).strip()
        ]
        raw_names.append(" ".join(parts))
    names = _make_clean_names(raw_names)
    return pd.read_csv(path, skiprows=2, header=None, names=names)


def _reshape_mets(df: pd.DataFrame, type_of_trade: str) -> pd.DataFrame:
    """Melt one wide METS month-matrix into the long target schema.

    Pure function (no I/O) so it can be unit-tested with an in-memory fixture.
    """
    cols = list(df.columns)
    month_cols = [c for c in cols if _parse_month_token(c) is not None]
    if not month_cols:
        logger.warning("No month columns detected in METS file — check raw format.")
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    state_col = _find_col(cols, "state")
    hs_col = _find_col(cols, "hs", "chapter")
    country_col = _find_col(cols, "country", "partner")

    work = df.copy()
    # Drop the "PEN M'SIA" (Malaysia aggregate) rows; keep Penang only.
    if state_col:
        norm = (
            work[state_col].astype("string").str.upper()
            .str.replace(r"[^A-Z]", "", regex=True)
        )
        work = work[norm != "PENMSIA"]

    id_vars = [c for c in (state_col, hs_col, country_col) if c]
    long = work.melt(
        id_vars=id_vars,
        value_vars=month_cols,
        var_name="month_raw",
        value_name="trade_values",
    )
    long["month"] = long["month_raw"].map(_parse_month_token)
    long = long[long["month"].notna()].copy()

    rename = {}
    if state_col:
        rename[state_col] = "state"
    if hs_col:
        rename[hs_col] = "hs"
    if country_col:
        rename[country_col] = "country"
    long = long.rename(columns=rename)

    for required in ("state", "hs", "country"):
        if required not in long.columns:
            long[required] = pd.NA

    long["hs"] = _normalise_hs(long["hs"])
    long["type_of_trade"] = type_of_trade
    long["trade_values"] = pd.to_numeric(long["trade_values"], errors="coerce")
    return long[OUTPUT_COLUMNS]


def transform() -> pd.DataFrame:
    """Reshape every METS HS CSV in the Drive inbox into the long target schema."""
    folder_id = get_drive_id("trade_hs", "inbox")
    if _is_placeholder(folder_id):
        logger.warning(
            "Trade HS (METS) inbox folder not configured (%s) — "
            "set trade_hs.drive_files.inbox in google_sheets_registry.yaml.",
            folder_id,
        )
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    frames: list[pd.DataFrame] = []
    for entry in list_drive_folder(folder_id):
        name = entry["name"]
        if not name.lower().endswith(".csv") or name.startswith("~$"):
            continue
        trade_type = _extract_trade_type(name)
        if trade_type is None:
            logger.warning("Skipping METS file (no exports/imports in name): %s", name)
            continue
        try:
            path = download_file_from_drive(entry["id"], suffix=".csv")
            df = _read_mets_csv(path)
            reshaped = _reshape_mets(df, trade_type)
            if not reshaped.empty:
                frames.append(reshaped)
            logger.info("Reshaped METS file %s (%d rows)", name, len(reshaped))
        except Exception as e:
            logger.warning("Failed to process METS file %s: %s", name, e)

    result = (
        pd.concat(frames, ignore_index=True)
        if frames
        else pd.DataFrame(columns=OUTPUT_COLUMNS)
    )
    logger.info("Trade HS (METS): %d rows", len(result))
    return result


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
