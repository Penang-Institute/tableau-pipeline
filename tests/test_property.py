"""Property transform: NAPIC parsers, date handling and write safety.

Synthetic grids mimic the NAPIC sheet layouts (header=None reads). Set
NAPIC_DIR to a local copy of the four NAPIC folders (sales/prices/status/
launched) to also run the parsers over the real files.
"""

import glob
import os
import re

import pandas as pd
import pytest

from pipeline.transforms import property as prop
from pipeline.transforms import property_napic as pn


def grid(rows, width=None):
    width = width or max(len(r) for r in rows)
    return pd.DataFrame([list(r) + [None] * (width - len(r)) for r in rows])


# --- file names and labels ---------------------------------------------------

@pytest.mark.parametrize("name, expected", [
    ("2017 Q1.xlsx", "2017-01-01"),
    ("2011Q3.xlsx", "2011-07-01"),
    ("6.PULAUPINANGQ12022.xlsx", "2022-01-01"),
    ("7. JADUAL TRANSAKSI PULAU PINANG Q3 2024.xlsx", "2024-07-01"),  # R's regex missed this style
    ("Property Market Status Report - 2019Q4.xls", "2019-10-01"),
    ("1639011474224JadualStatusPasaranHartaTanahQ32021(Revise08122021).xls", "2021-07-01"),
    ("1617623718979JADUALSTATUSQ42020.xls", "2020-10-01"),
])
def test_file_quarter_reads_every_naming_style(name, expected):
    assert pn.file_quarter(name) == pd.Timestamp(expected)


def test_file_quarter_and_year_reject_names_without_a_period():
    with pytest.raises(pn.LayoutError):
        pn.file_quarter("2020 H1.xls")
    assert pn.file_year("1617631677688TheResidentialPriceYearly2020.xlsx") == 2020


def test_normalise_type_never_produces_detacheded_or_terraced():
    old = ["Single Storey Terrace", "2 -3 Storey Terrace", "2-3 Storey Semi- Detach", "Detach", "Low Cost Flat"]
    new = ["Single Storey Terraced", "2 -3 Storey Terraced", "2-3 Storey Semi- Detached", "Detached", "Low Cost Flat"]
    assert [pn.normalise_type(t) for t in old] == [pn.normalise_type(t) for t in new] == [
        "Single storey terrace", "2-3 storey terrace", "2-3 storey semi-detached", "Detached", "Low-cost flat",
    ]
    # R's broken labels in the live tab map onto the same fixed labels
    assert pn.normalise_type("2-3 storey semi-detacheded") == "2-3 storey semi-detached"
    assert pn.normalise_type("Detacheded") == "Detached"


# --- sales tables 6.1 / 6.3 ---------------------------------------------------

SALES_HEADER = ["", "Price Range", "Quarter", "Residential", "Commercial", "Industrial",
                "Agricultural", "Development", "Others", "Total"]


def sales_grid(scale=1):
    rows = [["", "Table 6.3"], [], SALES_HEADER, []]
    for price, base in (("0 - 100,000", 10), ("100,001 - 200,000", 20)):
        rows.append(["", price, "Q2 2024", *[(base + i) * scale for i in range(7)]])
        rows.append(["", "", "Q3 2024 P", *[(base + 100 + i) * scale for i in range(7)]])
    rows += [["", "Total", "", *[999] * 7], ["", "% Breakdown", "", *[1] * 7]]
    return grid(rows)


def test_sales_table_assigns_quarters_by_position_and_stops_at_total():
    out = pn.sales_table(sales_grid(), "Number")
    assert len(out) == 2 * 2 * 7
    row = out[(out["Price range"] == "100,001 - 200,000") & (out["Sub-sector"] == "Agriculture")]
    assert dict(zip(row["Date"].dt.strftime("%Y-%m-%d"), row["Number"])) == {"2024-04-01": 23, "2024-07-01": 123}
    assert 999 not in out["Number"].tolist()


def test_parse_sales_joins_count_and_value_in_ringgit():
    out = pn.parse_sales({"6.1&6.2": sales_grid(), "6.3&6.4": sales_grid(scale=0.5)})
    first = out.iloc[0]
    assert first["Number"] == 10 and first["Value (RM)"] == 5_000_000


def test_sales_table_rejects_uneven_quarter_groups():
    df = sales_grid().drop(index=5)  # drop the 2nd quarter row of the first price range
    with pytest.raises(pn.LayoutError):
        pn.sales_table(df.reset_index(drop=True), "Number")


# --- unsold status tables -----------------------------------------------------

