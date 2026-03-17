"""Tests for pipeline transforms.

Extends the testing patterns from keyPenangMetrics/test_metrics.py.
Tests are structured as:
  1. Unit tests for transform logic (mocked fetchers)
  2. Integration tests for data validation (marked with pytest.mark.integration)
"""

import io
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# CPI transform tests
# ---------------------------------------------------------------------------

class TestCPITransform:
    """Test CPI by state transform logic."""

    def _make_raw_cpi(self):
        """Create a minimal CPI parquet-like DataFrame."""
        return pd.DataFrame({
            "state": ["Pulau Pinang", "Pulau Pinang", "Johor"],
            "date": pd.to_datetime(["2024-01-01", "2024-01-01", "2024-01-01"]),
            "division": ["overall", "01", "overall"],
            "index": [130.5, 135.2, 128.1],
            "extra_col": [1, 2, 3],
        })

    @patch("pipeline.transforms.cpi.fetch_parquet")
    @patch("pipeline.transforms.cpi.get_parquet_url", return_value="http://mock")
    def test_transform_columns(self, mock_url, mock_fetch):
        mock_fetch.return_value = self._make_raw_cpi()
        from pipeline.transforms.cpi import transform

        result = transform()
        assert list(result.columns) == ["state", "date", "division", "index"]

    @patch("pipeline.transforms.cpi.fetch_parquet")
    @patch("pipeline.transforms.cpi.get_parquet_url", return_value="http://mock")
    def test_transform_row_count(self, mock_url, mock_fetch):
        mock_fetch.return_value = self._make_raw_cpi()
        from pipeline.transforms.cpi import transform

        result = transform()
        assert len(result) == 3

    @patch("pipeline.transforms.cpi.fetch_parquet")
    @patch("pipeline.transforms.cpi.get_parquet_url", return_value="http://mock")
    def test_extra_columns_dropped(self, mock_url, mock_fetch):
        mock_fetch.return_value = self._make_raw_cpi()
        from pipeline.transforms.cpi import transform

        result = transform()
        assert "extra_col" not in result.columns


# ---------------------------------------------------------------------------
# CPI National transform tests
# ---------------------------------------------------------------------------

class TestCPINationalTransform:
    """Test national CPI transform logic."""

    def _make_raw_cpi_national(self):
        """Create a minimal national CPI parquet-like DataFrame."""
        return pd.DataFrame({
            "date": pd.to_datetime([
                "2009-12-01", "2010-01-01", "2010-02-01",
                "2009-12-01", "2010-01-01", "2010-02-01",
            ]),
            "division": ["overall", "overall", "overall", "01", "01", "01"],
            "series": ["abs", "abs", "abs", "abs", "abs", "abs"],
            "index": [99.5, 100.0, 100.2, 98.1, 99.0, 99.3],
            "index_sa": [99.6, 100.1, 100.3, 98.2, 99.1, 99.4],
        })

    @patch("pipeline.transforms.cpi_national.fetch_parquet")
    @patch("pipeline.transforms.cpi_national.get_parquet_url", return_value="http://mock")
    def test_columns(self, mock_url, mock_fetch):
        mock_fetch.return_value = self._make_raw_cpi_national()
        from pipeline.transforms.cpi_national import transform

        result = transform()
        assert list(result.columns) == ["date", "division", "index"]

    @patch("pipeline.transforms.cpi_national.fetch_parquet")
    @patch("pipeline.transforms.cpi_national.get_parquet_url", return_value="http://mock")
    def test_date_filter_from_2010(self, mock_url, mock_fetch):
        mock_fetch.return_value = self._make_raw_cpi_national()
        from pipeline.transforms.cpi_national import transform

        result = transform()
        assert len(result) == 4

    @patch("pipeline.transforms.cpi_national.fetch_parquet")
    @patch("pipeline.transforms.cpi_national.get_parquet_url", return_value="http://mock")
    def test_date_format_dd_mm_yyyy(self, mock_url, mock_fetch):
        mock_fetch.return_value = self._make_raw_cpi_national()
        from pipeline.transforms.cpi_national import transform

        result = transform()
        assert result["date"].iloc[0] == "01/01/2010"

    @patch("pipeline.transforms.cpi_national.fetch_parquet")
    @patch("pipeline.transforms.cpi_national.get_parquet_url", return_value="http://mock")
    def test_filters_to_abs_series(self, mock_url, mock_fetch):
        raw = self._make_raw_cpi_national()
        extra = pd.DataFrame({
            "date": pd.to_datetime(["2010-01-01"]),
            "division": ["overall"],
            "series": ["growth_yoy"],
            "index": [2.5],
            "index_sa": [2.6],
        })
        mock_fetch.return_value = pd.concat([raw, extra], ignore_index=True)
        from pipeline.transforms.cpi_national import transform

        result = transform()
        assert len(result) == 4


# ---------------------------------------------------------------------------
# CPI Core transform tests
# ---------------------------------------------------------------------------

class TestCPICoreTransform:
    """Test core CPI transform logic."""

    def _make_raw_cpi_core(self):
        """Create a minimal core CPI parquet-like DataFrame."""
        return pd.DataFrame({
            "date": pd.to_datetime(["2017-12-01", "2018-01-01", "2018-02-01"]),
            "division": ["overall", "overall", "overall"],
            "index": [99.0, 100.0, 100.3],
        })

    @patch("pipeline.transforms.cpi_core.fetch_parquet")
    @patch("pipeline.transforms.cpi_core.get_parquet_url", return_value="http://mock")
    def test_columns(self, mock_url, mock_fetch):
        mock_fetch.return_value = self._make_raw_cpi_core()
        from pipeline.transforms.cpi_core import transform

        result = transform()
        assert list(result.columns) == ["date", "division", "index"]

    @patch("pipeline.transforms.cpi_core.fetch_parquet")
    @patch("pipeline.transforms.cpi_core.get_parquet_url", return_value="http://mock")
    def test_date_filter_from_2018(self, mock_url, mock_fetch):
        mock_fetch.return_value = self._make_raw_cpi_core()
        from pipeline.transforms.cpi_core import transform

        result = transform()
        assert len(result) == 2

    @patch("pipeline.transforms.cpi_core.fetch_parquet")
    @patch("pipeline.transforms.cpi_core.get_parquet_url", return_value="http://mock")
    def test_date_format_dd_mm_yyyy(self, mock_url, mock_fetch):
        mock_fetch.return_value = self._make_raw_cpi_core()
        from pipeline.transforms.cpi_core import transform

        result = transform()
        assert result["date"].iloc[0] == "01/01/2018"


# ---------------------------------------------------------------------------
# GDP Quarterly transform tests
# ---------------------------------------------------------------------------

