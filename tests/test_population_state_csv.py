"""The state population CSV must keep the layout Tableau was built on.

The workbook reads population_by_state_age_ethnicity_sex.csv by Drive file ID
and binds to these six lowercase columns (data spec "6. Population &
Demographics", and the R script prep_pop_opendosm.R that wrote the file until
2024). Renaming any of them breaks the next Refresh in Tableau Desktop.
"""
from unittest.mock import patch

import pandas as pd
import pytest

from pipeline.transforms.population_opendosm import (
    STATE_CSV_COLUMNS,
    to_state_csv,
    transform_state,
)


def _raw(**overrides) -> pd.DataFrame:
    base = {
        "state": ["Pulau Pinang"] * 6,
        "date": ["2024-01-01"] * 6,
        "sex": ["both", "male", "female", "both", "both", "both"],
        "age": ["overall", "0-4", "85+", "overall", "overall", "overall"],
        "ethnicity": ["overall", "bumi_malay", "other_noncitizen", "chinese", "other", "overall_ethnicity"],
        "population": [1800.5, 20.1, 3.2, 700.0, 5.5, 1800.5],
    }
    return pd.DataFrame({**base, **overrides})


def test_header_is_exactly_the_spec_columns_in_order():
    assert STATE_CSV_COLUMNS == ["state", "sex", "age", "ethnicity", "population", "year"]
    assert list(to_state_csv(_raw()).columns) == STATE_CSV_COLUMNS


def test_labels_match_the_r_output():
    out = to_state_csv(_raw())
    assert out["sex"].tolist() == ["Total", "Male", "Female", "Total", "Total", "Total"]
    assert out["age"].tolist() == ["Total", "0-4", "85+", "Total", "Total", "Total"]
    assert out["ethnicity"].tolist() == [
        "Total", "Malay", "Non-Malaysian Citizens", "Chinese", "Other", "Total",
    ]


def test_year_is_an_integer_and_population_is_untouched():
    out = to_state_csv(_raw())
    assert out["year"].tolist() == [2024] * 6
    assert pd.api.types.is_integer_dtype(out["year"])
    assert out["population"].tolist() == [1800.5, 20.1, 3.2, 700.0, 5.5, 1800.5]


def test_input_frame_is_not_mutated():
    raw = _raw()
    before = raw.copy()
    to_state_csv(raw)
    pd.testing.assert_frame_equal(raw, before)


def test_missing_source_column_fails_loudly():
    with pytest.raises(ValueError, match="ethnicity"):
        to_state_csv(_raw().drop(columns=["ethnicity"]))


def test_unparseable_date_fails_instead_of_writing_float_years():
    with pytest.raises(ValueError, match="unparseable dates"):
        to_state_csv(_raw(date=["2024-01-01"] * 5 + ["not a date"]))


def test_missing_label_stays_an_empty_cell_in_the_csv():
    out = to_state_csv(_raw(ethnicity=["overall", "bumi_malay", None, "chinese", "other", "overall"]))
    assert pd.isna(out["ethnicity"].iloc[2])
    assert out.to_csv(index=False).splitlines()[3] == "Pulau Pinang,Female,85+,,3.2,2024"


def test_csv_text_is_what_tableau_reads():
    lines = to_state_csv(_raw()).to_csv(index=False).splitlines()
    assert lines[0] == "state,sex,age,ethnicity,population,year"
    assert lines[1] == "Pulau Pinang,Total,Total,Total,1800.5,2024"


@patch("pipeline.transforms.population_opendosm.fetch_parquet")
def test_transform_state_emits_the_spec_header(mock_fetch):
    mock_fetch.return_value = _raw()
    assert list(transform_state().columns) == STATE_CSV_COLUMNS


# --- census history, 1901 to 1957 -------------------------------------------

from pipeline.transforms.population_opendosm import (  # noqa: E402
    load_census_history,
    with_census_history,
)

_KEY = ["state", "sex", "age", "ethnicity", "year"]


def test_census_history_file_is_the_144_rows_the_workbook_holds():
    hist = load_census_history()
    assert list(hist.columns) == STATE_CSV_COLUMNS
    assert len(hist) == 144
    assert sorted(hist["year"].unique()) == [1901, 1911, 1921, 1931, 1947, 1957]
    assert set(hist["age"]) == {"Total"} and set(hist["ethnicity"]) == {"Total"}
    assert "Peninsular Malaysia" in set(hist["state"])
    assert not hist.duplicated(_KEY).any()
    penang_1901 = hist[(hist["state"] == "Pulau Pinang") & (hist["sex"] == "Total") & (hist["year"] == 1901)]
    assert penang_1901["population"].tolist() == [248.207]


def test_history_is_appended_after_the_opendosm_rows():
    out = with_census_history(to_state_csv(_raw()), load_census_history())
    assert list(out.columns) == STATE_CSV_COLUMNS
    assert len(out) == 6 + 144
    assert out["year"].iloc[0] == 2024 and out["year"].iloc[-1] < 1970
    assert pd.api.types.is_integer_dtype(out["year"])


def test_history_never_overlaps_years_opendosm_covers():
    early = to_state_csv(_raw(date=["1947-01-01"] * 6))
    out = with_census_history(early, load_census_history())
    assert (out["year"] >= 1947).sum() == 6  # only the OpenDOSM rows remain for 1947 onwards
    assert set(out["year"]) == {1901, 1911, 1921, 1931, 1947}


def test_history_with_wrong_columns_fails_loudly():
    bad = load_census_history().rename(columns={"sex": "Gender"})
    with pytest.raises(ValueError, match="census history"):
        with_census_history(to_state_csv(_raw()), bad)


@patch("pipeline.transforms.population_opendosm.fetch_parquet")
def test_transform_state_includes_the_census_history(mock_fetch):
    mock_fetch.return_value = _raw()
    out = transform_state()
    assert len(out) == 6 + 144
    assert out["year"].min() == 1901
