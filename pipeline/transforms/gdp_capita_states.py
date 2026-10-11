"""GDP per capita by state transform (worksheet a).

Semi-automated inbox flow: Hajar downloads the DOSM "Table of GDP by State"
publication and drops it in a Drive inbox folder. This transform reads the
**Jad 44** sheet (GDP per capita by state), reshapes it to the long target
schema, and upserts it into the by-state Sheet — preserving older years the
publication no longer covers (e.g. 2005–2014) and applying revisions to the
years it does (2015 onward).

Source : Drive inbox folder (registry gdp_capita_states.drive_files.inbox) —
         "Table of GDP by State, YYYY-YYYY.xlsx", sheet "Jad 43-44"
         (≤2024 editions) or "A22-A23" (2025+ editions, renumbered by DOSM).
Output : Google Sheet 1Ua9_28dpHeWlea9QfbkYrGSSuBtwL2pXOWobpX8A_1Q, tab "data"
         columns: State | Year | GDP per capita (RM) | GDP per capita (Malaysia)
                  | Data status | Updated as of
"""

from __future__ import annotations

import logging
import re

import pandas as pd

from pipeline.config.registry import get_drive_id, get_sheet_id
from pipeline.fetchers.gdrive import download_excel_from_drive, list_drive_folder
from pipeline.loaders.google_sheets import upsert_rows_to_sheet

logger = logging.getLogger(__name__)

OUTPUT_SHEET_ID = get_sheet_id("gdp_capita_states", "output")
_PLACEHOLDER_PREFIX = "REPLACE_WITH"

# 15 states in the GDP-per-capita table (Jad 44); Supra/total are excluded.
STATES_15 = {
    "Johor", "Kedah", "Kelantan", "Melaka", "Negeri Sembilan", "Pahang",
    "Pulau Pinang", "Perak", "Perlis", "Selangor", "Terengganu", "Sabah",
    "Sarawak", "W.P. Kuala Lumpur", "W.P. Labuan",
}
OUTPUT_COLUMNS = [
    "State", "Year", "GDP per capita (RM)", "GDP per capita (Malaysia)",
    "Data status", "Updated as of",
]

# The publication writes "W.P. ..."; the Sheet/Tableau (and the PDF spec) use
# "WP ..." — normalise so the upsert keys match and no duplicate states appear.
STATE_FIXES = {
    "W.P. Kuala Lumpur": "WP Kuala Lumpur",
    "W.P. Labuan": "WP Labuan",
}


def _is_placeholder(value: str) -> bool:
    return (not value) or value.startswith(_PLACEHOLDER_PREFIX)


def _year_cell(v) -> tuple[int, str] | None:
    """Parse a year header cell → (year, data_status). 'e'=estimate, 'p'=preliminary.

    A trailing apostrophe (e.g. "2023'") is DOSM's "revised" marker — strip it so
    the base year still parses (2025 edition tags its first year this way).
    """
    s = str(v).strip().replace(".0", "").rstrip("'’\"")
    m = re.match(r"^(20\d{2})([ep]?)$", s)
    if not m:
        return None
    return int(m.group(1)), {"e": "estimate", "p": "preliminary"}.get(m.group(2), "")


def _find_jad4344_sheet(sheet_names: list[str]) -> str | None:
    """Locate the per-capita sheet: "Jad 43-44" (≤2024 editions) or "A22-A23"
    (2025+ editions — DOSM renumbered the tables; per Hajar, Jul 2026)."""
    for s in sheet_names:
        c = s.replace(" ", "").lower()
        if ("43" in c and "44" in c) or ("a22" in c and "a23" in c):
            return s
    for s in sheet_names:
        c = s.replace(" ", "").lower()
        if "44" in c or "a23" in c:
            return s
    return None