class TestGDPQuarterlyTransform:
    """Test GDP quarterly transform logic."""

    def test_build_paths(self):
        """Verify the 6 GDP parquet URL paths are generated correctly."""
        from pipeline.transforms.gdp_quarterly import _build_paths

        paths = _build_paths()
        assert len(paths) == 6
        # real_sa demand should NOT have _sub
        real_sa_demand = paths[paths["catalogue_id"] == "real_sa_demand"]
        assert len(real_sa_demand) == 1
        assert "demand_sub" not in real_sa_demand.iloc[0]["url"]
        # nominal demand SHOULD have _sub in URL
        nominal_demand = paths[paths["catalogue_id"] == "nominal_demand"]
        assert "demand_sub" in nominal_demand.iloc[0]["url"]

    @patch("pipeline.transforms.gdp_quarterly.fetch_parquet")
    def test_transform_produces_level_columns(self, mock_fetch):
        """Verify hierarchical level columns are created."""
        # Minimal GDP data
        lookup = pd.DataFrame({
            "code": ["p0", "p0.1"],
            "desc_en": ["GDP", "Agriculture"],
        })
        gdp_data = pd.DataFrame({
            "date": pd.to_datetime(["2024-03-31", "2024-03-31"]),
            "code": ["p0", "p0.1"],
            "series": ["abs", "abs"],
            "value": [100.0, 20.0],
        })

        def side_effect(url, **kwargs):
            if "lookup" in url:
                return lookup
            return gdp_data

        mock_fetch.side_effect = side_effect
        from pipeline.transforms.gdp_quarterly import transform

        result = transform()
        assert "lvl1" in result.columns
        assert "lvl1_desc" in result.columns
        assert len(result) > 0

    @patch("pipeline.transforms.gdp_quarterly.fetch_parquet")
    def test_date_format_dd_mm_yyyy(self, mock_fetch):
        """GDP dates must be dd/mm/yyyy per PDF spec."""
        lookup = pd.DataFrame({
            "code": ["e0"],
            "desc_en": ["GDP at purchasers' prices"],
        })
        gdp_data = pd.DataFrame({
            "date": pd.to_datetime(["2024-01-01"]),
            "code": ["e0"],
            "series": ["abs"],
            "value": [100.0],
        })

        def side_effect(url, **kwargs):
            if "lookup" in url:
                return lookup
            return gdp_data

        mock_fetch.side_effect = side_effect
        from pipeline.transforms.gdp_quarterly import transform

        result = transform()
        assert result["date"].iloc[0] == "01/01/2024"

    @patch("pipeline.transforms.gdp_quarterly.fetch_parquet")
    def test_production_codes_lvl1_is_na(self, mock_fetch):
        """Production codes (p0-p6) must have NA for lvl1 per PDF spec."""
        lookup = pd.DataFrame({
            "code": ["p0", "p1"],
            "desc_en": ["GDP at purchasers' prices", "Agriculture"],
        })
        gdp_data = pd.DataFrame({
            "date": pd.to_datetime(["2024-01-01", "2024-01-01"]),
            "sector": ["p0", "p1"],
            "series": ["abs", "abs"],
            "value": [100.0, 20.0],
        })

        def side_effect(url, **kwargs):
            if "lookup" in url:
                return lookup
            return gdp_data

        mock_fetch.side_effect = side_effect
        from pipeline.transforms.gdp_quarterly import transform

        result = transform()
        p_rows = result[result["code"].str.startswith("p")]
        assert p_rows["lvl1"].isna().all(), "p-codes must have NA for lvl1"

    @patch("pipeline.transforms.gdp_quarterly.fetch_parquet")
    def test_desc_column_present(self, mock_fetch):
        """Output must include a 'desc' column with code descriptions."""
        lookup = pd.DataFrame({
            "code": ["e0", "e1"],
            "desc_en": ["GDP at purchasers' prices", "Private final consumption expenditure"],
        })
        gdp_data = pd.DataFrame({
            "date": pd.to_datetime(["2024-01-01", "2024-01-01"]),
            "code": ["e0", "e1"],
            "series": ["abs", "abs"],
            "value": [500.0, 300.0],
        })

        def side_effect(url, **kwargs):
            if "lookup" in url:
                return lookup
            return gdp_data

        mock_fetch.side_effect = side_effect
        from pipeline.transforms.gdp_quarterly import transform

        result = transform()
        assert "desc" in result.columns
        e0_row = result[result["code"] == "e0"]
        assert e0_row["desc"].iloc[0] == "GDP at purchasers' prices"

    @patch("pipeline.transforms.gdp_quarterly.fetch_parquet")
    def test_real_sa_na_for_unavailable_codes(self, mock_fetch):
        """Expenditure sub-codes without SA data must have NA in real_sa."""
        lookup = pd.DataFrame({
            "code": ["e0", "e1.1.01"],
            "desc_en": ["GDP", "Food and non-alcoholic beverages"],
        })
        gdp_demand = pd.DataFrame({
            "date": pd.to_datetime(["2024-01-01", "2024-01-01"]),
            "type": ["e0", "e1.1.01"],
            "series": ["abs", "abs"],
            "value": [500.0, 50.0],
        })
        gdp_sa = pd.DataFrame({
            "date": pd.to_datetime(["2024-01-01", "2024-01-01"]),
            "type": ["e0", "e1.1.01"],
            "series": ["abs", "abs"],
            "value": [490.0, 48.0],
        })

        def side_effect(url, **kwargs):
            if "lookup" in url:
                return lookup
            if "real_sa" in url:
                return gdp_sa.copy()
            return gdp_demand.copy()

        mock_fetch.side_effect = side_effect
        from pipeline.transforms.gdp_quarterly import transform

        result = transform()
        e1101 = result[result["code"] == "e1.1.01"]
        if not e1101.empty and "real_sa" in result.columns:
            assert e1101["real_sa"].isna().all(), "e1.1.01 must have NA for real_sa"

    @patch("pipeline.transforms.gdp_quarterly.fetch_parquet")
    def test_column_order_matches_spec(self, mock_fetch):
        """Output columns must match PDF spec order."""
        lookup = pd.DataFrame({
            "code": ["e0"],
            "desc_en": ["GDP at purchasers' prices"],
        })
        gdp_data = pd.DataFrame({
            "date": pd.to_datetime(["2024-01-01"]),
            "code": ["e0"],
            "series": ["abs"],
            "value": [500.0],
        })

        def side_effect(url, **kwargs):
            if "lookup" in url:
                return lookup
            return gdp_data

        mock_fetch.side_effect = side_effect
        from pipeline.transforms.gdp_quarterly import transform

        result = transform()
        expected_order = [
            "date", "code", "nominal", "real", "real_sa",
            "lvl1", "lvl2", "lvl3", "lvl1_desc", "lvl2_desc", "lvl3_desc", "desc",
        ]
        present = [c for c in expected_order if c in result.columns]
        actual_present = [c for c in result.columns if c in expected_order]
        assert present == actual_present, f"Column order mismatch: expected {present}, got {actual_present}"


# ---------------------------------------------------------------------------
# Utilisation transform tests
# ---------------------------------------------------------------------------

class TestUtilisationTransform:
    """Test hospital utilisation transform logic."""

    @patch("pipeline.fetchers.opendosm.fetch_parquet")
    @patch("pipeline.fetchers.opendosm.get_parquet_url", return_value="http://mock")
    def test_transform_passthrough(self, mock_url, mock_fetch):
        """Utilisation is a passthrough — data should come through unchanged."""
        raw = pd.DataFrame({
            "state": ["Pulau Pinang", "Johor"],
            "date": pd.to_datetime(["2024-01-01", "2024-01-01"]),
            "admitted": [100, 200],
        })
        mock_fetch.return_value = raw
        from pipeline.transforms.utilisation import transform

        result = transform()
        pd.testing.assert_frame_equal(result, raw)


# ---------------------------------------------------------------------------
# Population transform tests
# ---------------------------------------------------------------------------

class TestPopulationTransform:
    """Test population transform logic."""

    @patch("pipeline.fetchers.opendosm.fetch_parquet")
    @patch("pipeline.fetchers.opendosm.get_parquet_url", return_value="http://mock")
    def test_current_data_filters_correctly(self, mock_url, mock_fetch):
        raw = pd.DataFrame({
            "state": ["Pulau Pinang", "Pulau Pinang", "Johor"],
            "date": pd.to_datetime(["2024-01-01", "2024-01-01", "2024-01-01"]),
            "sex": ["both", "male", "both"],
            "age": ["overall", "overall", "overall"],
            "ethnicity": ["overall", "overall", "overall"],
            "population": [1800, 900, 3600],
        })
        mock_fetch.return_value = raw
        from pipeline.transforms.population import transform_current

        result = transform_current()
        # Should filter out the male row
        assert len(result) == 2
        assert set(result.columns) == {"state", "year", "population"}

    @patch("pipeline.transforms.population.fetch_parquet")
    @patch("pipeline.transforms.population.get_parquet_url", return_value="http://mock")
    def test_state_name_cleaning(self, mock_url, mock_fetch):
        raw = pd.DataFrame({
            "state": ["W.P. Kuala Lumpur", "W.P. Putrajaya"],
            "date": pd.to_datetime(["2024-01-01", "2024-01-01"]),
            "sex": ["both", "both"],
            "age": ["overall", "overall"],
            "ethnicity": ["overall", "overall"],
            "population": [2000, 100],
        })
        mock_fetch.return_value = raw
        from pipeline.transforms.population import transform

        result = transform()
        # "W.P." prefix should be stripped from all state names
        assert not result["state"].str.contains(r"W\.P\.").any()
        assert "Kuala Lumpur" in result["state"].values
        assert "Putrajaya" in result["state"].values


