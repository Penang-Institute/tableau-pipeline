"""Penang HS-level trade data transform (METS Online — Trade by Channel).

Semi-automated flow: Hajar downloads the monthly Penang "Trade by Channel (RM)
Multi Trade Flow" export from METS Online (CSV or XLSX — one file holds *both*
exports and imports) and drops it in a Drive inbox folder. This transform reads
each file, melts the month/direction value columns into long format, and writes
`penang_monthly_exim_hs_country.csv`.

Real METS layout (verified against a 2026 export):
  - A title row, then the header row: No, State, Chapter, Chapter Description,
    Partner Country Name, then one column per month *and direction*, e.g.
    "May 2026 IMPORTS Value (MYR)", "May 2026 EXPORTS Value (MYR)".
  - HS code lives in "Chapter" (stored as an Excel text formula ="01" in CSV).
  - Trade direction is in the value-column header, NOT the file name.

Target form (PDF "External Trade dashboard", worksheet b):
  state | type_of_trade | hs | country | month | trade_values

Source : Drive inbox folder (registry trade_hs.drive_files.inbox)
Output : penang_monthly_exim_hs_country.csv / .parquet
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pandas as pd

from pipeline.config.registry import get_drive_id
from pipeline.fetchers.gdrive import download_file_from_drive, list_drive_folder
from pipeline.loaders.drive_merge import append_periods_to_drive_csv
from pipeline.loaders.file_writer import write_csv, write_parquet

logger = logging.getLogger(__name__)

_PLACEHOLDER_PREFIX = "REPLACE_WITH"
OUTPUT_COLUMNS = ["state", "type_of_trade", "hs", "country", "month", "trade_values"]

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


# METS occasionally relabels a country. The dashboard's "Trading Partner
# (Country)" control is a Tableau *parameter* with a hard-coded member list, so
# an unmapped label is silently unselectable and its series splits in two at the
# rename date. Map incoming METS spellings onto the parameter's vocabulary.
# Adding an entry here is cheaper than editing the workbook.
_COUNTRY_ALIASES = {
    "ANTIGUA & BARBUDA": "ANTIGUA AND BARBUDA",
    "OTHER COUNTRIES,NES": "OTHER COUNTRIES, NES.",
    "UNITED STATE MINOR OUTLYING ISLANDS": "UNITED STATES MINOR OUTLYING ISLANDS",
    # TURKEY -> TURKIYE was applied the other way round (the parameter was
    # updated to the modern name), so METS's "TURKIYE" needs no mapping.
}


def _is_placeholder(value: str) -> bool:
    return (not value) or value.startswith(_PLACEHOLDER_PREFIX)


def _clean(name: str) -> str:
    c = re.sub(r"[^a-z0-9]+", "_", str(name).lower())
    return re.sub(r"_+", "_", c).strip("_")


def _parse_month(token: str) -> pd.Timestamp | None:
    """Parse 'May 2026 ...' (cleaned: 'may_2026_...') into a 1st-of-month date."""
    t = str(token).lower()
    ym = re.search(r"(20\d{2})", t)
    if not ym:
        return None
    for mon, num in _MONTHS.items():
        if re.search(rf"(?<![a-z]){mon}", t):
            return pd.Timestamp(year=int(ym.group(1)), month=num, day=1)
    return None


def _find_col(cols: list[str], *keywords: str) -> str | None:
    for kw in keywords:
        for c in cols:
            if kw in c:
                return c
    return None


def _normalise_hs(series: pd.Series) -> pd.Series:
    """HS chapter → 2-digit string (strip the Excel ="01" wrapper, zero-pad)."""
    digits = series.astype("string").str.replace(r"[^0-9]", "", regex=True)
    return digits.str.zfill(2).where(digits.str.len() > 0, series.astype("string"))


def _detect_header_row(preview: pd.DataFrame) -> int:
    """The header row is the one containing both 'State' and 'Chapter'."""
    for i in range(len(preview)):
        vals = [str(x).strip().lower() for x in preview.iloc[i]]
        if "state" in vals and "chapter" in vals:
            return i
    return 0


def _read_mets_file(path: Path, is_excel: bool) -> pd.DataFrame:
    """Read a METS file (CSV or XLSX), skipping the title row(s); clean columns."""
    if is_excel:
        preview = pd.read_excel(path, sheet_name=0, header=None, nrows=8, dtype=str)
        hdr = _detect_header_row(preview)
        df = pd.read_excel(path, sheet_name=0, skiprows=hdr, dtype=str)
    else:
        preview = pd.read_csv(path, header=None, nrows=8, dtype=str)
        hdr = _detect_header_row(preview)
        df = pd.read_csv(path, skiprows=hdr, dtype=str)
    df.columns = [_clean(c) for c in df.columns]
    return df


def _reshape_mets(df: pd.DataFrame) -> pd.DataFrame:
    """Melt the month/direction value columns into the long target schema.

    Pure function (no I/O) so it is unit-testable with an in-memory fixture.
    """
    cols = list(df.columns)
    value_cols = [
        c for c in cols
        if re.search(r"import|export", c) and _parse_month(c) is not None
    ]
    if not value_cols:
        logger.warning("No month/direction value columns detected — check format.")
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    state_col = _find_col(cols, "state")
    hs_col = next((c for c in cols if c == "chapter"), None) \
        or next((c for c in cols if "chapter" in c and "desc" not in c), None)
    country_col = _find_col(cols, "country", "partner")
    id_vars = [c for c in (state_col, hs_col, country_col) if c]

    long = df.melt(
        id_vars=id_vars, value_vars=value_cols,
        var_name="_col", value_name="trade_values",
    )
    long["month"] = long["_col"].map(_parse_month)
    long["type_of_trade"] = long["_col"].apply(
        lambda c: "imports" if "import" in c else "exports"
    )
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

    # Keep real state rows only — drop the "Grand Total" row (state "0"), the
    # "File Generated On" footer (blank state) and any "PEN M'SIA" aggregate.
    norm_state = (
        long["state"].astype("string").str.upper()
        .str.replace(r"[^A-Z]", "", regex=True).fillna("")
    )
    long = long[~norm_state.isin(["", "PENMSIA"])]

    long["hs"] = _normalise_hs(long["hs"])
    long["country"] = long["country"].replace(_COUNTRY_ALIASES)
    long["trade_values"] = pd.to_numeric(long["trade_values"], errors="coerce")
    return long[OUTPUT_COLUMNS].reset_index(drop=True)


def transform() -> pd.DataFrame:
    """Reshape every METS file in the Drive inbox into the long target schema."""
    folder_id = get_drive_id("trade_hs", "inbox")
    if _is_placeholder(folder_id):
        logger.warning(
            "Trade HS (METS) inbox folder not configured (%s) — "
            "set trade_hs.drive_files.inbox in the registry. Skipping.",
            folder_id,
        )
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    frames: list[pd.DataFrame] = []
    for entry in list_drive_folder(folder_id):
        name = entry["name"]
        low = name.lower()
        is_excel = low.endswith((".xlsx", ".xls"))
        if not (is_excel or low.endswith(".csv")) or name.startswith("~$"):
            continue
        try:
            path = download_file_from_drive(
                entry["id"], suffix=".xlsx" if is_excel else ".csv"
            )
            df = _read_mets_file(path, is_excel)
            reshaped = _reshape_mets(df)
            if not reshaped.empty:
                frames.append(reshaped)
            logger.info("Reshaped METS file %s (%d rows)", name, len(reshaped))
        except Exception as e:
            logger.warning("Failed to process METS file %s: %s", name, e)

    if not frames:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    out = pd.concat(frames, ignore_index=True)
    out = out.drop_duplicates(
        subset=["state", "type_of_trade", "hs", "country", "month"], keep="last"
    ).reset_index(drop=True)
    logger.info("Trade HS (METS): %d rows", len(out))
    return out


def load(df: pd.DataFrame) -> None:
    """Write the commodity CSV/Parquet (month formatted yyyy/mm/dd per the PDF)."""
    if df.empty:
        return
    out = df.copy()
    out["month"] = pd.to_datetime(out["month"]).dt.strftime("%Y/%m/%d")
    write_csv(out, "penang_monthly_exim_hs_country.csv", date_tag=True)
    write_parquet(df, "penang_monthly_exim_hs_country.parquet", date_tag=True)

    # Live Tableau source ("Online Stats > Penang > Monthly"): append-only,
    # existing rows untouched; months already present are skipped.
    folder_id = get_drive_id("trade_hs", "online_stats_folder")
    if _is_placeholder(folder_id):
        logger.warning("Online Stats folder not configured — skipping live CSV append.")
        return
    append_periods_to_drive_csv(
        df, folder_id,
        "penang_monthly_exim_hs_country.csv", date_col="month",
    )


def main() -> pd.DataFrame:
    """Run full trade HS pipeline."""
    df = transform()
    load(df)
    return df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