def _reshape_jad44(raw: pd.DataFrame) -> pd.DataFrame:
    """Unpivot the Jad 44 (GDP per capita by state) block into the long schema.

    Pure function (no I/O) — unit-testable with an in-memory fixture.
    """
    def _is_marker(i: int) -> bool:
        c1 = str(raw.iat[i, 1]).strip().upper()
        c2 = str(raw.iat[i, 2]).strip().replace(".0", "").upper()
        return c1 in ("JADUAL", "TABLE") and c2 in ("44", "A23")

    def _is_percap_title(i: int) -> bool:
        text = " ".join(str(v) for v in raw.iloc[i].tolist() if pd.notna(v)).lower()
        return "per capita" in text or "per kapita" in text

    # Old editions mark the block "JADUAL 44"; 2025+ renumber it "A23".
    # Fall back to the per-capita title text if the marker style changes again.
    j44 = next((i for i in range(len(raw)) if _is_marker(i)), None)
    if j44 is None:
        j44 = next((i for i in range(len(raw)) if _is_percap_title(i)), None)
    if j44 is None:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    # The year-header row has several year cells (skip the title row that merely
    # mentions the span, e.g. "GDP per capita by state, 2015-2024").
    hdr = next(
        (i for i in range(j44, min(j44 + 12, len(raw)))
         if sum(_year_cell(raw.iat[i, j]) is not None for j in range(raw.shape[1])) >= 3),
        None,
    )
    if hdr is None:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    year_cols = {
        j: yc for j in range(raw.shape[1])
        if (yc := _year_cell(raw.iat[hdr, j])) is not None
    }

    # State names sit in the column just left of the year block, but its index
    # shifted between editions ("Jad 43-44" used col 2; the 2025 "A22-A23" block
    # is tighter, col 1). Detect it from the known state names rather than hardcode.
    first_year_col = min(year_cols)
    state_col = next(
        (j for j in range(first_year_col)
         if any(str(raw.iat[i, j]).strip() in STATES_15
                for i in range(hdr + 1, min(hdr + 40, len(raw))))),
        first_year_col - 1,
    )

    rows: list[tuple] = []
    malaysia: dict[int, float] = {}
    seen_state = False
    for i in range(hdr + 1, len(raw)):
        name = str(raw.iat[i, state_col]).strip()
        if name in STATES_15:
            seen_state = True
            for j, (yr, status) in year_cols.items():
                v = raw.iat[i, j]
                if pd.notna(v):
                    rows.append((name, yr, float(v), status))
        elif seen_state and name.lower() in ("nan", "none", "") and any(
            pd.notna(raw.iat[i, j]) for j in year_cols
        ):
            # The Malaysia total row (blank state) right after the last state.
            for j, (yr, _status) in year_cols.items():
                if pd.notna(raw.iat[i, j]):
                    malaysia[yr] = float(raw.iat[i, j])
            break

    if not rows:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    df = pd.DataFrame(rows, columns=["State", "Year", "GDP per capita (RM)", "Data status"])
    df["State"] = df["State"].replace(STATE_FIXES)
    df["GDP per capita (Malaysia)"] = df["Year"].map(malaysia)
    df["Updated as of"] = pd.Timestamp.today().year
    return df[OUTPUT_COLUMNS]


def _read_inbox() -> tuple[pd.DataFrame, list[str]]:
    """Read every publication in the GDP inbox.

    Returns (rows, unreadable): the merged rows from the files that parsed, and
    the names of files that yielded nothing (no per-capita sheet, 0 rows, or an
    error), so the caller can fail the run instead of silently carrying on.
    """
    folder_id = get_drive_id("gdp_capita_states", "inbox")
    if _is_placeholder(folder_id):
        logger.warning(
            "GDP inbox folder not configured (%s) — "
            "set gdp_capita_states.drive_files.inbox in the registry. Skipping.",
            folder_id,
        )
        return pd.DataFrame(columns=OUTPUT_COLUMNS), []

    frames: list[pd.DataFrame] = []
    unreadable: list[str] = []
    for entry in list_drive_folder(folder_id):
        name = entry["name"]
        if not name.lower().endswith((".xlsx", ".xls")) or name.startswith("~$"):
            continue
        try:
            xls = download_excel_from_drive(entry["id"])
            sheet = _find_jad4344_sheet(xls.sheet_names)
            if not sheet:
                logger.warning("No Jad 43-44 sheet in %s", name)
                unreadable.append(name)
                continue
            raw = pd.read_excel(xls, sheet_name=sheet, header=None)
            d = _reshape_jad44(raw)
            if d.empty:
                unreadable.append(name)
            else:
                frames.append(d)
            logger.info("Reshaped GDP by-state from %s: %d rows", name, len(d))
        except Exception as e:
            logger.warning("Failed to process GDP file %s: %s", name, e)
            unreadable.append(name)

    if not frames:
        return pd.DataFrame(columns=OUTPUT_COLUMNS), unreadable
    # Publication recency = the latest year it covers. Sort ascending so the
    # newest edition lands last — Drive listing order is arbitrary, and the
    # newest edition must win the keep="last" dedupe (it carries revisions).
    frames.sort(key=lambda d: int(d["Year"].max()))
    out = pd.concat(frames, ignore_index=True)
    # If multiple publications overlap, keep the newest file's value per State+Year.
    out = out.drop_duplicates(subset=["State", "Year"], keep="last").reset_index(drop=True)
    logger.info("GDP per capita states: %d rows from inbox", len(out))
    return out, unreadable


def transform() -> pd.DataFrame:
    """Read every publication in the GDP inbox and reshape its Jad 44 table."""
    return _read_inbox()[0]


def load(df: pd.DataFrame) -> None:
    """Upsert into the by-state Sheet — preserves older years, applies revisions."""
    if not df.empty:
        upsert_rows_to_sheet(df, OUTPUT_SHEET_ID, "data", key_cols=["State", "Year"])


def main() -> pd.DataFrame:
    """Run full GDP per capita pipeline.

    Loads whatever parsed, then fails if any inbox file did not: a new DOSM
    edition in a layout we cannot read used to log "0 rows" and report success,
    leaving the Sheet silently stuck at 2024 (Jul-Oct 2026).
    """
    df, unreadable = _read_inbox()
    load(df)
    if unreadable:
        raise RuntimeError(
            "GDP inbox file(s) yielded no per-capita rows: "
            + ", ".join(unreadable)
            + ". Fix the parser or remove the file from the inbox."
        )
    return df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