def test_unsold_table_reads_only_the_penang_block():
    df = grid([
        ["Table 2"], [],
        ["State", "Price Range", "Single Storey Terraced", "2 -3 Storey Terrace", "Semi- Detach", "Total"],
        ["MALAYSIA"],
        ["Unit Launched", "RM0 - RM100,000", 1, 2, 3, 6],
        ["Unsold Units", None, 1, 1, 1, 3],
        ["Value (RM Milllion)", None, 0.1, 0.1, 0.1, 0.3],
        ["PULAU PINANG"],
        [None, "RM0 - RM100,000", 10, 20, 30, 60],
        [None, None, 1, 2, 3, 6],
        [None, None, 0.5, 0.6, 0.7, 1.8],
        [None, "TOTAL", 10, 20, 30, 60], [None, None, 1, 2, 3, 6], [None, None, 0.5, 0.6, 0.7, 1.8],
        ["KEDAH"],
        [None, "RM0 - RM100,000", 99, 99, 99, 99], [None, None, 99, 99, 99, 99], [None, None, 9, 9, 9, 9],
    ])
    out = pn.unsold_table(df, "Overhang").set_index("Type")
    assert sorted(out.index) == ["2-3 storey terrace", "Semi-detached", "Single storey terrace"]
    assert set(out["Price range"]) == {"0-100,000"}
    assert out.loc["Semi-detached", ["Number of units launched", "Number of unsold units",
                                     "Unsold value (RM mil)"]].tolist() == [30, 3, 0.7]


# --- newly launched -----------------------------------------------------------

LAUNCH_HEADER = ["Single Storey Terrace", "2 - 3 Storey Terrace", "Single Storey Semi-Detached",
                 "2 - 3 Storey Semi-Detached", "Detached", "Town-house", "Cluster", "Low-Cost House",
                 "Low-Cost Flat", "Flat", "Condominium/ Apartment", "Total"]


def launch_grid(header=LAUNCH_HEADER):
    def values(v):
        return [x for _ in header for x in (v, None)]  # Units, Sale Performance

    head = ["State & District", "Price Range", "Quarter & Year", None] + [x for h in header for x in (h, None)]
    return grid([
        ["Table 1.1"], head,
        ["PULAU PINANG"], ["LAUNCHED IN Q3 2024"], [None, "RM100,000 Or Less"],
        [None, None, "Q3 2024", "Unit Launched", *values(7)],
        ["Timur Laut"], ["LAUNCHED IN Q3 2024"], [None, "RM100,000 Or Less"],
        [None, None, "Q3 2024", "Unit Launched", *values(5)],
        [None, None, "Within 3 Months", "Sold Units", *values(2)],
        ["LAUNCHED WITHIN 3 QUARTERS"], [None, "RM100,000 Or Less"],
        [None, None, "Within 3 Quarters", "Sold Units", *values(9)],
    ])


def test_newly_launched_table_keeps_districts_and_quarters_only():
    out = pn.newly_launched_table(launch_grid())
    assert len(out) == 11  # one row per property type, Timur Laut only
    assert set(out["District"]) == {"Timur Laut"}
    assert set(out["Price range"]) == {"100,000 or less"}
    assert out["Date"].eq(pd.Timestamp("2024-07-01")).all()
    assert out["Newly launches"].eq(5).all() and out["Sold units (W3)"].eq(2).all()


def test_newly_launched_table_rejects_changed_type_columns():
    with pytest.raises(pn.LayoutError):
        pn.newly_launched_table(launch_grid(header=LAUNCH_HEADER[:-2] + ["Serviced Apartment", "Total"]))


# --- property.py: dates, revisions, output, write safety ----------------------

def test_sheet_dates_reads_serials_display_text_and_iso_but_rejects_junk():
    dates = prop.sheet_dates(pd.Series([44104, "Sep-20", "2024-07-01", "", None], name="Date"))
    assert dates.iloc[:3].dt.strftime("%Y-%m-%d").tolist() == ["2020-09-30", "2020-09-01", "2024-07-01"]
    assert dates.iloc[3:].isna().all()
    with pytest.raises(ValueError):
        prop.sheet_dates(pd.Series(["someday"], name="Date"))


def test_sheet_dates_rejects_numbers_that_are_not_date_serials():
    with pytest.raises(ValueError, match="not date serials"):
        prop.sheet_dates(pd.Series([2020], name="Date"))


def _folder(monkeypatch, names):
    monkeypatch.setattr(prop, "get_drive_id", lambda t, k: "folder")
    monkeypatch.setattr(prop, "list_drive_folder", lambda folder: [{"name": n, "id": n} for n in names])


