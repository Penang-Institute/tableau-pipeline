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


def test_live_csv_round_trip_keeps_zero_padded_codes():
    # An all-numeric code column ("01", "10") is parsed as int by default, which
    # strips the zero from every existing row on each append. Existing rows must
    # come back byte-identical, and appended rows must stay padded too.
    from pipeline.loaders.drive_merge import read_live_csv
    raw = (
        b"state,hs,month,trade_values\n"
        b"PULAU PINANG,01,01/06/2026,5\n"
        b"PULAU PINANG,10,01/06/2026,7\n"
    )
    cur = read_live_csv(raw)
    assert cur["hs"].tolist() == ["01", "10"]
    assert cur.to_csv(index=False).encode() == raw   # lossless for untouched rows

    new = pd.DataFrame({
        "state": ["PULAU PINANG"],
        "hs": pd.array(["01"], dtype="string"),      # what trade_hs emits
        "month": ["01/07/2026"],
        "trade_values": [9.0],
    })
    text = merge_new_periods(cur, new, "month").to_csv(index=False)
    assert "PULAU PINANG,01,01/06/2026,5\n" in text   # history stays padded
    assert "PULAU PINANG,01,01/07/2026,9.0\n" in text  # new month padded


def test_schema_drift_does_not_crash_when_live_file_has_extra_columns():
    # Live PPI file carries series/index_sa the current transform dropped.
    from pipeline.loaders.drive_merge import merge_new_periods
    cur = pd.DataFrame({
        "date": ["2025-12-01"], "index": [100.0], "series": ["abs"], "index_sa": [99.0],
    })
    new = pd.DataFrame({"date": ["01/01/2026"], "index": [101.0]})  # 2 cols only
    merged = merge_new_periods(cur, new, "date")
    assert len(merged) == 2                     # appended, not KeyError
    assert merged.iloc[1]["index"] == 101.0     # real metric preserved
    assert pd.isna(merged.iloc[1]["series"])    # dropped column NaN-filled


def test_live_csv_round_trip_keeps_na_looking_cells():
    # "NA" (Namibia) and "null" must not turn into blanks on rewrite.
    from pipeline.loaders.drive_merge import read_live_csv
    raw = b"country,month,value\nNA,01/06/2026,5\nnull,01/06/2026,7\n"
    cur = read_live_csv(raw)
    assert cur["country"].tolist() == ["NA", "null"]
    assert cur.to_csv(index=False).encode() == raw


def test_drive_md5_lookup_escapes_quotes_and_returns_checksum():
    from unittest.mock import MagicMock
    from pipeline.transforms.copy_opendosm import _get_drive_file_md5
    service = MagicMock()
    list_call = service.files.return_value.list
    list_call.return_value.execute.return_value = {"files": [{"id": "1", "md5Checksum": "abc"}]}
    assert _get_drive_file_md5(service, "drive", "folder", "it's.csv") == "abc"
    query = list_call.call_args.kwargs["q"]
    assert "name='it\\'s.csv'" in query
    list_call.return_value.execute.return_value = {"files": []}
    assert _get_drive_file_md5(service, "drive", "folder", "x.csv") is None