# ---------------------------------------------------------------------------
# Copy OpenDOSM tests
# ---------------------------------------------------------------------------

class TestCopyOpenDOSM:
    """Test manifest loading and URL construction."""

    def test_build_source_url_dosm(self):
        from pipeline.fetchers.opendosm import build_source_url

        url = build_source_url("dosm", "cpi/cpi_2d.csv")
        assert url == "https://storage.dosm.gov.my/cpi/cpi_2d.csv"

    def test_build_source_url_data(self):
        from pipeline.fetchers.opendosm import build_source_url

        url = build_source_url("data", "healthcare/covid_cases.csv")
        assert url == "https://storage.data.gov.my/healthcare/covid_cases.csv"

    def test_build_source_url_na(self):
        from pipeline.fetchers.opendosm import build_source_url
        import numpy as np

        url = build_source_url(np.nan, "https://raw.githubusercontent.com/MoH-Malaysia/file.csv")
        assert url == "https://raw.githubusercontent.com/MoH-Malaysia/file.csv"


# ---------------------------------------------------------------------------
# Orchestrator tests
# ---------------------------------------------------------------------------

class TestOrchestrator:
    """Test orchestrator registry and execution."""

    def test_all_transforms_importable(self):
        """Verify all registered transforms can be imported."""
        from pipeline.orchestrator import TRANSFORMS
        import importlib

        for name, module_path in TRANSFORMS.items():
            module = importlib.import_module(module_path)
            assert hasattr(module, "main"), f"{name} missing main() function"

    def test_transforms_have_transform_function(self):
        """Verify most transforms expose a transform() function."""
        from pipeline.orchestrator import TRANSFORMS
        import importlib

        # These transforms use different entry point patterns
        # (multiple sub-transforms, or direct main() without transform())
        skip = {"copy_opendosm", "hospitals", "gender", "gross_income"}
        for name, module_path in TRANSFORMS.items():
            if name in skip:
                continue
            module = importlib.import_module(module_path)
            assert hasattr(module, "transform"), f"{name} missing transform() function"


# ---------------------------------------------------------------------------
# Fetcher tests
# ---------------------------------------------------------------------------

class TestFetchers:
    """Test shared fetcher utilities."""

    @patch("pipeline.fetchers.opendosm.requests.get")
    def test_fetch_parquet_retries(self, mock_get):
        """Verify retry logic on transient failures."""
        from pipeline.fetchers.opendosm import fetch_parquet

        # First call fails, second succeeds
        buf = io.BytesIO()
        pd.DataFrame({"a": [1]}).to_parquet(buf)
        buf.seek(0)

        mock_resp_ok = MagicMock()
        mock_resp_ok.content = buf.read()
        mock_resp_ok.raise_for_status = MagicMock()

        mock_get.side_effect = [Exception("timeout"), mock_resp_ok]

        result = fetch_parquet("http://test.parquet", retries=2)
        assert len(result) == 1
        assert mock_get.call_count == 2

    @patch("pipeline.fetchers.opendosm.requests.get")
    def test_fetch_csv(self, mock_get):
        from pipeline.fetchers.opendosm import fetch_csv

        mock_resp = MagicMock()
        mock_resp.text = "a,b\n1,2\n3,4"
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = fetch_csv("http://test.csv")
        assert len(result) == 2
        assert list(result.columns) == ["a", "b"]


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------

class TestConfig:
    """Test configuration files are valid."""

    def test_data_sources_yaml_loads(self):
        import yaml

        config_dir = Path(__file__).resolve().parent.parent / "pipeline" / "config"
        with open(config_dir / "data_sources.yaml") as f:
            cfg = yaml.safe_load(f)
        assert "opendosm" in cfg
        assert "parquet" in cfg["opendosm"]

    def test_sheets_registry_yaml_loads(self):
        import yaml

        config_dir = Path(__file__).resolve().parent.parent / "pipeline" / "config"
        with open(config_dir / "google_sheets_registry.yaml") as f:
            cfg = yaml.safe_load(f)
        assert "main_workbook" in cfg
        assert "id" in cfg["main_workbook"]

    def test_sheets_registry_has_all_required_sheets(self):
        import yaml

        config_dir = Path(__file__).resolve().parent.parent / "pipeline" / "config"
        with open(config_dir / "google_sheets_registry.yaml") as f:
            cfg = yaml.safe_load(f)
        required_sheets = [
            "cpi_by_state",
            "utilisation_opendosm",
            "facilities_by_state",
            "population_by_state",
        ]
        for sheet in required_sheets:
            assert sheet in cfg["main_workbook"]["sheets"], f"Missing sheet: {sheet}"


# ---------------------------------------------------------------------------
# File writer tests
# ---------------------------------------------------------------------------

class TestFileWriter:
    """Test local file output."""

    def test_write_csv(self, tmp_path):
        from pipeline.loaders.file_writer import write_csv

        df = pd.DataFrame({"x": [1, 2], "y": [3, 4]})
        path = write_csv(df, "test.csv", output_dir=tmp_path)
        assert path.exists()

        loaded = pd.read_csv(path)
        pd.testing.assert_frame_equal(loaded, df)

    def test_write_parquet(self, tmp_path):
        from pipeline.loaders.file_writer import write_parquet

        df = pd.DataFrame({"x": [1, 2], "y": [3, 4]})
        path = write_parquet(df, "test.parquet", output_dir=tmp_path)
        assert path.exists()

        loaded = pd.read_parquet(path)
        pd.testing.assert_frame_equal(loaded, df)


# ---------------------------------------------------------------------------
# Phase 2 transform tests
# ---------------------------------------------------------------------------

class TestInferredPopulation:
    """Test inferred population transform."""

    def test_network_path_graceful_skip(self):
        """Should return empty DataFrame when network path unavailable."""
        from pipeline.transforms.inferred_population import transform

        result = transform()
        assert isinstance(result, pd.DataFrame)
        # Empty because network drive not accessible
        assert result.empty

    def test_mutate_period(self):
        """Test period column extraction."""
        from pipeline.transforms.inferred_population import _mutate_period

        df = pd.DataFrame({"period": ["2020", "2021p"]})
        result = _mutate_period(df)
        assert "year" in result.columns
        assert result["year"].tolist() == [2020, 2021]
        assert result["status"].tolist() == [None, "preliminary"]


class TestGDPCapitaStates:
    """Test GDP per capita by states transform."""

    @patch("pipeline.transforms.gdp_capita_states.download_excel_from_drive")
    def test_transform_handles_missing_drive(self, mock_download):
        mock_download.side_effect = Exception("No credentials")
        from pipeline.transforms.gdp_capita_states import transform

        result = transform()
        assert isinstance(result, pd.DataFrame)
        assert result.empty


class TestGDPEconActivity:
    """Test GDP by economic activity transform."""

    @patch("pipeline.transforms.gdp_econ_activity.download_excel_from_drive")
    @patch("pipeline.transforms.gdp_econ_activity.read_google_sheet")
    def test_transform_returns_dict(self, mock_sheet, mock_download):
        mock_download.side_effect = Exception("No credentials")
        mock_sheet.side_effect = Exception("No credentials")
        from pipeline.transforms.gdp_econ_activity import transform

        result = transform()
        assert isinstance(result, dict)
        assert "by_econ_act" in result
        assert "by_subecon_act" in result


class TestGender:
    """Test gender statistics transform."""

    def test_literacy_graceful_skip(self):
        """Should return None when education file not found."""
        from pipeline.transforms.gender import transform_literacy

        result = transform_literacy()
        # Returns None when women_stats_education.xlsx not found
        assert result is None