def test_napic_files_refuses_two_files_for_one_quarter(monkeypatch):
    _folder(monkeypatch, ["Table 1.1 New Launches Q3 2024.xls", "Table 1.1 New Launches Q3 2024 (1).xls"])
    with pytest.raises(RuntimeError, match="same period"):
        prop.napic_files("launched", pn.file_quarter)
    assert len(prop.napic_files("launched", pn.file_quarter, allow_same_period=True)) == 2


def test_napic_files_fails_on_unknown_undated_names_but_skips_known_ones(monkeypatch):
    _folder(monkeypatch, ["2020 H1.xls", "2021 Q3.xlsx", "notes.pdf"])
    assert [n for n, _, _ in prop.napic_files("sales", pn.file_quarter)] == ["2021 Q3.xlsx"]
    _folder(monkeypatch, ["Penang Third Quarter 2024.xlsx"])
    with pytest.raises(pn.LayoutError):
        prop.napic_files("sales", pn.file_quarter)


def test_require_every_quarter_spots_a_gap():
    prop.require_every_quarter(pd.Series(pd.to_datetime(["2021-04-01", "2021-07-01"])), pd.Timestamp("2021-04-01"), "x")
    with pytest.raises(RuntimeError, match="2021-07"):
        prop.require_every_quarter(pd.Series(pd.to_datetime(["2021-04-01", "2021-10-01"])),
                                   pd.Timestamp("2021-04-01"), "x")


def test_renamed_legacy_column_fails_instead_of_writing_blanks():
    legacy = pd.DataFrame({"Updated as of": [2019], "Year": [2019], "State": ["Penang"], "Measure": ["Mean"],
                           "House price (RM per unit)": [1.0]})  # header renamed upstream
    with pytest.raises(KeyError, match="House price"):
        prop.check_legacy_columns(legacy, "house_prices")


def test_for_sheet_refuses_duplicate_rows_and_missing_columns():
    row = {"Date": pd.Timestamp("2024-07-01"), "Sub-sector": "Total", "Updated as of": "",
           "Price range": "a", "Number": 1, "Value (RM)": 1}
    with pytest.raises(ValueError, match="share a key"):
        prop.for_sheet(pd.DataFrame([row, row]), "transactions")
    with pytest.raises(KeyError, match="Value"):
        prop.for_sheet(pd.DataFrame([row]).drop(columns="Value (RM)"), "transactions")


def test_same_rows_ignores_order_but_not_values():
    a = pd.DataFrame({"k": [1, 2], "v": [0.5, None]})
    assert prop._same_rows(a, a.iloc[::-1])
    assert not prop._same_rows(a, a.assign(v=[0.6, None]))


def test_latest_keeps_newest_release_and_groups_without_one():
    df = pd.DataFrame({"Date": ["q3", "q3", "q4"], "rel": [1, 2, None], "v": ["old", "new", "only"]})
    assert prop.latest(df, ["Date"], "rel")["v"].tolist() == ["new", "only"]


def transactions(**cols):
    """Full transactions frame; override any column."""
    n = len(next(iter(cols.values()))) if cols else 1
    base = {"Date": pd.to_datetime(["2024-07-01"] * n), "Sub-sector": ["Total"] * n, "Updated as of": [""] * n,
            "Price range": [f"r{i}" for i in range(n)], "Number": [1.0] * n, "Value (RM)": [1.0] * n}
    return pd.DataFrame({**base, **cols})


def test_for_sheet_formats_dates_and_refuses_blank_dates():
    out = prop.for_sheet(transactions(Number=[3.0]), "transactions")
    assert list(out.columns) == prop.OUTPUT_COLUMNS["transactions"] and out["Date"].tolist() == ["2024-07-01"]
    with pytest.raises(ValueError):
        prop.for_sheet(transactions(Date=[pd.NaT]), "transactions")


def test_for_sheet_keeps_formula_like_text_literal():
    df = transactions(**{"Price range": ["=HYPERLINK(1)", "0 - 100,000", ""], "Number": [1.0, -2.0, 3.0]})
    out = prop.for_sheet(df, "transactions")
    assert out["Price range"].tolist() == ["'=HYPERLINK(1)", "0 - 100,000", ""]
    assert out["Number"].tolist() == [1.0, -2.0, 3.0]  # numbers untouched


def test_transform_fails_loudly_when_a_legacy_tab_cannot_be_read(monkeypatch):
    def boom(key):
        raise PermissionError("403")

    monkeypatch.setattr(prop, "read_legacy", boom)
    with pytest.raises(PermissionError):
        prop.transform()


