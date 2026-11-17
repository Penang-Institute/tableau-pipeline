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
from pipeline.transforms.property_napic import normalise_type

logger = logging.getLogger(__name__)

KEYS = prop.UNIQUE_KEYS
SAMPLES = 8
# Tight enough to catch 0.2 vs 0.205 in "Unsold value (RM mil)"; rtol absorbs
# float noise in large values such as R's RM-million x 1e6 products.
TOLERANCE = {"rtol": 1e-9, "atol": 1e-6}
# Value columns holding text, compared as text (everything else is numeric).
TEXT_VALUES = {"newly_launched": {"Data status"}}


def _text_in_numbers(df: pd.DataFrame, key: str) -> dict[str, list]:
    """Non-blank values in number columns that are not numbers (e.g. "N/A")."""
    found = {}
    for col in prop.OUTPUT_COLUMNS[key]:
        if col in KEYS[key] or col in prop.DATE_COLUMNS[key] or col in TEXT_VALUES.get(key, set()) or col not in df.columns:
            continue
        raw = df[col].map(lambda v: "" if pd.isna(v) else str(v).strip())
        bad = raw.ne("") & pd.to_numeric(raw.str.lstrip("'"), errors="coerce").isna()
        if bad.any():
            found[col] = sorted(set(raw[bad]))[:5]
    return found


def _normalise(df: pd.DataFrame, key: str) -> pd.DataFrame:
    """Same columns, comparable types: dates as YYYY-MM-DD, numbers, stripped text."""
    out = df.reindex(columns=prop.OUTPUT_COLUMNS[key]).copy()
    for col in out.columns:
        if col in prop.DATE_COLUMNS[key]:
            out[col] = prop.sheet_dates(out[col].rename(col)).dt.strftime("%Y-%m-%d").fillna("")
        elif col in KEYS[key] or col in TEXT_VALUES.get(key, set()):
            out[col] = out[col].map(lambda v: "" if pd.isna(v) else str(v).strip())
            out[col] = out[col].str.replace(r"^(\d+)\.0$", r"\1", regex=True)
        else:
            out[col] = pd.to_numeric(out[col].replace("", np.nan), errors="coerce")
    return out


def _period_counts(df: pd.DataFrame) -> str:
    period = df["Date"] if "Date" in df.columns else df["Year"]
    counts = period.value_counts().sort_index()
    return ", ".join(f"{p or '(blank)'}: {n}" for p, n in counts.items()) or "none"


def _report_relabels(log, keys, values, removed, added) -> None:
    """Explain removed/added pairs that are the same row under a fixed type label.

    R wrote labels like "Detacheded" and "terraced"; the port writes "Detached"
    and "terrace". Map the live labels the same way and check the values match.
    """
    label_col = next((c for c in ("Type", "Property type") if c in keys), None)
    if label_col is None or removed.empty or added.empty:
        return
    mapped = removed.assign(**{label_col: removed[label_col].map(normalise_type)})
    pairs = mapped.merge(added, on=keys, suffixes=("_live", "_new"))
    if pairs.empty:
        return
    same = pd.concat(
        [
            pd.Series(np.isclose(pairs[f"{c}_live"], pairs[f"{c}_new"], **TOLERANCE)
                      | (pairs[f"{c}_live"].isna() & pairs[f"{c}_new"].isna()))
            for c in values
        ],
        axis=1,
    ).all(axis=1)
    renames = sorted(set(zip(removed[label_col], mapped[label_col])) - {(x, x) for x in mapped[label_col]})
    log("of these, %d rows are only relabelled (%d with identical values): %s", len(pairs), int(same.sum()),
        "; ".join(f"{old!r} -> {new!r}" for old, new in renames))


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
    blanks = {c: (int((b[c].isna() | b[c].eq("")).sum()), int((a[c].isna() | a[c].eq("")).sum())) for c in values}
    log("blank cells per column (live, new): %s", blanks)
    for label, frame in (("live", before), ("new", after)):
        text = _text_in_numbers(frame, key)
        if text:
            log("WARNING %s has text in number columns: %s", label, text)

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
    _report_relabels(log, keys, values, removed, added)

    first_b = b.drop_duplicates(keys).set_index(keys).loc[both]
    first_a = a.drop_duplicates(keys).set_index(keys).loc[both]
    changed_total = 0
    for col in values:
        x, y = first_b[col], first_a[col]
        if x.dtype == object or y.dtype == object:
            diff = x.astype(str).ne(y.astype(str))
        else:
            diff = ~(np.isclose(x, y, **TOLERANCE) | (x.isna() & y.isna()))
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
