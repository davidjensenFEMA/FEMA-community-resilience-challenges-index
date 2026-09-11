"""
Smoke tests for the CRIA pipeline.

These are thin end-to-end tests that prove "the pipeline does not crash."
They test shape and structure, NOT specific values.
All external APIs and database operations are mocked.
Each test should complete in under 5 seconds.
"""

import numpy as np
import pandas as pd
import pytest
from unittest.mock import patch, MagicMock

from src.core.aggregator import AggregateIndicator


# =============================================================================
# Synthetic Data Fixtures
# =============================================================================

SYNTHETIC_REFERENCE = pd.DataFrame({
    "Indicator": [
        "Poverty",
        "GINI",
        "Low Access to Communications",
        "Civil Org",
        "Population Change",
    ],
    "Source": ["ACS", "ACS", "ACS", "CBP", "POP"],
    "Function": ["divide", "divide", "reverse_divide", "divide_scalar", "mean"],
    "numerator": [
        "B17001_002E",
        "B19083_001E",
        "S2801_C01_005E",
        "813410",
        "NETMIG",
    ],
    "denominator": [
        "B17001_001E",
        "1",
        "S2801_C01_001E",
        "S0101_C01_001E",
        "S0101_C01_001E",
    ],
    "rate": [np.nan, np.nan, np.nan, 10.0, np.nan],
    "Units": ["fraction", "index", "fraction", "rate", "ratio"],
    "Augment": ["reverse", "reverse", "reverse", "none", "none"],
    "Order_2023": [1, 2, 3, 4, 5],
})

SYNTHETIC_YEARS = {
    "acs": 2021,
    "cbp": 2020,
    "naics": 2017,
    "pop": 2020,
    "asarb": 2020,
    "acs_labels": 2020,
}

# 10 rows of synthetic source data with all columns needed by SYNTHETIC_REFERENCE
np.random.seed(99)
_N = 10
_GEO_IDS = [f"0500000US{i:05d}" for i in range(1, _N + 1)]

SYNTHETIC_SOURCE_DATA = pd.DataFrame(
    {
        # ACS columns for Poverty (divide)
        "B17001_002E": np.random.randint(1000, 10000, _N).astype(float),
        "B17001_001E": np.random.randint(30000, 100000, _N).astype(float),
        # ACS column for GINI (divide, denominator=1)
        "B19083_001E": np.random.uniform(0.35, 0.55, _N),
        # ACS columns for Low Access to Communications (reverse_divide)
        "S2801_C01_005E": np.random.randint(5000, 20000, _N).astype(float),
        "S2801_C01_001E": np.random.randint(25000, 80000, _N).astype(float),
        # CBP column for Civil Org (divide_scalar)
        "813410": np.random.randint(0, 50, _N).astype(float),
        # Shared ACS population denominator
        "S0101_C01_001E": np.random.randint(30000, 100000, _N).astype(float),
        # POP columns for Population Change (mean): NETMIG{year} for 5 years
        "NETMIG2020": np.random.normal(100, 50, _N),
        "NETMIG2019": np.random.normal(80, 40, _N),
        "NETMIG2018": np.random.normal(90, 60, _N),
        "NETMIG2017": np.random.normal(70, 30, _N),
        "NETMIG2016": np.random.normal(110, 55, _N),
    },
    index=_GEO_IDS,
)
SYNTHETIC_SOURCE_DATA.index.name = "GEO_ID"


def _make_calculator(geography="county"):
    """
    Build an IndicatorCalculator without hitting real files or APIs.

    We mock DataPuller entirely so __init__ never loads reference files
    or creates API clients.
    """
    from src.core.indicators import IndicatorCalculator

    with patch.object(IndicatorCalculator, "__init__", lambda self, *a, **kw: None):
        calc = IndicatorCalculator.__new__(IndicatorCalculator)

    calc.geography = geography
    calc.db = None
    calc.data_puller = MagicMock()
    calc.reference = SYNTHETIC_REFERENCE.copy()
    calc.years = dict(SYNTHETIC_YEARS)
    return calc


# =============================================================================
# County-level smoke tests
# =============================================================================


