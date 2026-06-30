"""Trade by exit-entry point transform (DOSM JAD 12).

Ported from: tableau_data_prep/scripts/trade/prep_trade.R, then corrected to the
actual current JAD 12 layout (verified against a real publication, Jun 2026).

Semi-automated flow: Hajar downloads the monthly DOSM "Monthly External Trade
Statistics" publication and drops the raw Excel into a shared Google Drive
"inbox" folder. This transform lists that folder, reshapes the JAD 12 cross-tab
in every file into long format, unions any legacy history, and writes to the
Tableau Google Sheet. No more manual unpivoting.

Real JAD 12 layout (sheet "JAD 12"):
  - Column 0 holds BOTH state names (subtotal rows) and their exit/entry points
    (sub-rows); blank rows separate states; "JUMLAH/TOTAL" is the grand total.
  - Exports block starts at the "EKSPORT/EXPORTS" header column; its FIRST column
    is the current month's value. Imports block likewise ("IMPORT/IMPORTS").
  - The data month + year sit in the header rows under the exports column.
  Negeri Sembilan & Pahang have no separate points — the state row IS the point.

Target form: State | Date | Type of trade | Exit-entry point | Value (RM mil) |
             Updated as of   (see "2. External Trade dashboard.pdf").

Sources:
  - Google Drive inbox folder: registry trade.drive_files.inbox
  - Legacy history CSV (optional): data/trade/ (pre-inbox backfill)
Output: Google Sheet 1zw1vHUE3wkKNEs-A9FZvxfmkXAxxrmSJLuVntxCQ2lc, tab "data"
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pandas as pd

from pipeline.config.registry import get_drive_id, get_sheet_id
from pipeline.fetchers.gdrive import download_excel_from_drive, list_drive_folder
from pipeline.loaders.google_sheets import append_new_months_to_sheet

logger = logging.getLogger(__name__)

OUTPUT_SHEET_ID = get_sheet_id("trade", "output")
_PLACEHOLDER_PREFIX = "REPLACE_WITH"

STATES_UPPER = {
    "JOHOR", "KEDAH", "KELANTAN", "MELAKA", "NEGERI SEMBILAN", "PAHANG",
    "PERAK", "PERLIS", "PULAU PINANG", "SABAH", "SARAWAK", "SELANGOR",
    "TERENGGANU",
}
NS_PAHANG_UPPER = {"NEGERI SEMBILAN", "PAHANG"}
# Casing fixes applied AFTER str.title() (Python title-cases acronyms differently
# from the raw uppercase, so only genuinely irregular labels need correcting).
EXIT_ENTRY_FIXES = {"Klia, Sepang": "KLIA, Sepang", "Lain-Lain": "Others"}

OUTPUT_COLUMNS = [
    "State", "Date", "Type of trade", "Exit-entry point",
    "Value (RM mil)", "Updated as of",
]

# First-three-letters of Malay/English month names → month number.
_MONTH3 = {
    "JAN": 1, "FEB": 2, "MAC": 3, "MAR": 3, "APR": 4, "MEI": 5, "MAY": 5,
    "JUN": 6, "JUL": 7, "OGO": 8, "AUG": 8, "SEP": 9, "OKT": 10, "OCT": 10,
    "NOV": 11, "DIS": 12, "DEC": 12,
}
_MALAY_MONTHS = {
    "januari": 1, "februari": 2, "mac": 3, "april": 4, "mei": 5, "jun": 6,
    "julai": 7, "ogos": 8, "september": 9, "oktober": 10, "november": 11,
    "disember": 12,
}
_ENGLISH_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
}


def _is_placeholder(value: str) -> bool:
    return (not value) or value.startswith(_PLACEHOLDER_PREFIX)


def _is_excel(name: str) -> bool:
    lower = name.lower()
    return lower.endswith((".xlsx", ".xls")) and not name.startswith("~$")


def _parse_month(name: str) -> pd.Timestamp | None:
    """Fallback: infer the data month from a file name (sheet header preferred)."""
    stem = Path(name).stem.lower()
    m = re.search(r"(20\d{2})[_\-\s]?(0[1-9]|1[0-2])(?!\d)", stem)
    if m:
        return pd.Timestamp(year=int(m.group(1)), month=int(m.group(2)), day=1)
    m = re.search(r"(?<!\d)(0[1-9]|1[0-2])[_\-\s](20\d{2})", stem)
    if m:
        return pd.Timestamp(year=int(m.group(2)), month=int(m.group(1)), day=1)
    year_m = re.search(r"(20\d{2})", stem)
    if year_m:
        for token, num in {**_MALAY_MONTHS, **_ENGLISH_MONTHS}.items():
            if token in stem:
                return pd.Timestamp(year=int(year_m.group(1)), month=num, day=1)
    return None


def _find_jadual_sheet(sheet_names: list[str]) -> str:
    """Locate the JAD 12 sheet (JAD 14 in older files) by number in its name."""
    for token in ("12", "14"):
        for s in sheet_names:
            if token in s.replace(" ", ""):
                return s
    return sheet_names[0]


def _locate_value_columns(raw: pd.DataFrame) -> tuple[int | None, int | None]:
    """Find the monthly Exports / Imports column = first col of each block."""
    exp_col = imp_col = None
    for i in range(min(10, len(raw))):
        for j in range(raw.shape[1]):
            v = raw.iat[i, j]
            if pd.isna(v):
                continue
            s = str(v).strip().upper()
            if exp_col is None and s in ("EKSPORT", "EXPORTS"):
                exp_col = j
            if imp_col is None and s in ("IMPORT", "IMPORTS"):
                imp_col = j
    return exp_col, imp_col


def _detect_month(raw: pd.DataFrame, col: int) -> pd.Timestamp | None:
    """Read the data month + year from the header cells above the month column."""
    month = year = None
    for i in range(min(12, len(raw))):
        cell = raw.iat[i, col]
        if pd.isna(cell):
            continue
        s = str(cell).strip()
        token = s.upper()[:3]
        if token in _MONTH3:
            month = _MONTH3[token]
        m = re.fullmatch(r"(20\d{2})(?:\.0)?", s)
        if m:
            year = int(m.group(1))
    if month and year:
        return pd.Timestamp(year=year, month=month, day=1)
    return None


def _read_jad12_sheet(xls: pd.ExcelFile) -> tuple[pd.DataFrame, pd.Timestamp | None]:
    """Read the raw JAD 12 sheet into a tidy (label, exports, imports) frame.

    Returns the 3-column frame plus the month detected from the sheet header.
    """
    sheet = _find_jadual_sheet(xls.sheet_names)
    raw = pd.read_excel(xls, sheet_name=sheet, header=None)
    exp_col, imp_col = _locate_value_columns(raw)
    logger.info(
        "JAD 12 sheet '%s': exports col=%s, imports col=%s", sheet, exp_col, imp_col
    )
    month_date = _detect_month(raw, exp_col) if exp_col is not None else None
    df3 = pd.DataFrame({
        "label": raw.iloc[:, 0],
        "exports": raw.iloc[:, exp_col] if exp_col is not None else pd.NA,
        "imports": raw.iloc[:, imp_col] if imp_col is not None else pd.NA,
    })
    return df3, month_date


def _reshape_jad12(
    df3: pd.DataFrame, month_date: pd.Timestamp, updated_as_of: pd.Timestamp,
) -> pd.DataFrame:
    """Unpivot one month's JAD 12 frame into the long target schema.

    Input: a tidy frame with columns ``label`` (state OR exit/entry point in the
    raw column 0), ``exports`` and ``imports`` (the monthly values).
    Pure function (no I/O) so it can be unit-tested with an in-memory fixture.
    """
    df = df3.copy()
    df["label"] = df["label"].astype("string").str.strip()
    df = df[
        df["label"].notna()
        & (df["label"].str.len() > 0)
        & (df["label"].str.lower() != "nan")
    ].copy()
    df["exports"] = pd.to_numeric(df["exports"], errors="coerce")
    df["imports"] = pd.to_numeric(df["imports"], errors="coerce")

    # State names appear on subtotal rows; carry the state down to its points.
    is_state = df["label"].str.upper().isin(STATES_UPPER)
    df["state"] = df["label"].where(is_state).ffill()
    df = df[df["state"].notna()].copy()  # drop pre-first-state rows (JUMLAH, headers)

    is_state_row = df["label"].str.upper().isin(STATES_UPPER)
    ns_pahang = df["state"].str.upper().isin(NS_PAHANG_UPPER)
    # Keep point rows; drop per-state subtotal rows — except NS/Pahang, which have
    # no points so their state row IS the single data row.
    df = df[(~is_state_row) | ns_pahang].copy()

    df["State"] = df["state"].str.title()
    df["Exit-entry point"] = df["label"].str.title().replace(EXIT_ENTRY_FIXES)

    long = df.melt(
        id_vars=["State", "Exit-entry point"],
        value_vars=["exports", "imports"],
        var_name="Type of trade",
        value_name="Value (RM mil)",
    )
    long["Type of trade"] = long["Type of trade"].map(
        {"exports": "Export", "imports": "Import"}
    )
    long["Date"] = pd.Timestamp(month_date)
    long["Updated as of"] = pd.Timestamp(updated_as_of)
    return long[OUTPUT_COLUMNS].reset_index(drop=True)


def transform() -> pd.DataFrame:
    """Reshape every JAD 12 file in the Drive inbox into the long target schema.

    Returns only the inbox-derived rows. History lives in the output Sheet;
    load() appends just the new months, so the inbox can hold any subset of
    files (already-loaded months are skipped on append).
    """
    folder_id = get_drive_id("trade", "inbox")
    if _is_placeholder(folder_id):
        logger.warning(
            "Trade JAD 12 inbox folder not configured (%s) — "
            "set trade.drive_files.inbox in google_sheets_registry.yaml. Skipping.",
            folder_id,
        )
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    today = pd.Timestamp.today().normalize()
    frames: list[pd.DataFrame] = []
    for entry in list_drive_folder(folder_id):
        name = entry["name"]
        if not _is_excel(name):
            continue
        try:
            xls = download_excel_from_drive(entry["id"])
            df3, sheet_month = _read_jad12_sheet(xls)
            month_date = sheet_month or _parse_month(name)
            if month_date is None:
                logger.warning("Skipping trade file (cannot determine month): %s", name)
                continue
            frames.append(_reshape_jad12(df3, month_date, today))
            logger.info("Reshaped JAD 12 file %s (%s)", name, month_date.date())
        except Exception as e:
            logger.warning("Failed to process trade file %s: %s", name, e)

    reshaped = (
        pd.concat(frames, ignore_index=True)
        if frames
        else pd.DataFrame(columns=OUTPUT_COLUMNS)
    )
    logger.info("Trade by exit/entry: %d reshaped rows from inbox", len(reshaped))
    return reshaped


def load(df: pd.DataFrame) -> None:
    """Append only the new months to the trade Sheet (history preserved)."""
    if not df.empty:
        append_new_months_to_sheet(df, OUTPUT_SHEET_ID, "data", date_col="Date")


def main() -> pd.DataFrame:
    """Run full trade pipeline."""
    df = transform()
    load(df)
    return df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