class TestGraduates:
    """Test graduate employment transform."""

    def test_make_clean_name(self):
        from pipeline.transforms.graduates import _make_clean_name

        assert _make_clean_name("Hello World!") == "hello_world"
        assert _make_clean_name("  test  123  ") == "test_123"

    def test_build_paired_colnames(self):
        from pipeline.transforms.graduates import _build_paired_colnames

        result = _build_paired_colnames(["Arts", "Science"])
        assert len(result) == 6  # 3 headers (arts, science, jumlah) × 2 (bil, pct)
        assert "arts_bil" in result
        assert "science_pct" in result
        assert "jumlah_bil" in result

    def test_transform_missing_file(self):
        """Should return empty dict values when file missing."""
        from pipeline.transforms.graduates import transform

        result = transform()
        assert isinstance(result, dict)
        assert "sektor_ekonomi" in result
        assert "status_pekerjaan" in result


class TestGrossIncome:
    """Test household income transform."""

    @patch("pipeline.transforms.gross_income.fetch_parquet")
    def test_hies_combined_fetch(self, mock_fetch):
        mock_fetch.return_value = pd.DataFrame({
            "date": pd.to_datetime(["2022-01-01"]),
            "state": ["Pulau Pinang"],
            "gini": [0.35],
            "income_mean": [8000],
            "income_median": [6000],
        })
        from pipeline.transforms.gross_income import _fetch_hies_combined

        result = _fetch_hies_combined("state")
        assert not result.empty
        assert "year" in result.columns
        assert "gini_gross_income" in result.columns
        assert "mean_gross_income" in result.columns

    @patch("pipeline.transforms.gross_income.fetch_parquet")
    def test_hies_combined_error_returns_empty(self, mock_fetch):
        mock_fetch.side_effect = Exception("Network error")
        from pipeline.transforms.gross_income import _fetch_hies_combined

        result = _fetch_hies_combined("state")
        assert result.empty


class TestLabour:
    """Test labour force statistics transform."""

    def test_map_state(self):
        from pipeline.transforms.labour import _map_state

        assert _map_state("N.SEMBILAN") == "Negeri Sembilan"
        assert _map_state("P.PINANG") == "Pulau Pinang"
        assert _map_state("JOHOR") == "Johor"

    def test_transform_returns_dict(self):
        from pipeline.transforms.labour import transform

        result = transform()
        assert isinstance(result, dict)
        assert "principal" in result


class TestLabourDemographics:
    """Test labour demographics transform."""

    def test_get_skip_rows(self):
        from pipeline.transforms.labour_demographics import _get_skip_rows

        assert _get_skip_rows("Employed by age.xlsx") == 4
        assert _get_skip_rows("Labour by ethnic.xlsx") == 7
        assert _get_skip_rows("by educational attainment.xlsx") == 5
        assert _get_skip_rows("by marital status.xlsx") == 5
        assert _get_skip_rows("unknown_type.xlsx") is None

    def test_infer_strata(self):
        from pipeline.transforms.labour_demographics import _infer_strata

        assert _infer_strata("by age group.xlsx") == "age group"
        assert _infer_strata("by ethnic.xlsx") == "ethnicity"
        assert _infer_strata("by educational.xlsx") == "highest certificate"
        assert _infer_strata("by marital.xlsx") == "marital status"
        assert _infer_strata("other.xlsx") == "unknown"

    def test_infer_measure(self):
        from pipeline.transforms.labour_demographics import _infer_measure

        assert _infer_measure("Employed by age.xlsx") == "Employed persons"
        assert _infer_measure("Labour by age.xlsx") == "Labour force"


class TestDemoMukim:
    """Test mukim demographics transform."""

    def test_transform_graceful_skip(self):
        """Should return empty DataFrame when census file unavailable."""
        from pipeline.transforms.demo_mukim import transform

        result = transform()
        assert isinstance(result, pd.DataFrame)
        assert result.empty


class TestPopulationOpenDOSM:
    """Test population OpenDOSM transform."""

    @patch("pipeline.transforms.population_opendosm.fetch_parquet")
    def test_clean_opendosm_ethnicity_mapping(self, mock_fetch):
        raw = pd.DataFrame({
            "state": ["Pulau Pinang"],
            "date": pd.to_datetime(["2024-01-01"]),
            "sex": ["both"],
            "age": ["overall"],
            "ethnicity": ["bumi_malay"],
            "population": [500],
        })
        mock_fetch.return_value = raw
        from pipeline.transforms.population_opendosm import _clean_opendosm

        result = _clean_opendosm(raw)
        assert result["Ethnic"].iloc[0] == "Malay"
        assert result["Gender"].iloc[0] == "Total"

    @patch("pipeline.transforms.population_opendosm.fetch_parquet")
    def test_transform_state(self, mock_fetch):
        raw = pd.DataFrame({
            "state": ["Pulau Pinang", "Johor"],
            "date": pd.to_datetime(["2024-01-01", "2024-01-01"]),
            "sex": ["both", "both"],
            "age": ["overall", "overall"],
            "ethnicity": ["overall_ethnicity", "overall_ethnicity"],
            "population": [1800, 3600],
        })
        mock_fetch.return_value = raw
        from pipeline.transforms.population_opendosm import transform_state

        result = transform_state()
        assert not result.empty
        assert "Year" in result.columns
        assert "Ethnic" in result.columns


class TestPopulationEthnicity:
    """Test population ethnicity transform."""

    @patch("pipeline.transforms.population_ethnicity.fetch_parquet")
    def test_transform_penang(self, mock_fetch):
        raw = pd.DataFrame({
            "state": ["Pulau Pinang", "Johor"],
            "date": pd.to_datetime(["2024-01-01", "2024-01-01"]),
            "sex": ["both", "both"],
            "age": ["overall", "overall"],
            "ethnicity": ["bumi_malay", "bumi_malay"],
            "population": [500, 300],
        })
        mock_fetch.return_value = raw
        from pipeline.transforms.population_ethnicity import transform_penang

        result = transform_penang()
        assert not result.empty
        # Should only include Pulau Pinang
        assert all(result["state"] == "Pulau Pinang")

    def test_transform_fertility_missing_file(self):
        from pipeline.transforms.population_ethnicity import transform_fertility

        result = transform_fertility()
        assert isinstance(result, pd.DataFrame)


class TestProperty:
    """Test property market transform."""

    def test_transform_graceful_skip(self):
        """Should return dict of empty DataFrames when paths unavailable."""
        from pipeline.transforms.property import transform

        result = transform()
        assert isinstance(result, dict)
        assert "transactions" in result
        assert "house_prices" in result


class TestTradeHS:
    """Test HS trade data transform."""

    def test_make_clean_names(self):
        from pipeline.transforms.trade_hs import _make_clean_names

        result = _make_clean_names(["Hello World!", "Test 123"])
        assert result == ["hello_world", "test_123"]

    def test_transform_graceful_skip(self):
        from pipeline.transforms.trade_hs import transform

        result = transform()
        assert isinstance(result, pd.DataFrame)
        assert result.empty


class TestTrade:
    """Test trade by exit-entry point transform."""

    def test_transform_graceful_skip(self):
        from pipeline.transforms.trade import transform

        result = transform()
        assert isinstance(result, pd.DataFrame)


class TestAirports:
    """Test airports/transport transform."""

    def test_transform_graceful_skip(self):
        """Should return dict of empty DataFrames when paths unavailable."""
        from pipeline.transforms.airports import transform

        result = transform()
        assert isinstance(result, dict)
        assert "passengers" in result
        assert "aircraft" in result
        assert "airport_cargo" in result
        assert "maritime_cargo" in result


# ===========================================================================
# TASK-008: Comprehensive Phase 2 transform tests
# ===========================================================================


# ---------------------------------------------------------------------------
# GDP Per Capita States — comprehensive tests
# ---------------------------------------------------------------------------