def test_load_tries_every_sheet_then_fails(monkeypatch):
    tried = []

    def fake_write(df, sheet_id, tab, **kwargs):
        tried.append(sheet_id)
        assert kwargs == {"value_input_option": "USER_ENTERED", "max_shrink": prop.MAX_SHRINK}
        if sheet_id == prop.OUTPUT_SHEETS["transactions"]:
            raise PermissionError("403")

    monkeypatch.setattr(prop, "write_sheet", fake_write)
    with pytest.raises(RuntimeError, match="1 of 4 sheets failed: transactions"):
        prop.load({k: pd.DataFrame({"x": [1]}) for k in prop.OUTPUT_SHEETS})
    assert len(tried) == 4


def test_write_sheet_refuses_to_shrink_a_tab(monkeypatch):
    from pipeline.loaders import google_sheets as gs

    calls = []

    class FakeWS:
        def __init__(self, fail_updates=0):
            self.fail_updates = fail_updates

        def get_all_values(self):
            calls.append("read")
            return [["h"]] + [["r"]] * 100

        def clear(self):
            calls.append("clear")

        def update(self, *a, **k):
            calls.append("update")
            if self.fail_updates:
                self.fail_updates -= 1
                raise ConnectionError("503")

        def batch_clear(self, ranges):
            calls.append(("batch_clear", ranges))

    ws = FakeWS()
    sheet = type("S", (), {"worksheet": lambda _s, _n: ws})()
    monkeypatch.setattr(gs, "_get_gspread_client", lambda: type("C", (), {"open_by_key": lambda _s, _k: sheet})())
    monkeypatch.setattr(gs.time, "sleep", lambda s: None)
    with pytest.raises(gs.WriteRefused):
        gs.write_sheet(pd.DataFrame({"h": range(50)}), "id", "data", max_shrink=0.1)
    assert calls == ["read"]  # nothing cleared, nothing written

    # Safe mode never clears first: overwrite, then blank only the old leftover rows.
    calls.clear()
    gs.write_sheet(pd.DataFrame({"h": range(95)}), "id", "data", max_shrink=0.1)
    assert calls == ["read", "update", ("batch_clear", ["A97:A101"])]

    # A failed update leaves the old rows in place; retries reuse the first row count.
    calls.clear()
    ws.fail_updates = 1
    gs.write_sheet(pd.DataFrame({"h": range(95)}), "id", "data", max_shrink=0.1)
    assert calls == ["read", "update", "update", ("batch_clear", ["A97:A101"])]
    assert "clear" not in calls


def release_grid(quarters, base):
    """Sales table with one price range, one row per quarter label."""
    rows = [SALES_HEADER]
    for i, q in enumerate(quarters):
        rows.append(["", "0 - 100,000" if i == 0 else "", q, *[base + i] * 7])
    return grid(rows + [["", "Total", "", *[0] * 7]])


def test_transactions_keep_one_copy_of_a_quarter_in_two_releases(monkeypatch):
    """Regression: Q3 2023 is in the Q3 2023 and Q3 2024 releases; R kept both."""
    releases = {
        "6. JADUAL TRANSAKSI HARTA TANAH PULAU PINANG Q3 2023.xlsx": (["Q2 2023", "Q3 2023 P"], 100),
        "7. JADUAL TRANSAKSI PULAU PINANG Q3 2024.xlsx": (["Q3 2023", "Q3 2024 P"], 200),
        "6.PULAUPINANGQ12021.xls": (["Q4 2020", "Q1 2021 P"], 900),  # before the cut-off: not read
        "2020 H1.xls": (["Q2 2020"], 900),                            # no period in name: skipped
    }
    legacy = pd.DataFrame({"Updated as of": ["2021Q1"], "Date": ["Sep-20"], "Sub-sector": ["Development land"],
                           "Price range": ["0 - 50,000"], "Number": [1], "Value (RM)": [2]})
    monkeypatch.setattr(prop, "read_legacy", lambda key: legacy.copy())
    monkeypatch.setattr(prop, "list_drive_folder", lambda folder: [{"name": n, "id": n} for n in releases])
    monkeypatch.setattr(prop, "get_drive_id", lambda t, k: "folder")
    monkeypatch.setattr(prop, "require_every_quarter", lambda *a: None)  # sparse fixture; tested separately
    monkeypatch.setattr(prop, "read_sheets", lambda fid, pattern: {
        "6.1&6.2": release_grid(*releases[fid]), "6.3&6.4": release_grid(*releases[fid])})

    out = prop.for_sheet(prop.transform_transactions(), "transactions")
    per_quarter = out[out["Sub-sector"] == "Residential"].set_index("Date")["Number"]
    # Q3 2023 once, from the newer (Q3 2024) release; nothing from the skipped files.
    assert per_quarter.to_dict() == {"2023-04-01": 100, "2023-07-01": 200, "2024-07-01": 201}
    assert out.loc[0, ["Date", "Sub-sector"]].tolist() == ["2020-07-01", "Development"]  # legacy row


