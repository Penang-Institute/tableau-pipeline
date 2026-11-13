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


def test_append_serialises_non_date_col_datetimes(monkeypatch):
    """A datetime column other than date_col must not reach the API as a Timestamp.

    Regression: trade's "Updated as of" stayed a pandas Timestamp because
    select_new_period_rows only formats date_col, so append_rows raised
    "Object of type Timestamp is not JSON serializable".
    """
    import json
    import pandas as pd
    from pipeline.loaders import google_sheets as gs

    captured = {}

    class FakeWS:
        def get_all_values(self):
            return [["Date", "Updated as of", "Value"],
                    ["2026-05-01", "2026-05-01", "1.0"]]

        def append_rows(self, rows, value_input_option=None):
            captured["rows"] = rows

    class FakeClient:
        def open_by_key(self, _):
            return type("S", (), {"worksheet": lambda _s, _n: FakeWS()})()

    monkeypatch.setattr(gs, "_get_gspread_client", lambda: FakeClient())

    df_new = pd.DataFrame({
        "Date": pd.to_datetime(["2026-06-01"]),
        "Updated as of": pd.to_datetime(["2026-10-14"]),
        "Value": [2.0],
    })
    gs.append_new_months_to_sheet(df_new, "sheet-id", "data", date_col="Date")

    rows = captured["rows"]
    assert rows, "expected the new month to be appended"
    # the real failure mode: must be JSON-encodable
    json.dumps(rows)
    # and must match the sheet's existing date style, not "2026-10-14 00:00:00"
    assert rows[0] == ["2026-06-01", "2026-10-14", "2.0"], rows[0]