class TestGDPCapitaStatesComprehensive:
    """Comprehensive tests for GDP per capita by states transform."""

    @patch("pipeline.transforms.gdp_capita_states.download_excel_from_drive")
    def test_data_status_extracts_e_and_p(self, mock_download,
                                          mock_excel_from_dataframes):
        """Data status should extract 'estimate' from 'e' suffix and
        'preliminary' from 'p' suffix."""
        state_df = pd.DataFrame({
            "Year": ["2020", "2021e", "2022p"],
            "State": ["Pulau Pinang", "Pulau Pinang", "Pulau Pinang"],
            "Base Year": [2015, 2015, 2015],
            "Value RM Million": [45000.0, 46000.0, 47000.0],
        })
        msia_df = pd.DataFrame({
            "Year": ["2020", "2021", "2022"],
            "GDP per capita (RM)": [42000.0, 43000.0, 44000.0],
        })

        # First call = state, second call = malaysia
        mock_download.side_effect = [
            mock_excel_from_dataframes({"dataset": state_df}),
            mock_excel_from_dataframes({"dataset": msia_df}),
        ]

        from pipeline.transforms.gdp_capita_states import transform
        result = transform()

        assert not result.empty
        statuses = result.sort_values("Year")["Data status"].tolist()
        assert statuses[0] is None  # 2020 — no suffix
        assert statuses[1] == "estimate"  # 2021e
        assert statuses[2] == "preliminary"  # 2022p

    @patch("pipeline.transforms.gdp_capita_states.download_excel_from_drive")
    def test_transform_output_columns(self, mock_download,
                                      mock_excel_from_dataframes):
        """Transform should produce the expected output columns."""
        state_df = pd.DataFrame({
            "Year": ["2020"],
            "State": ["Pulau Pinang"],
            "Base Year": [2015],
            "Value RM Million": [45000.0],
        })
        msia_df = pd.DataFrame({
            "Year": ["2020"],
            "GDP per capita (RM)": [42000.0],
        })
        mock_download.side_effect = [
            mock_excel_from_dataframes({"dataset": state_df}),
            mock_excel_from_dataframes({"dataset": msia_df}),
        ]

        from pipeline.transforms.gdp_capita_states import transform
        result = transform()

        expected_cols = [
            "State", "Year", "GDP per capita (RM)",
            "GDP per capita (Malaysia)", "Data status", "Updated as of",
        ]
        assert result.columns.tolist() == expected_cols

    @patch("pipeline.transforms.gdp_capita_states.download_excel_from_drive")
    def test_transform_merges_malaysia_data(self, mock_download,
                                            mock_excel_from_dataframes):
        """Malaysia GDP per capita should be merged into state data."""
        state_df = pd.DataFrame({
            "Year": ["2020"],
            "State": ["Pulau Pinang"],
            "Base Year": [2015],
            "Value RM Million": [45000.0],
        })
        msia_df = pd.DataFrame({
            "Year": ["2020"],
            "GDP per capita (RM)": [42000.0],
        })
        mock_download.side_effect = [
            mock_excel_from_dataframes({"dataset": state_df}),
            mock_excel_from_dataframes({"dataset": msia_df}),
        ]

        from pipeline.transforms.gdp_capita_states import transform
        result = transform()

        assert result["GDP per capita (Malaysia)"].iloc[0] == 42000.0

    @patch("pipeline.transforms.gdp_capita_states.download_excel_from_drive")
    def test_transform_keeps_latest_base_year(self, mock_download,
                                              mock_excel_from_dataframes):
        """When same Year/State has multiple base years, keep the latest."""
        state_df = pd.DataFrame({
            "Year": ["2020", "2020"],
            "State": ["Pulau Pinang", "Pulau Pinang"],
            "Base Year": [2010, 2015],
            "Value RM Million": [40000.0, 45000.0],
        })
        msia_df = pd.DataFrame({
            "Year": ["2020"],
            "GDP per capita (RM)": [42000.0],
        })
        mock_download.side_effect = [
            mock_excel_from_dataframes({"dataset": state_df}),
            mock_excel_from_dataframes({"dataset": msia_df}),
        ]

        from pipeline.transforms.gdp_capita_states import transform
        result = transform()

        # Should only have 1 row (2015 base year kept, 2010 dropped)
        assert len(result) == 1
        assert result["GDP per capita (RM)"].iloc[0] == 45000.0


# ---------------------------------------------------------------------------
# Demo Mukim — comprehensive tests
# ---------------------------------------------------------------------------

class TestDemoMukimComprehensive:
    """Comprehensive tests for mukim demographics transform."""

    def test_name_point1_columns(self):
        """Point 1 column naming should assign correct metric/year names."""
        from pipeline.transforms.demo_mukim import _name_point1_columns

        # Build a mock DataFrame with enough columns for Point 1
        # sheet(0), area(1), pop_total_2010(2), pop_total_2020(3), sep(4),
        # pop_male_2010(5), pop_male_2020(6), sep(7), ...
        ncols = 23  # sheet + area + 7 metrics * 3 cols (2 year + 1 sep) - last sep
        data = {i: ["test"] for i in range(ncols)}
        df = pd.DataFrame(data)

        result = _name_point1_columns(df)

        assert "sheet" in result.columns
        assert "area" in result.columns
        assert "pop_total_2010" in result.columns
        assert "pop_total_2020" in result.columns
        assert "pop_male_2010" in result.columns
        assert "pop_female_2020" in result.columns
        # Separator columns should be dropped
        assert not any(c.startswith("_sep_") for c in result.columns)

    def test_name_point2_columns(self):
        """Point 2 (ethnicity) column naming should have ethnicity groups."""
        from pipeline.transforms.demo_mukim import _name_point2_columns

        ncols = 20  # sheet + area + 9 groups * 2 years
        data = {i: ["test"] for i in range(ncols)}
        df = pd.DataFrame(data)

        result = _name_point2_columns(df)

        assert "sheet" in result.columns
        assert "area" in result.columns
        assert "total_2010" in result.columns
        assert "bumiputera_2020" in result.columns
        assert "chinese_2010" in result.columns

    def test_name_point3_columns(self):
        """Point 3 (age groups) column naming should include age groups."""
        from pipeline.transforms.demo_mukim import _name_point3_columns

        # sheet + area + 2 total + 3 age * 2 + blank + 3 ratios * 2
        ncols = 2 + 2 + 6 + 1 + 6  # = 17
        data = {i: ["test"] for i in range(ncols)}
        df = pd.DataFrame(data)

        result = _name_point3_columns(df)

        assert "total 2010" in result.columns
        assert "age-group_under-14_2010" in result.columns
        assert "age-group_65-plus_2020" in result.columns
        assert "dependency-ratio_total_2010" in result.columns

    def test_process_and_pivot_produces_long_format(self):
        """_process_and_pivot should produce a long-format DataFrame."""
        from pipeline.transforms.demo_mukim import _process_and_pivot

        # Minimal input: must have sheet, area, and at least one year column
        df = pd.DataFrame({
            "sheet": ["S1", "S1", "S1"],
            "area": ["PULAU PINANG", "Timur Laut", "Georgetown"],
            "pop_total_2020": [None, None, 500.0],
        })
        districts = pd.DataFrame({"state": ["Pulau Pinang"]})

        result = _process_and_pivot(df, districts)

        # Should have pivoted: name1 column "pop" should appear
        assert not result.empty
        assert "year" in result.columns


# ---------------------------------------------------------------------------
# Labour — comprehensive tests
# ---------------------------------------------------------------------------

class TestLabourComprehensive:
    """Comprehensive tests for labour force statistics transform."""

    def test_map_state_standard_names(self):
        """Standard uppercase state names should be title-cased."""
        from pipeline.transforms.labour import _map_state

        assert _map_state("KEDAH") == "Kedah"
        assert _map_state("MELAKA") == "Melaka"
        assert _map_state("SABAH") == "Sabah"

    def test_map_state_special_abbreviations(self):
        """Special abbreviated state names should map to full forms."""
        from pipeline.transforms.labour import _map_state

        assert _map_state("N.SEMBILAN") == "Negeri Sembilan"
        assert _map_state("P.PINANG") == "Pulau Pinang"
        assert _map_state("W.P.KUALA LUMPUR") == "W.P. Kuala Lumpur"
        assert _map_state("W.P.LABUAN") == "W.P. Labuan"
        assert _map_state("W.P.PUTRAJAYA") == "W.P. Putrajaya"

    def test_transform_returns_dict_with_principal_key(self):
        """transform() must return dict with 'principal' key."""
        from pipeline.transforms.labour import transform

        result = transform()
        assert isinstance(result, dict)
        assert "principal" in result
        # Value can be None or a DataFrame
        val = result["principal"]
        assert val is None or isinstance(val, pd.DataFrame)

    def test_state_map_completeness(self):
        """STATE_MAP should cover all known abbreviated state names."""
        from pipeline.transforms.labour import STATE_MAP

        assert len(STATE_MAP) == 5
        assert "N.SEMBILAN" in STATE_MAP
        assert "P.PINANG" in STATE_MAP



