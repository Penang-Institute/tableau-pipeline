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
