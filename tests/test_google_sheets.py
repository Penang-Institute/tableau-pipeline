"""Serialization safety for the Sheets loader.

Regression for the pandas-3 CI failure: astype(str) in pandas >= 3 keeps
missing values as float NaN, which the Sheets API rejects ("Out of range
float values are not JSON compliant"). dataframe_to_rows must always yield
pure JSON-safe strings, with missing values as empty cells.
"""

import math

import numpy as np
import pandas as pd

from pipeline.loaders.google_sheets import dataframe_to_rows


def test_dataframe_to_rows_is_json_safe_and_blanks_missing():
    df = pd.DataFrame({
        "state": ["Johor", None, "Penang"],
        "value": [1.5, np.nan, np.inf],
        "year": pd.array([2020, None, 2024], dtype="Int64"),
        "when": pd.to_datetime(["2024-01-01", None, "2026-07-06"]),
    })
    rows = dataframe_to_rows(df)

    flat = [v for row in rows for v in row]
    assert all(isinstance(v, str) for v in flat)          # nothing but strings
    assert not any(isinstance(v, float) and (math.isnan(v) or math.isinf(v))
                   for v in flat)                          # no raw NaN/inf
    assert rows[1][0] == "" and rows[1][1] == ""           # missing -> blank
    assert "nan" not in flat and "NaT" not in flat         # no literal junk
    assert rows[0][1] == "1.5"



def test_append_new_months_sends_json_safe_date_only_rows(monkeypatch):
    """The rows handed to the Sheets API must survive its JSON body.

    Regression: the append built rows straight from itertuples, so a Timestamp
    column raised "Object of type Timestamp is not JSON serializable" and no
    month could ever be appended to a non-empty tab. CI stayed green because
    only dataframe_to_rows was covered, not the append path that skipped it.
    """
    import json

    from pipeline.loaders import google_sheets as gs

    sent = {}

    class FakeWorksheet:
        def get_all_values(self):
            return [
                ["State", "Date", "Value (RM mil)", "Updated as of"],
                ["Pulau Pinang", "2026-05-01", "89133", "2026-06-29"],
            ]

        def append_rows(self, rows, value_input_option=None):
            json.dumps(rows, allow_nan=False)  # exactly what the API does
            sent["rows"] = rows

    class FakeClient:
        def open_by_key(self, key):
            return type("FakeSheet", (), {"worksheet": lambda _s, n: FakeWorksheet()})()

    monkeypatch.setattr(gs, "_get_gspread_client", lambda: FakeClient())

    df_new = pd.DataFrame({
        "State": ["Pulau Pinang", "Sabah"],
        "Date": pd.to_datetime(["2026-06-01", "2026-06-01"]),
        "Value (RM mil)": [74399.099412, float("nan")],
        "Updated as of": pd.to_datetime(["2026-08-21", "2026-08-21"]),
    })

    gs.append_new_months_to_sheet(df_new, "fake-sheet-id", "data")

    rows = sent["rows"]
    assert len(rows) == 2  # only the new month, May is already present
    assert rows[0][1] == "2026-06-01"  # date-only, matching the sheet's history
    assert rows[0][3] == "2026-08-21"
    assert rows[1][2] == ""  # missing value becomes a blank cell, not "nan"