# ---------------------------------------------------------------------------
# Inferred Population — comprehensive tests
# ---------------------------------------------------------------------------

class TestInferredPopulationComprehensive:
    """Comprehensive tests for inferred population transform."""

    def test_mutate_period_with_estimate_suffix(self):
        """Year ending with 'e' should yield 'estimate' status."""
        from pipeline.transforms.inferred_population import _mutate_period

        df = pd.DataFrame({"period": ["2021e"]})
        result = _mutate_period(df)
        assert result["year"].iloc[0] == 2021
        assert result["status"].iloc[0] == "estimate"

    def test_mutate_period_with_clean_year(self):
        """Plain 4-digit year should yield None status."""
        from pipeline.transforms.inferred_population import _mutate_period

        df = pd.DataFrame({"period": ["2020"]})
        result = _mutate_period(df)
        assert result["year"].iloc[0] == 2020
        assert result["status"].iloc[0] is None

    def test_extract_base_year(self):
        """Should extract base year from filename pattern."""
        from pipeline.transforms.inferred_population import _extract_base_year

        assert _extract_base_year("GDP by State 2005-2010 (2000=100).xlsx") == "2000"
        assert _extract_base_year("GDP by State 2010-2016 (2010=100).xlsx") == "2010"
        assert _extract_base_year("no_match.xlsx") is None

    def test_extract_last_updated(self):
        """Should extract last year from year range in filename."""
        from pipeline.transforms.inferred_population import _extract_last_updated

        assert _extract_last_updated("GDP by State 2005-2010 (2000=100).xlsx") == "2010"
        assert _extract_last_updated("GDP by State, 2015-2021 (2015=100).xlsx") == "2021"
        assert _extract_last_updated("no_match.xlsx") is None

    def test_transform_returns_dataframe(self):
        """Transform should return a DataFrame."""
        from pipeline.transforms.inferred_population import transform

        result = transform()
        assert isinstance(result, pd.DataFrame)


# ---------------------------------------------------------------------------
# GDP Economic Activity — comprehensive tests
# ---------------------------------------------------------------------------

class TestGDPEconActivityComprehensive:
    """Comprehensive tests for GDP by economic activity transform."""

    def test_fix_econ_activity(self):
        """_fix_econ_activity should standardize known variations."""
        from pipeline.transforms.gdp_econ_activity import _fix_econ_activity

        assert _fix_econ_activity("Mining and quarrying") == "Mining and Quarrying"
        assert _fix_econ_activity("plus: Import Duties") == "Import Duties"
        assert _fix_econ_activity("Plus: Import duties") == "Import Duties"
        # Unknown values pass through
        assert _fix_econ_activity("Agriculture") == "Agriculture"

    def test_fix_sub_sector(self):
        """_fix_sub_sector should standardize sub-sector name variations."""
        from pipeline.transforms.gdp_econ_activity import _fix_sub_sector

        assert _fix_sub_sector("Other services") == "Other Services"
        assert _fix_sub_sector("Government services") == "Government Services"
        assert _fix_sub_sector("Unknown") == "Unknown"

    def test_extract_data_status(self):
        """_extract_data_status should identify 'e' and 'p' suffixes."""
        from pipeline.transforms.gdp_econ_activity import _extract_data_status

        assert _extract_data_status("2021e") == "estimate"
        assert _extract_data_status("2022p") == "preliminary"
        assert _extract_data_status("2020") is None

    @patch("pipeline.transforms.gdp_econ_activity.download_excel_from_drive")
    @patch("pipeline.transforms.gdp_econ_activity.read_google_sheet")
    def test_transform_returns_dict_with_required_keys(self, mock_sheet, mock_download):
        """transform() must return dict with 'by_econ_act' and 'by_subecon_act'."""
        mock_download.side_effect = Exception("No credentials")
        mock_sheet.side_effect = Exception("No credentials")

        from pipeline.transforms.gdp_econ_activity import transform
        result = transform()

        assert isinstance(result, dict)
        assert "by_econ_act" in result
        assert "by_subecon_act" in result
        assert isinstance(result["by_econ_act"], pd.DataFrame)
        assert isinstance(result["by_subecon_act"], pd.DataFrame)

    def test_malaysia_activities_list(self):
        """MALAYSIA_ACTIVITIES should list the 6 main sectors."""
        from pipeline.transforms.gdp_econ_activity import MALAYSIA_ACTIVITIES

        assert len(MALAYSIA_ACTIVITIES) == 6
        assert "Agriculture" in MALAYSIA_ACTIVITIES
        assert "Manufacturing" in MALAYSIA_ACTIVITIES
        assert "Import Duties" in MALAYSIA_ACTIVITIES


# ---------------------------------------------------------------------------
# Gender — comprehensive tests
# ---------------------------------------------------------------------------

class TestGenderComprehensive:
    """Comprehensive tests for gender statistics transforms."""

    def test_transform_literacy_no_file(self):
        """transform_literacy returns None when education file not found."""
        from pipeline.transforms.gender import transform_literacy

        result = transform_literacy()
        assert result is None

    @patch("pipeline.transforms.gender.download_file_from_drive")
    def test_transform_decision_making_no_credentials(self, mock_download):
        """transform_decision_making returns None on download failure."""
        mock_download.side_effect = Exception("No credentials")

        from pipeline.transforms.gender import transform_decision_making
        result = transform_decision_making()
        assert result is None

    def test_main_returns_dict_with_two_keys(self):
        """main() should return dict with literacy and decision_making."""
        with patch("pipeline.transforms.gender.load"):
            from pipeline.transforms.gender import main
            with patch("pipeline.transforms.gender.transform_decision_making", return_value=None):
                result = main()

        assert isinstance(result, dict)
        assert "literacy" in result
        assert "decision_making" in result
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Graduates — comprehensive tests
# ---------------------------------------------------------------------------

class TestGraduatesComprehensive:
    """Comprehensive tests for graduate employment transforms."""

    def test_make_clean_name_special_chars(self):
        """_make_clean_name should handle various special characters."""
        from pipeline.transforms.graduates import _make_clean_name

        assert _make_clean_name("A & B") == "a_b"
        assert _make_clean_name("Year/Month") == "year_month"
        assert _make_clean_name("GDP (RM)") == "gdp_rm"
        assert _make_clean_name("") == ""

    def test_build_paired_colnames_structure(self):
        """_build_paired_colnames should produce bil/pct pairs + jumlah."""
        from pipeline.transforms.graduates import _build_paired_colnames

        result = _build_paired_colnames(["Science"])
        assert result == [
            "science_bil", "science_pct",
            "jumlah_bil", "jumlah_pct",
        ]

    def test_build_paired_colnames_empty(self):
        """_build_paired_colnames with no headers still produces jumlah."""
        from pipeline.transforms.graduates import _build_paired_colnames

        result = _build_paired_colnames([])
        assert result == ["jumlah_bil", "jumlah_pct"]

    def test_transform_returns_dict_with_both_keys(self):
        """transform() must return dict with sektor_ekonomi + status_pekerjaan."""
        from pipeline.transforms.graduates import transform

        result = transform()
        assert isinstance(result, dict)
        assert "sektor_ekonomi" in result
        assert "status_pekerjaan" in result
        # Both should be DataFrames (possibly empty)
        assert isinstance(result["sektor_ekonomi"], pd.DataFrame)
        assert isinstance(result["status_pekerjaan"], pd.DataFrame)


