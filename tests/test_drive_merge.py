"""Unit test for the append-merge logic (history preservation)."""

import pandas as pd

from pipeline.loaders.drive_merge import merge_new_periods


def test_appends_only_new_month_and_preserves_history():
    # Existing live file: ISO dates, history back to 1980 (sampled).
    cur = pd.DataFrame({
        "date": ["1980-01-01", "2026-03-01", "2026-04-01"],
        "division": ["01", "01", "01"],
        "index": [10.0, 120.0, 121.0],
    })
    # Transform output: OpenDOSM range only (2010+), dd/mm/yyyy, adds May.
    new = pd.DataFrame({
        "date": ["01/04/2026", "01/05/2026"],
        "division": ["01", "01"],
        "index": [121.0, 122.0],
    })
    out = merge_new_periods(cur, new, "date")

    # Pre-2010 history kept, only May added, no duplicate April.
    assert len(out) == 4
    assert "1980-01-01" in set(out["date"])          # history preserved
    assert out["date"].tolist().count("2026-04-01") == 1  # no dup of overlap
    assert "2026-05-01" in set(out["date"])          # new month, ISO format
    assert out.iloc[-1]["index"] == 122.0


def test_never_shrinks_and_noop_when_current():
    cur = pd.DataFrame({"date": ["2026-05-01"], "division": ["01"], "index": [122.0]})
    new = pd.DataFrame({"date": ["01/05/2026"], "division": ["01"], "index": [122.0]})
    out = merge_new_periods(cur, new, "date")
    assert len(out) == len(cur)  # nothing new -> unchanged


def test_select_new_period_rows_returns_only_new_and_matches_format():
    from pipeline.loaders.drive_merge import select_new_period_rows
    cur = pd.DataFrame({
        "State": ["Johor"], "Date": ["2025-12-01"], "Value (RM mil)": [1.0],
    })
    new = pd.DataFrame({
        "State": ["Johor", "Johor"],
        "Date": ["01/12/2025", "01/01/2026"],   # dd/mm/yyyy in; Dec overlaps
        "Value (RM mil)": [1.0, 2.0],
    })
    add = select_new_period_rows(cur, new, "Date")
    assert len(add) == 1                       # only Jan 2026
    assert add.iloc[0]["Date"] == "2026-01-01"  # reformatted to cur's ISO style
    assert list(add.columns) == list(cur.columns)  # cur column order
