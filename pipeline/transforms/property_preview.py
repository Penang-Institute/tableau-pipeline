"""Read-only dry run of the property transform: what would a write change?

Builds exactly what property.load() would write, reads each live "data" tab,
and logs a row-by-row comparison. Never writes. Manual only:
    python -m pipeline.orchestrator property_preview
(or the workflow's manual trigger with transforms=property_preview).
Run it, and read the report, before granting the service account edit access.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from pipeline.fetchers.gdrive import read_google_sheet
from pipeline.transforms import property as prop

logger = logging.getLogger(__name__)

KEYS = {
    "transactions": ["Date", "Sub-sector", "Price range", "Updated as of"],
    "house_prices": ["Year", "State", "Measure", "Updated as of"],
    "unsold": ["Date", "Status of property", "Price range", "Type"],
    "newly_launched": ["Date", "District", "Property type", "Price range"],
}
SAMPLES = 8


def _normalise(df: pd.DataFrame, key: str) -> pd.DataFrame:
    """Same columns, comparable types: dates as YYYY-MM-DD, numbers, stripped text."""
    out = df.reindex(columns=prop.OUTPUT_COLUMNS[key]).copy()
    for col in out.columns:
        if col in prop.DATE_COLUMNS[key]:
            out[col] = prop.sheet_dates(out[col].rename(col)).dt.strftime("%Y-%m-%d").fillna("")
        elif col in KEYS[key]:
            out[col] = out[col].map(lambda v: "" if pd.isna(v) else str(v).strip())
            out[col] = out[col].str.replace(r"^(\d+)\.0$", r"\1", regex=True)
        else:
            out[col] = pd.to_numeric(out[col].replace("", np.nan), errors="coerce")
    return out


def _period_counts(df: pd.DataFrame) -> str:
    period = df["Date"] if "Date" in df.columns else df["Year"]
    counts = period.value_counts().sort_index()
    return ", ".join(f"{p or '(blank)'}: {n}" for p, n in counts.items()) or "none"


def compare(key: str, before: pd.DataFrame, after: pd.DataFrame) -> dict:
    """Log and return a summary of how `after` differs from `before`."""
    keys = KEYS[key]
    values = [c for c in prop.OUTPUT_COLUMNS[key] if c not in keys]
    b, a = _normalise(before, key), _normalise(after, key)

    def log(msg: str, *args) -> None:
        logger.info("PREVIEW %s " + msg, key, *args)

    log("rows: live %d -> new %d (%+d)", len(b), len(a), len(a) - len(b))
    period = "Date" if "Date" in b.columns else "Year"
    log("blank %s: live %d, new %d", period, int(b[period].eq("").sum()), int(a[period].eq("").sum()))

    nb, na = b.groupby(keys).size(), a.groupby(keys).size()
    both = nb.index.intersection(na.index)
    dupes = nb.loc[both] - na.loc[both]
    removed = b.set_index(keys).loc[nb.index.difference(na.index)].reset_index()
    added = a.set_index(keys).loc[na.index.difference(nb.index)].reset_index()
    log("duplicate copies removed: %d rows  by period: %s", int(dupes[dupes > 0].sum()),
        _period_counts(dupes[dupes > 0].reset_index()) if (dupes > 0).any() else "-")
    if (dupes < 0).any():
        log("WARNING rows duplicated by the new data: %d", int(-dupes[dupes < 0].sum()))
    log("rows only in live (would be removed): %d  by period: %s", len(removed),
        _period_counts(removed) if len(removed) else "-")
    log("rows only in new (would be added): %d  by period: %s", len(added),
        _period_counts(added) if len(added) else "-")
    for label, rows in (("removed", removed), ("added", added)):
        for _, row in rows.head(SAMPLES).iterrows():
            log("  e.g. %s: %s", label, " | ".join(str(v) for v in row.values))

    first_b = b.drop_duplicates(keys).set_index(keys).loc[both]
    first_a = a.drop_duplicates(keys).set_index(keys).loc[both]
    changed_total = 0
    for col in values:
        x, y = first_b[col], first_a[col]
        if x.dtype == object or y.dtype == object:
            diff = x.astype(str).ne(y.astype(str))
        else:
            diff = ~(np.isclose(x, y, rtol=1e-9, atol=0.01) | (x.isna() & y.isna()))
        n = int(diff.sum())
        changed_total += n
        if n:
            log("value changes in %r: %d rows  by period: %s", col, n,
                _period_counts(diff[diff].reset_index()))
            for idx in diff[diff].index[:SAMPLES]:
                log("  e.g. %s: %s -> %s", " | ".join(map(str, idx)), x.loc[idx], y.loc[idx])
    log("rows matched: %d, values changed: %d", len(both), changed_total)
    return {"live": len(b), "new": len(a), "removed": len(removed), "added": len(added),
            "dupes_removed": int(dupes[dupes > 0].sum()), "values_changed": changed_total}


def main() -> dict:
    """Compare all four tabs. Never calls write_sheet."""
    summary = {}
    for key, fn in prop.TRANSFORMS.items():
        after = prop.for_sheet(fn(), key)
        before = read_google_sheet(
            prop.OUTPUT_SHEETS[key], prop.OUTPUT_TAB, value_render_option="UNFORMATTED_VALUE"
        )
        summary[key] = compare(key, before, after)
    logger.info("PREVIEW summary: %s", summary)
    return summary