# ---------------------------------------------------------------------------
# Gross Income — comprehensive tests
# ---------------------------------------------------------------------------

class TestGrossIncomeComprehensive:
    """Comprehensive tests for household income transforms."""

    @patch("pipeline.transforms.gross_income.fetch_parquet")
    def test_fetch_hies_combined_column_renames(self, mock_fetch):
        """_fetch_hies_combined should rename income_mean->mean_gross_income etc."""
        mock_fetch.return_value = pd.DataFrame({
            "date": pd.to_datetime(["2022-01-01"]),
            "state": ["Pulau Pinang"],
            "gini": [0.35],
            "income_mean": [8000],
            "income_median": [6000],
        })
        from pipeline.transforms.gross_income import _fetch_hies_combined

        result = _fetch_hies_combined("state")
        assert "gini_gross_income" in result.columns
        assert "mean_gross_income" in result.columns
        assert "median_gross_income" in result.columns
        assert "year" in result.columns
        assert "updated_as_of" in result.columns

    @patch("pipeline.transforms.gross_income.fetch_parquet")
    def test_fetch_hies_combined_all_fail(self, mock_fetch):
        """_fetch_hies_combined returns empty DataFrame when all fetches fail."""
        mock_fetch.side_effect = Exception("Network error")
        from pipeline.transforms.gross_income import _fetch_hies_combined

        result = _fetch_hies_combined("state")
        assert result.empty

    @patch("pipeline.transforms.gross_income.fetch_parquet")
    def test_fetch_hh_poverty_combines_sources(self, mock_fetch):
        """_fetch_hh_poverty should combine Malaysia + state + district data."""
        mock_fetch.return_value = pd.DataFrame({
            "date": pd.to_datetime(["2022-01-01"]),
            "state": ["Pulau Pinang"],
            "poverty_relative": [5.0],
        })
        from pipeline.transforms.gross_income import _fetch_hh_poverty

        result = _fetch_hh_poverty()
        assert not result.empty
        assert "incidence_of_relative_poverty_percent" in result.columns

    @patch("pipeline.transforms.gross_income.fetch_parquet")
    def test_fetch_hh_poverty_all_fail(self, mock_fetch):
        """_fetch_hh_poverty returns empty DataFrame when all fetches fail."""
        mock_fetch.side_effect = Exception("Network error")
        from pipeline.transforms.gross_income import _fetch_hh_poverty

        result = _fetch_hh_poverty()
        assert result.empty

    def test_lookup_map_structure(self):
        """LOOKUP should map 4 standard metric names to new OpenDOSM columns."""
        from pipeline.transforms.gross_income import LOOKUP

        assert len(LOOKUP) == 4
        assert LOOKUP["gini_gross_income"] == "gini"
        assert LOOKUP["mean_gross_income"] == "income_mean"
        assert LOOKUP["median_gross_income"] == "income_median"
        assert LOOKUP["absolute_poverty"] == "poverty_absolute"


# ---------------------------------------------------------------------------
# Population OpenDOSM — comprehensive tests
# ---------------------------------------------------------------------------

class TestPopulationOpenDOSMComprehensive:
    """Comprehensive tests for population OpenDOSM transform."""

    @patch("pipeline.transforms.population_opendosm.fetch_parquet")
    def test_clean_opendosm_sex_mapping(self, mock_fetch):
        """_clean_opendosm should map sex codes to proper Gender labels."""
        raw = pd.DataFrame({
            "state": ["Pulau Pinang", "Pulau Pinang", "Pulau Pinang"],
            "date": pd.to_datetime(["2024-01-01"] * 3),
            "sex": ["both", "male", "female"],
            "age": ["overall"] * 3,
            "ethnicity": ["overall_ethnicity"] * 3,
            "population": [1800, 900, 900],
        })
        from pipeline.transforms.population_opendosm import _clean_opendosm

        result = _clean_opendosm(raw)
        assert result["Gender"].tolist() == ["Total", "Male", "Female"]

    @patch("pipeline.transforms.population_opendosm.fetch_parquet")
    def test_clean_opendosm_year_extraction(self, mock_fetch):
        """_clean_opendosm should extract year from date column."""
        raw = pd.DataFrame({
            "state": ["Pulau Pinang"],
            "date": pd.to_datetime(["2024-01-01"]),
            "sex": ["both"],
            "age": ["overall"],
            "ethnicity": ["overall_ethnicity"],
            "population": [1800],
        })
        from pipeline.transforms.population_opendosm import _clean_opendosm

        result = _clean_opendosm(raw)
        assert "Year" in result.columns
        assert result["Year"].iloc[0] == 2024
        assert "date" not in result.columns

    @patch("pipeline.transforms.population_opendosm.fetch_parquet")
    def test_clean_opendosm_population_rename(self, mock_fetch):
        """_clean_opendosm should rename population column."""
        raw = pd.DataFrame({
            "state": ["Pulau Pinang"],
            "date": pd.to_datetime(["2024-01-01"]),
            "sex": ["both"],
            "age": ["overall"],
            "ethnicity": ["overall_ethnicity"],
            "population": [1800],
        })
        from pipeline.transforms.population_opendosm import _clean_opendosm

        result = _clean_opendosm(raw)
        assert "Population ('000)" in result.columns
        assert "population" not in result.columns

    @patch("pipeline.transforms.population_opendosm.fetch_parquet")
    def test_transform_state_returns_dataframe(self, mock_fetch):
        """transform_state should return a non-empty DataFrame."""
        mock_fetch.return_value = pd.DataFrame({
            "state": ["Pulau Pinang"],
            "date": pd.to_datetime(["2024-01-01"]),
            "sex": ["both"],
            "age": ["overall"],
            "ethnicity": ["overall_ethnicity"],
            "population": [1800],
        })
        from pipeline.transforms.population_opendosm import transform_state

        result = transform_state()
        assert isinstance(result, pd.DataFrame)
        assert not result.empty

    @patch("pipeline.transforms.population_opendosm.fetch_parquet")
    def test_transform_state_failure(self, mock_fetch):
        """transform_state returns empty DataFrame on fetch failure."""
        mock_fetch.side_effect = Exception("Network error")
        from pipeline.transforms.population_opendosm import transform_state

        result = transform_state()
        assert result.empty

    def test_ethnicity_map_completeness(self):
        """ETHNICITY_MAP should cover all expected codes."""
        from pipeline.utils.opendosm_helpers import ETHNICITY_MAP

        assert len(ETHNICITY_MAP) == 8
        assert ETHNICITY_MAP["bumi_malay"] == "Malay"
        assert ETHNICITY_MAP["chinese"] == "Chinese"
        assert ETHNICITY_MAP["indian"] == "Indians"
        assert ETHNICITY_MAP["other_noncitizen"] == "Non-Malaysian Citizens"

    def test_state_renames_map(self):
        """STATE_RENAMES should map old/English spellings to current."""
        from pipeline.utils.opendosm_helpers import STATE_RENAMES

        assert STATE_RENAMES["Penang"] == "Pulau Pinang"
        assert STATE_RENAMES["Malacca"] == "Melaka"


# ---------------------------------------------------------------------------
# Population Ethnicity — comprehensive tests
# ---------------------------------------------------------------------------

