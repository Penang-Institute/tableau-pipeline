"""Shared pytest fixtures for pipeline tests.

Provides reusable mock DataFrames matching the structures expected by
various pipeline transforms, plus common patching helpers.
"""

import io
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Common raw OpenDOSM population DataFrame
# ---------------------------------------------------------------------------

@pytest.fixture
def raw_population_state():
    """Minimal OpenDOSM population_state parquet-like DataFrame.

    Contains rows for Pulau Pinang and Johor with various sex/ethnicity
    combinations that many population transforms filter on.
    """
    return pd.DataFrame({
        "state": [
            "Pulau Pinang", "Pulau Pinang", "Pulau Pinang",
            "Pulau Pinang", "Johor", "Johor",
        ],
        "date": pd.to_datetime([
            "2024-01-01", "2024-01-01", "2024-01-01",
            "2024-01-01", "2024-01-01", "2024-01-01",
        ]),
        "sex": ["both", "male", "female", "both", "both", "male"],
        "age": [
            "overall", "overall", "overall",
            "overall", "overall", "overall",
        ],
        "ethnicity": [
            "overall_ethnicity", "overall_ethnicity", "overall_ethnicity",
            "bumi_malay", "overall_ethnicity", "overall_ethnicity",
        ],
        "population": [1800, 900, 900, 500, 3600, 1800],
    })


@pytest.fixture
def raw_population_district():
    """Minimal OpenDOSM population_district parquet-like DataFrame."""
    return pd.DataFrame({
        "state": [
            "Pulau Pinang", "Pulau Pinang", "Pulau Pinang",
            "Pulau Pinang",
        ],
        "district": [
            "Timur Laut", "Timur Laut", "Barat Daya", "Barat Daya",
        ],
        "date": pd.to_datetime([
            "2024-01-01", "2024-01-01", "2024-01-01", "2024-01-01",
        ]),
        "sex": ["both", "male", "both", "both"],
        "age": ["overall", "overall", "overall", "overall"],
        "ethnicity": [
            "bumi_malay", "overall_ethnicity",
            "bumi_malay", "overall_ethnicity",
        ],
        "population": [200, 600, 150, 400],
    })


# ---------------------------------------------------------------------------
# GDP mock data
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_gdp_state_excel():
    """Mock Excel DataFrame for GDP per capita state data."""
    return pd.DataFrame({
        "Year": ["2020", "2021e", "2022p"],
        "State": ["Pulau Pinang", "Pulau Pinang", "Pulau Pinang"],
        "Base Year": [2015, 2015, 2015],
        "Value RM Million": [45000.0, 46000.0, 47000.0],
    })


@pytest.fixture
def mock_gdp_malaysia_excel():
    """Mock Excel DataFrame for GDP per capita Malaysia data."""
    return pd.DataFrame({
        "Year": ["2020", "2021", "2022"],
        "GDP per capita (RM)": [42000.0, 43000.0, 44000.0],
    })


# ---------------------------------------------------------------------------
# HIS / Gross income mock data
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_hiesba_snapshot():
    """Mock HIES/BA snapshot DataFrame."""
    return pd.DataFrame({
        "date": pd.to_datetime(["2022-01-01", "2022-01-01"]),
        "state": ["Pulau Pinang", "Johor"],
        "gini": [0.35, 0.38],
        "mean": [8000, 7500],
        "median": [6000, 5800],
    })


# ---------------------------------------------------------------------------
# Labour mock data
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_labour_timeseries():
    """Mock labour time series DataFrame (simplified principal stats)."""
    return pd.DataFrame({
        "year": [2020, 2021, 2022],
        "state": ["Pulau Pinang", "Pulau Pinang", "Pulau Pinang"],
        "labour_force_000": [850.0, 860.0, 870.0],
        "employed_000": [820.0, 830.0, 840.0],
        "unemployed_000": [30.0, 30.0, 30.0],
    })


# ---------------------------------------------------------------------------
# Trade mock data
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_trade_legacy_csv():
    """Mock legacy trade CSV DataFrame."""
    return pd.DataFrame({
        "State": ["Pulau Pinang", "Pulau Pinang"],
        "Date": pd.to_datetime(["2022-01-01", "2022-02-01"]),
        "Type of trade": ["Export", "Import"],
        "Exit-entry point": ["Penang Port", "Penang Port"],
        "Value (RM mil)": [1500.0, 1200.0],
        "Updated as of": pd.to_datetime(["2022-06-01", "2022-06-01"]),
    })


# ---------------------------------------------------------------------------
# Parquet byte-buffer helper
# ---------------------------------------------------------------------------

@pytest.fixture
def parquet_bytes_factory():
    """Factory fixture to create parquet bytes from a DataFrame.

    Usage:
        buf = parquet_bytes_factory(df)
        mock_get.return_value.content = buf
    """
    def _factory(df: pd.DataFrame) -> bytes:
        buf = io.BytesIO()
        df.to_parquet(buf)
        buf.seek(0)
        return buf.read()

    return _factory


# ---------------------------------------------------------------------------
# Mock Google Drive download helper
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_excel_from_dataframes():
    """Factory fixture that creates a mock ExcelFile from a dict of DataFrames.

    Usage:
        mock_xls = mock_excel_from_dataframes({"dataset": df, "Sheet2": df2})
    """
    def _factory(sheet_dict: dict[str, pd.DataFrame]) -> pd.ExcelFile:
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            for sheet_name, df in sheet_dict.items():
                df.to_excel(writer, sheet_name=sheet_name, index=False)
        buf.seek(0)
        return pd.ExcelFile(buf)

    return _factory