def test_preview_reports_removed_duplicates_additions_and_value_changes():
    from pipeline.transforms import property_preview as pv

    live = pd.DataFrame({"Date": [45108, 45108, 45200], "Sub-sector": ["Total"] * 3, "Updated as of": [""] * 3,
                         "Price range": ["a", "a", "a"], "Number": [1, 1, 3], "Value (RM)": [10.0, 10.0, 30.0]})
    new = pd.DataFrame({"Date": ["2023-07-01", "2023-10-01", "2024-01-01"], "Sub-sector": ["Total"] * 3,
                        "Updated as of": [""] * 3, "Price range": ["a", "a", "a"],
                        "Number": [1.0, 4.0, 5.0], "Value (RM)": [10.000001, 30.0, 50.0]})
    summary = pv.compare("transactions", live, new)
    assert summary == {"live": 3, "new": 3, "removed": 0, "added": 1, "dupes_removed": 1, "values_changed": 1}


def test_preview_explains_relabelled_rows(caplog):
    from pipeline.transforms import property_preview as pv

    cols = {"Date": [45200], "Status of property": ["Overhang"], "Price range": ["0-100,000"],
            "Number of units launched": [4], "Number of unsold units": [1], "Unsold value (RM mil)": [0.5]}
    live = pd.DataFrame({**cols, "Type": ["2-3 storey semi-detacheded"]})
    new = pd.DataFrame({**cols, "Date": ["2023-10-01"], "Type": ["2-3 storey semi-detached"]})
    with caplog.at_level("INFO"):
        pv.compare("unsold", live, new)
    assert "1 rows are only relabelled (1 with identical values)" in caplog.text
    assert "'2-3 storey semi-detacheded' -> '2-3 storey semi-detached'" in caplog.text


def test_preview_flags_text_in_number_columns_and_small_value_changes(caplog):
    from pipeline.transforms import property_preview as pv

    base = {"Date": ["2023-10-01"], "Status of property": ["Overhang"], "Price range": ["0-100,000"],
            "Type": ["Flat"], "Number of units launched": [4], "Number of unsold units": [1]}
    live = pd.DataFrame({**base, "Unsold value (RM mil)": ["N/A"]})
    new = pd.DataFrame({**base, "Unsold value (RM mil)": [0.205]})
    with caplog.at_level("INFO"):
        pv.compare("unsold", live, new)
    assert "live has text in number columns: {'Unsold value (RM mil)': ['N/A']}" in caplog.text

    live = pd.DataFrame({**base, "Unsold value (RM mil)": [0.2]})
    assert pv.compare("unsold", live, new)["values_changed"] == 1  # 0.2 vs 0.205 is a real change


# --- optional: real NAPIC files -------------------------------------------------

NAPIC_DIR = os.environ.get("NAPIC_DIR")


def _sheets(path, pattern):
    xl = pd.ExcelFile(path)
    return {s: pd.read_excel(xl, sheet_name=s, header=None)
            for s in xl.sheet_names if re.fullmatch(pattern, s.strip(), re.I)}


def _in_scope(folder, start, inclusive):
    for path in glob.glob(f"{NAPIC_DIR}/{folder}/*"):
        try:
            quarter = pn.file_quarter(os.path.basename(path))
        except pn.LayoutError:  # e.g. "2020 H1.xls", skipped by the transform too
            continue
        if quarter >= start if inclusive else quarter > start:
            yield path


@pytest.mark.skipif(not NAPIC_DIR, reason="set NAPIC_DIR to run against real NAPIC files")
def test_parsers_on_real_napic_files():
    for path in _in_scope("sales", prop.SALES_AFTER, inclusive=False):
        assert len(pn.parse_sales(_sheets(path, r"6\.[13](?!\d).*"))) == 231
    for path in _in_scope("status", prop.UNSOLD_FROM, inclusive=True):
        assert len(pn.parse_unsold(_sheets(path, "TABLE [246]"))) == 363
    for path in glob.glob(f"{NAPIC_DIR}/launched/*"):
        assert len(pn.newly_launched_table(_sheets(path, "PULAU PINANG")["PULAU PINANG"])) == 1815