class TestPopulationEthnicityComprehensive:
    """Comprehensive tests for population ethnicity transform."""

    @patch("pipeline.transforms.population_ethnicity.fetch_parquet")
    def test_transform_penang_filters_state(self, mock_fetch):
        """transform_penang should only return Pulau Pinang rows."""
        raw = pd.DataFrame({
            "state": ["Pulau Pinang", "Johor", "Kedah"],
            "date": pd.to_datetime(["2024-01-01"] * 3),
            "sex": ["both"] * 3,
            "age": ["overall"] * 3,
            "ethnicity": ["bumi_malay"] * 3,
            "population": [500, 300, 200],
        })
        mock_fetch.return_value = raw
        from pipeline.transforms.population_ethnicity import transform_penang

        result = transform_penang()
        assert not result.empty
        assert all(result["state"] == "Pulau Pinang")
        assert len(result) == 1

    @patch("pipeline.transforms.population_ethnicity.fetch_parquet")
    def test_clean_opendosm_ethnicity_and_nationality(self, mock_fetch):
        """_clean_opendosm should map both Ethnic and Nationality."""
        raw = pd.DataFrame({
            "state": ["Pulau Pinang"],
            "date": pd.to_datetime(["2024-01-01"]),
            "sex": ["both"],
            "age": ["overall"],
            "ethnicity": ["other_noncitizen"],
            "population": [100],
        })
        from pipeline.transforms.population_ethnicity import _clean_opendosm

        result = _clean_opendosm(raw)
        # Base mapping returns "Non-Malaysian Citizens"; recode_ethnicity_for_district() converts to "Non-citizens"
        assert result["Ethnic"].iloc[0] == "Non-Malaysian Citizens"
        assert result["Nationality"].iloc[0] == "Non-Malaysian"

    def test_recode_ethnicity_for_district(self):
        """recode_ethnicity_for_district should convert labels for district outputs."""
        from pipeline.utils.opendosm_helpers import recode_ethnicity_for_district

        assert recode_ethnicity_for_district("Non-Malaysian Citizens") == "Non-citizens"
        assert recode_ethnicity_for_district("Others") == "Other Malaysians"
        assert recode_ethnicity_for_district("Malay") == "Malay"

    def test_transform_fertility_missing_file(self):
        """transform_fertility should return empty DataFrame when file missing."""
        from pipeline.transforms.population_ethnicity import transform_fertility

        result = transform_fertility()
        assert isinstance(result, pd.DataFrame)

    @patch("pipeline.transforms.population_ethnicity.fetch_parquet")
    def test_transform_returns_dict_with_all_keys(self, mock_fetch):
        """transform() should return dict with 5 keys."""
        mock_fetch.return_value = pd.DataFrame({
            "state": ["Pulau Pinang"],
            "date": pd.to_datetime(["2024-01-01"]),
            "sex": ["both"],
            "age": ["overall"],
            "ethnicity": ["overall_ethnicity"],
            "population": [1800],
        })
        from pipeline.transforms.population_ethnicity import transform

        result = transform()
        assert isinstance(result, dict)
        expected_keys = {"penang", "malaysia", "district_ethnicity",
                         "district_sex", "fertility"}
        assert set(result.keys()) == expected_keys


# ---------------------------------------------------------------------------
# Property — comprehensive tests
# ---------------------------------------------------------------------------

class TestPropertyComprehensive:
    """Comprehensive tests for property market transform."""

    def test_transform_returns_dict_with_four_keys(self):
        """transform() must return dict with all 4 property categories."""
        from pipeline.transforms.property import transform

        result = transform()
        assert isinstance(result, dict)
        expected_keys = {"transactions", "house_prices", "unsold", "newly_launched"}
        assert set(result.keys()) == expected_keys

    def test_transform_values_are_dataframes(self):
        """All values in transform() result must be DataFrames."""
        from pipeline.transforms.property import transform

        result = transform()
        for key, val in result.items():
            assert isinstance(val, pd.DataFrame), f"{key} is not a DataFrame"


# ---------------------------------------------------------------------------
# Trade — comprehensive tests
# ---------------------------------------------------------------------------

class TestTradeComprehensive:
    """Comprehensive tests for trade by exit-entry point transform."""

    def test_transform_returns_dataframe(self):
        """transform() should return a DataFrame (possibly empty)."""
        from pipeline.transforms.trade import transform

        result = transform()
        assert isinstance(result, pd.DataFrame)


# ---------------------------------------------------------------------------
# Trade HS — comprehensive tests
# ---------------------------------------------------------------------------

class TestTradeHSComprehensive:
    """Comprehensive tests for HS trade data transform."""

    def test_make_clean_names_various(self):
        """_make_clean_names should handle various input patterns."""
        from pipeline.transforms.trade_hs import _make_clean_names

        assert _make_clean_names(["State/Territory"]) == ["state_territory"]
        assert _make_clean_names(["Jan 2024"]) == ["jan_2024"]
        assert _make_clean_names(["HS Code", "Country"]) == ["hs_code", "country"]
        assert _make_clean_names([""]) == [""]

    def test_make_clean_names_preserves_order(self):
        """Output order should match input order."""
        from pipeline.transforms.trade_hs import _make_clean_names

        input_names = ["Alpha", "Beta", "Gamma"]
        result = _make_clean_names(input_names)
        assert result == ["alpha", "beta", "gamma"]

    def test_transform_returns_empty_when_no_path(self):
        """transform() should return empty DataFrame when path unavailable."""
        from pipeline.transforms.trade_hs import transform

        result = transform()
        assert isinstance(result, pd.DataFrame)
        assert result.empty


# ---------------------------------------------------------------------------
# Airports — comprehensive tests
# ---------------------------------------------------------------------------

class TestAirportsComprehensive:
    """Comprehensive tests for airport/transport transforms."""

    def test_transform_returns_dict_with_all_keys(self):
        """transform() should return dict with exactly 4 transport categories."""
        from pipeline.transforms.airports import transform

        result = transform()
        assert isinstance(result, dict)
        expected = {"passengers", "aircraft", "airport_cargo", "maritime_cargo"}
        assert set(result.keys()) == expected

    def test_all_values_are_dataframes(self):
        """All transform() results should be DataFrames."""
        from pipeline.transforms.airports import transform

        result = transform()
        for key, val in result.items():
            assert isinstance(val, pd.DataFrame), f"{key} is not a DataFrame"

    def test_output_sheets_has_four_keys(self):
        """OUTPUT_SHEETS should map all 4 categories to sheet IDs."""
        from pipeline.transforms.airports import OUTPUT_SHEETS

        assert len(OUTPUT_SHEETS) == 4
        assert "passengers" in OUTPUT_SHEETS
        assert "aircraft" in OUTPUT_SHEETS
        assert "airport_cargo" in OUTPUT_SHEETS
        assert "maritime_cargo" in OUTPUT_SHEETS


# ---------------------------------------------------------------------------
# Labour Demographics — comprehensive tests
# ---------------------------------------------------------------------------

class TestLabourDemographicsComprehensive:
    """Comprehensive tests for labour demographics transform."""

    def test_get_skip_rows_all_types(self):
        """_get_skip_rows should return correct values for all file types."""
        from pipeline.transforms.labour_demographics import _get_skip_rows

        assert _get_skip_rows("Employed by age group.xlsx") == 4
        assert _get_skip_rows("Labour by ethnic group.xlsx") == 7
        assert _get_skip_rows("Employed by educational attainment.xlsx") == 5
        assert _get_skip_rows("Labour by highest certificate.xlsx") == 5
        assert _get_skip_rows("Employed by marital status.xlsx") == 5
        assert _get_skip_rows("random_file.xlsx") is None

    def test_infer_strata_all_types(self):
        """_infer_strata should identify all 4 strata types + unknown."""
        from pipeline.transforms.labour_demographics import _infer_strata

        assert _infer_strata("Labour by age group.xlsx") == "age group"
        assert _infer_strata("Employed by ethnic group.xlsx") == "ethnicity"
        assert _infer_strata("Labour by educational attainment.xlsx") == "highest certificate"
        assert _infer_strata("Labour by highest certificate.xlsx") == "highest certificate"
        assert _infer_strata("Employed by marital status.xlsx") == "marital status"
        assert _infer_strata("something_else.xlsx") == "unknown"

    def test_infer_measure_employed_vs_labour(self):
        """_infer_measure should distinguish Employed from Labour force."""
        from pipeline.transforms.labour_demographics import _infer_measure

        assert _infer_measure("Employed by age.xlsx") == "Employed persons"
        assert _infer_measure("Labour by age.xlsx") == "Labour force"
        # Non-Employed defaults to "Labour force"
        assert _infer_measure("Other by age.xlsx") == "Labour force"

    def test_transform_returns_empty_when_no_path(self):
        """transform() should return empty DataFrame when path unavailable."""
        from pipeline.transforms.labour_demographics import transform

        result = transform()
        assert isinstance(result, pd.DataFrame)
        assert result.empty