class TestPipelineSmokeCounty:
    """County-level pipeline smoke tests (5 bins)."""

    def test_indicator_calculation_no_crash(self):
        """IndicatorCalculator.calculate_all_indicators runs without error."""
        calc = _make_calculator(geography="county")

        result = calc.calculate_all_indicators(source_data=SYNTHETIC_SOURCE_DATA.copy())

        assert isinstance(result, pd.DataFrame)
        assert len(result.columns) > 0
        assert len(result) == len(SYNTHETIC_SOURCE_DATA)
        # Index should match source data
        assert list(result.index) == list(SYNTHETIC_SOURCE_DATA.index)

    def test_aggregation_no_crash(self):
        """AggregateIndicator.create_aggregate runs without error."""
        calc = _make_calculator(geography="county")
        indicators = calc.calculate_all_indicators(
            source_data=SYNTHETIC_SOURCE_DATA.copy()
        )

        aggregator = AggregateIndicator(geography="county", bins=5)
        results = aggregator.create_aggregate(
            indicators=indicators,
            reference=SYNTHETIC_REFERENCE,
            bin_indicators=True,
        )

        expected_keys = {
            "indicators", "pos", "scores", "scores_percentiles",
            "lowest_ind", "agg", "bin_labels", "bin_meta",
            "agg_labels", "agg_meta", "corr", "p", "zero", "n",
        }
        assert expected_keys == set(results.keys())

        # Each value should be a DataFrame
        for key in expected_keys:
            assert isinstance(results[key], pd.DataFrame), f"results['{key}'] not a DataFrame"

        # Aggregate should have standard columns
        assert "cri" in results["agg"].columns
        assert "cria_p" in results["agg"].columns

    def test_full_pipeline_mock_no_crash(self):
        """Calculator -> Aggregator pipeline runs end to end."""
        calc = _make_calculator(geography="county")
        source = SYNTHETIC_SOURCE_DATA.copy()

        indicators = calc.calculate_all_indicators(source_data=source)
        aggregator = AggregateIndicator(geography="county", bins=5)
        results = aggregator.create_aggregate(
            indicators=indicators,
            reference=SYNTHETIC_REFERENCE,
            bin_indicators=True,
        )

        # Final aggregate has same row count as input
        assert len(results["agg"]) == _N
        # Percentiles in [0, 1]
        assert results["agg"]["cria_p"].min() >= 0
        assert results["agg"]["cria_p"].max() <= 1

    def test_aggregation_no_binning_no_crash(self):
        """Aggregation with bin_indicators=False still produces valid output."""
        calc = _make_calculator(geography="county")
        indicators = calc.calculate_all_indicators(
            source_data=SYNTHETIC_SOURCE_DATA.copy()
        )

        aggregator = AggregateIndicator(geography="county", bins=5)
        results = aggregator.create_aggregate(
            indicators=indicators,
            reference=SYNTHETIC_REFERENCE,
            bin_indicators=False,
        )

        assert "agg" in results
        assert "cri" in results["agg"].columns
        # bin_labels should be empty when binning is disabled
        assert results["bin_labels"].empty
        assert results["bin_meta"].empty

    def test_excel_export_no_crash(self, tmp_path):
        """Pipeline results can be saved to Excel without error."""
        calc = _make_calculator(geography="county")
        indicators = calc.calculate_all_indicators(
            source_data=SYNTHETIC_SOURCE_DATA.copy()
        )

        aggregator = AggregateIndicator(geography="county", bins=5)
        results = aggregator.create_aggregate(
            indicators=indicators,
            reference=SYNTHETIC_REFERENCE,
            bin_indicators=True,
        )

        output_file = tmp_path / "smoke_county.xlsx"
        aggregator.save_to_excel(
            results=results,
            file_path=str(output_file),
            include_geo=False,
            reference=SYNTHETIC_REFERENCE,
            years=SYNTHETIC_YEARS,
        )

        assert output_file.exists()

        # Verify the file is readable and has expected sheets
        xl = pd.ExcelFile(output_file)
        sheet_names = xl.sheet_names
        assert "ref" in sheet_names
        assert "years" in sheet_names
        assert len(sheet_names) >= 4  # ref, years, + at least some result sheets


# =============================================================================
# Tract-level smoke tests
# =============================================================================


class TestPipelineSmokeTract:
    """Tract-level pipeline smoke tests (7 bins)."""

    def test_tract_7_bins_no_crash(self):
        """Tract pipeline runs with 7 bins without error."""
        calc = _make_calculator(geography="tract")
        indicators = calc.calculate_all_indicators(
            source_data=SYNTHETIC_SOURCE_DATA.copy()
        )

        aggregator = AggregateIndicator(geography="tract", bins=7)
        results = aggregator.create_aggregate(
            indicators=indicators,
            reference=SYNTHETIC_REFERENCE,
            bin_indicators=True,
        )

        assert "agg" in results
        assert len(results["agg"]) == _N
        assert "cri" in results["agg"].columns

        # Bin labels should exist (bins capped to available data count)
        assert not results["bin_labels"].empty


# =============================================================================
# Tribal-level smoke tests
# =============================================================================


class TestPipelineSmokeTribal:
    """Tribal pipeline smoke tests (non-ACS indicators set to NaN)."""

    def test_tribal_acs_only_no_crash(self):
        """
        Tribal pipeline completes when non-ACS indicators are NaN.

        Tribal areas only have ACS data; CBP, EAVS, ARDA, POP columns
        should be NaN. The pipeline must still produce valid output.
        """
        calc = _make_calculator(geography="tribal")

        # Start with normal source data then blank out non-ACS columns
        source = SYNTHETIC_SOURCE_DATA.copy()
        non_acs_cols = [
            "813410",  # CBP
            "NETMIG2020", "NETMIG2019", "NETMIG2018", "NETMIG2017", "NETMIG2016",  # POP
        ]
        for col in non_acs_cols:
            if col in source.columns:
                source[col] = np.nan

        indicators = calc.calculate_all_indicators(source_data=source)

        # Non-ACS indicators should be all-NaN
        assert indicators["Civil Org"].isna().all()
        assert indicators["Population Change"].isna().all()

        # ACS-based indicators should still have values
        assert indicators["Poverty"].notna().any()

        # Aggregation should still complete
        aggregator = AggregateIndicator(geography="tribal", bins=5)
        results = aggregator.create_aggregate(
            indicators=indicators,
            reference=SYNTHETIC_REFERENCE,
            bin_indicators=True,
        )

        assert "agg" in results
        assert len(results["agg"]) == _N
