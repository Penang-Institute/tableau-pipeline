"""Property market statistics transform.

Migrated from: scripts/property/property.R (tableau_data_prep repo)

Processes NAPIC (National Property Information Centre) data for Penang:
- Property sales transactions (count + value) by price range and sector
- Residential house prices by state and quantile
- Unsold property status (overhang, under construction, not constructed)
- Newly launched residential units and sales performance

Like R, each output "data" tab = frozen legacy tab in the same spreadsheet
+ rows parsed from the NAPIC Excel releases (see property_napic.py) after the
cut-off where the legacy tab ends.

Sources:
  - Google Sheets: legacy tab in each output spreadsheet
  - Google Drive: NAPIC release folders (registry property.drive_files.napic_*)
Output ("data" tab, fully replaced):
  - 1U2myOOIdtLoFnbNkENOvgcvOIXkWfzc6JfGxA7_GuZ8 (transactions)
  - 1NlDArTSUDBGTnJ8H9t6e1AJbdFIQU99dyYTTUW6dWa0 (house prices)
  - 1IE2m_JUXVM2CQuXzh0L9eCvPqivr6nQq1Gvmj_0GLkw (unsold)
  - 1560AqfA5UJRVa3N5y29su3xDRy9sQxWu0ehA-AktOfA (newly launched)
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable

import pandas as pd

from pipeline.config.registry import get_drive_id, get_sheet_id
from pipeline.fetchers.gdrive import download_excel_from_drive, list_drive_folder, read_google_sheet
from pipeline.loaders.google_sheets import write_sheet
from pipeline.transforms import property_napic as napic

logger = logging.getLogger(__name__)

OUTPUT_SHEETS = {
    "transactions": get_sheet_id("property", "transactions"),
    "house_prices": get_sheet_id("property", "house_prices"),
    "unsold": get_sheet_id("property", "unsold"),
    "newly_launched": get_sheet_id("property", "newly_launched"),
}
LEGACY_TABS = {
    "transactions": "byPrice&Sector",
    "house_prices": "House price",
    "unsold": "Unsold",
    "newly_launched": "Newly launch",
}
OUTPUT_TAB = "data"
OUTPUT_COLUMNS = {
    "transactions": ["Date", "Sub-sector", "Updated as of", "Price range", "Number", "Value (RM)"],
    "house_prices": ["Updated as of", "Year", "State", "Measure", "House price"],
    "unsold": [
        "Date", "Status of property", "Price range", "Type",
        "Number of units launched", "Number of unsold units", "Unsold value (RM mil)",
    ],
    "newly_launched": [
        "Date", "District", "Property type", "Price range", "Newly launches",
        "Sold units (W3)", "Sold units (W6)", "Sold units (W9)", "Sold units (W12)",
        "Updated as of", "Data status",
    ],
}
DATE_COLUMNS = {
    "transactions": ["Date"],
    "house_prices": [],
    "unsold": ["Date"],
    "newly_launched": ["Date", "Updated as of"],
}
# NAPIC rows start where each legacy tab ends (R's cut-offs).
SALES_AFTER = pd.Timestamp("2021-03-01")   # Date > 2021 Q1
PRICES_AFTER_YEAR = 2019                    # Year > 2019
UNSOLD_FROM = pd.Timestamp("2021-04-01")   # Date >= 2021 Q2
# Expected changes vs the live tabs are a few percent (duplicate quarters
# removed); refuse any write that would drop more than this share of rows.
MAX_SHRINK = 0.10
_SHEETS_EPOCH = pd.Timestamp("1899-12-30")


# --- reading -----------------------------------------------------------------

def read_legacy(key: str) -> pd.DataFrame:
    """Legacy tab with real values: dates as serial numbers, not display text."""
    return read_google_sheet(
        OUTPUT_SHEETS[key], LEGACY_TABS[key], value_render_option="UNFORMATTED_VALUE"
    )


def sheet_dates(values: pd.Series) -> pd.Series:
    """Dates from a sheet column: serial numbers, "Sep-20" or ISO text.

    Blank cells stay blank; any other unreadable value raises, so a format
    change cannot silently blank a column again.
    """
    serial = pd.to_numeric(values, errors="coerce")
    from_serial = _SHEETS_EPOCH + pd.to_timedelta(serial // 1, unit="D")
    text = values.where(serial.isna()).map(lambda v: "" if pd.isna(v) else str(v).strip())
    from_text = pd.to_datetime(text, format="%b-%y", errors="coerce").fillna(
        pd.to_datetime(text, format="ISO8601", errors="coerce")
    )
    dates = from_serial.fillna(from_text)
    bad = text.ne("") & dates.isna()
    if bad.any():
        raise ValueError(f"Unreadable dates in {values.name!r}: {sorted(set(text[bad]))[:5]}")
    return dates


def _quarter_text(value) -> pd.Timestamp:
    """'2021Q1' style label -> quarter start (R's lubridate::yq)."""
    text = "" if pd.isna(value) else str(value).strip()
    return napic.file_quarter(text) if text else pd.NaT


def napic_files(folder_key: str, period: Callable[[str], object]) -> list[tuple[str, object, str]]:
    """(name, period, file id) for each Excel file in a NAPIC folder.

    Files whose name carries no release period (e.g. "2020 H1.xls") are
    skipped with a warning; R skipped them too.
    """
    out = []
    for f in list_drive_folder(get_drive_id("property", f"napic_{folder_key}")):
        name = f["name"]
        if not re.search(r"\.xlsx?$", name, re.I):
            continue
        try:
            out.append((name, period(name), f["id"]))
        except napic.LayoutError:
            logger.warning("Skipping NAPIC file with no release period in its name: %s", name)
    return sorted(out, key=lambda t: (t[1], t[0]))


def read_sheets(file_id: str, pattern: str) -> dict[str, pd.DataFrame]:
    """Sheets whose name fully matches pattern, read raw (header=None)."""
    xl = download_excel_from_drive(file_id)
    return {
        s: pd.read_excel(xl, sheet_name=s, header=None)
        for s in xl.sheet_names
        if re.fullmatch(pattern, s.strip(), re.I)
    }


def latest(df: pd.DataFrame, keys: list[str], by: str) -> pd.DataFrame:
    """Rows holding the newest `by` within each key group (R's slice_max).

    Ties are all kept, and groups with no `by` value at all are kept, as R did.
    """
    newest = df.groupby(keys, dropna=False)[by].transform("max")
    return df[df[by].eq(newest) | newest.isna()]


def _need(frames: list[pd.DataFrame], what: str) -> pd.DataFrame:
    if not frames:
        raise RuntimeError(f"No NAPIC files found for {what}")
    return pd.concat(frames, ignore_index=True)


# --- transforms --------------------------------------------------------------

def transform_transactions() -> pd.DataFrame:
    """Legacy byPrice&Sector + NAPIC tables 6.1/6.3 after 2021 Q1 (R lines 17-133)."""
    legacy = read_legacy("transactions")
    legacy["Sub-sector"] = legacy["Sub-sector"].replace("Development land", "Development")
    legacy["Date"] = sheet_dates(legacy["Date"]).dt.to_period("Q").dt.to_timestamp()

    frames = [
        napic.parse_sales(read_sheets(fid, r"6\.[13](?!\d).*")).assign(_release=q)
        for _, q, fid in napic_files("sales", napic.file_quarter)
        if q > SALES_AFTER  # older releases only hold quarters the legacy tab covers
    ]
    sales = _need(frames, "transactions")
    sales = latest(sales[sales["Date"] > SALES_AFTER], ["Date"], "_release")

    result = pd.concat([legacy, sales.assign(**{"Updated as of": ""})], ignore_index=True)
    logger.info("Property transactions: %d legacy + %d NAPIC rows", len(legacy), len(sales))
    return result


def transform_house_prices() -> pd.DataFrame:
    """Legacy 2015-2019 + NAPIC annual price tables after 2019 (R lines 136-186)."""
    legacy = read_legacy("house_prices").rename(columns={"House price (RM/unit)": "House price"})

    files = [f for f in napic_files("prices", napic.file_year) if f[1] > PRICES_AFTER_YEAR]
    years = [year for _, year, _ in files]
    if len(years) != len(set(years)):
        raise RuntimeError(f"More than one NAPIC price file for a year: {sorted(years)}")
    frames = [
        napic.house_price_table(next(iter(read_sheets(fid, r"Keseluruhan.*").values())), year)
        for _, year, fid in files
    ]
    prices = _need(frames, "house prices")

    result = pd.concat([legacy, prices.assign(**{"Updated as of": ""})], ignore_index=True)
    logger.info("House prices: %d legacy + %d NAPIC rows", len(legacy), len(prices))
    return result


def transform_unsold() -> pd.DataFrame:
    """NAPIC status tables from 2021 Q2 + legacy Unsold tab (R lines 188-306)."""
    legacy = read_legacy("unsold")[OUTPUT_COLUMNS["unsold"]].copy()
    legacy["Date"] = sheet_dates(legacy["Date"]).dt.to_period("Q").dt.to_timestamp()

    frames, seen = [], {}
    for name, quarter, fid in napic_files("status", napic.file_quarter):
        if quarter < UNSOLD_FROM:
            continue
        if quarter in seen:  # e.g. Q1 2023 exists as both .xls and .xlsx
            logger.info("Skipping %s: same quarter as %s", name, seen[quarter])
            continue
        seen[quarter] = name
        sheets = read_sheets(fid, "|".join(re.escape(t) for t in napic.UNSOLD_TABLES))
        frames.append(napic.parse_unsold(sheets).assign(Date=quarter))
    unsold = _need(frames, "unsold")

    result = pd.concat([unsold, legacy], ignore_index=True)
    logger.info("Unsold property: %d NAPIC + %d legacy rows", len(unsold), len(legacy))
    return result


def transform_newly_launched() -> pd.DataFrame:
    """NAPIC new-launch tables + legacy tab, newest release per cell (R lines 308-440)."""
    legacy = read_legacy("newly_launched")
    legacy = legacy.drop(columns=[c for c in legacy.columns if str(c).endswith("bound")])
    legacy["Updated as of"] = legacy["Updated as of"].map(_quarter_text)
    legacy["Date"] = sheet_dates(legacy["Date"])

    frames = [
        napic.newly_launched_table(read_sheets(fid, r"PULAU PINANG")["PULAU PINANG"])
        .assign(**{"Updated as of": quarter})
        for _, quarter, fid in napic_files("launched", napic.file_quarter)
    ]
    launched = _need(frames, "newly launched")

    keys = ["Date", "District", "Property type", "Price range"]
    result = latest(pd.concat([launched, legacy], ignore_index=True), keys, "Updated as of")
    logger.info("Newly launched: %d rows (%d NAPIC parsed, %d legacy)", len(result), len(launched), len(legacy))
    return result


TRANSFORMS = {
    "transactions": transform_transactions,
    "house_prices": transform_house_prices,
    "unsold": transform_unsold,
    "newly_launched": transform_newly_launched,
}


def for_sheet(df: pd.DataFrame, key: str) -> pd.DataFrame:
    """Output columns in the live tab's order; dates as YYYY-MM-DD text.

    Written with USER_ENTERED, so Sheets stores dates and numbers typed, as R's
    sheet_write did. Refuses blank Date cells (the earlier port blanked them all).
    """
    out = df.reindex(columns=OUTPUT_COLUMNS[key]).copy()
    for col in DATE_COLUMNS[key]:
        dates = pd.to_datetime(out[col])
        if col == "Date" and dates.isna().any():
            raise ValueError(f"property {key}: {int(dates.isna().sum())} rows have no Date")
        out[col] = dates.dt.strftime("%Y-%m-%d")
    return out


def transform() -> dict[str, pd.DataFrame]:
    """Run all property transforms. Any read or parse error fails the run."""
    return {key: for_sheet(fn(), key) for key, fn in TRANSFORMS.items()}


def load(dfs: dict[str, pd.DataFrame]) -> None:
    """Write each "data" tab; try all four, then fail if any failed."""
    failed = []
    for key, df in dfs.items():
        try:
            write_sheet(
                df, OUTPUT_SHEETS[key], OUTPUT_TAB,
                value_input_option="USER_ENTERED", max_shrink=MAX_SHRINK,
            )
        except Exception:
            logger.exception("property: writing %s failed", key)
            failed.append(key)
    if failed:
        raise RuntimeError(f"property: {len(failed)} of {len(dfs)} sheets failed: {', '.join(failed)}")


def main() -> dict[str, pd.DataFrame]:
    """Run full property pipeline."""
    dfs = transform()
    load(dfs)
    return dfs


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
