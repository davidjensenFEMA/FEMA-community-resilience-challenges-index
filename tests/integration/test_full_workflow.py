"""
Integration tests for complete CRIA workflow.

Tests the full pipeline:
    Pull Data → Calculate Indicators → Create Aggregate
"""

import pytest
import pandas as pd
import numpy as np
from pathlib import Path


@pytest.fixture
def mock_reference_data():
    """Create mock reference data for testing."""
    return pd.DataFrame({
        "Indicator": ["Poverty", "GINI", "Unemployment"],
        "Source": ["ACS", "ACS", "ACS"],
        "Function": ["divide", "divide", "divide"],
        "numerator": ["B17001_002E", "B19083_001E", "B23025_005E"],
        "denominator": ["B17001_001E", "1", "B23025_002E"],
        "Units": ["fraction", "index", "fraction"],
        "Augment": ["reverse", "reverse", "reverse"],
        "Order_2023": [1, 2, 3]
    })


@pytest.fixture
def mock_geography_data():
    """Create mock geography data."""
    return pd.DataFrame({
        "NAME": ["County A", "County B", "County C"],
        "state_name": ["Alabama", "Alabama", "Connecticut"],
        "state_abbr": ["AL", "AL", "CT"],
        "state": [1, 1, 9],
        "county": ["001", "002", "003"]
    }, index=["GEO_001", "GEO_002", "GEO_003"])


@pytest.mark.integration
class TestFullWorkflow:
    """Integration tests for complete CRIA workflow."""

    def test_indicators_to_aggregate_pipeline(
        self,
        mock_reference_data,
        mock_geography_data
    ):
        """Test complete pipeline from indicators to aggregate."""
        from src.core.aggregator import AggregateIndicator

        # Step 1: Create mock indicators (simulating IndicatorCalculator output)
        np.random.seed(42)
        indicators = pd.DataFrame({
            "Poverty": np.random.beta(2, 5, 3),
            "GINI": np.random.uniform(0.3, 0.6, 3),
            "Unemployment": np.random.beta(2, 8, 3),
        }, index=["GEO_001", "GEO_002", "GEO_003"])

        # Step 2: Create aggregate
        aggregator = AggregateIndicator(geography="county", bins=5)

        results = aggregator.create_aggregate(
            indicators=indicators,
            reference=mock_reference_data,
            geo_reference=mock_geography_data,
            bin_indicators=True
        )

        # Verify results structure
        assert "indicators" in results
        assert "pos" in results
        assert "scores" in results
        assert "agg" in results
        assert "bin_labels" in results

        # Verify aggregate has required columns
        assert "agg" in results["agg"].columns
        assert "cri" in results["agg"].columns
        assert "cria_p" in results["agg"].columns

        # Verify bins are 1-indexed
        for col in indicators.columns:
            bin_col = f"{col}_bins"
            if bin_col in results["bin_labels"].columns:
                assert results["bin_labels"][bin_col].min() >= 1
                assert results["bin_labels"][bin_col].max() <= 5

    def test_county_level_complete_workflow(self, mock_reference_data):
        """Test complete county-level workflow with realistic data."""
        from src.core.aggregator import AggregateIndicator

        # Simulate 20 counties
        np.random.seed(123)
        n_counties = 20

        indicators = pd.DataFrame({
            "Poverty": np.random.beta(2, 5, n_counties),
            "GINI": np.random.uniform(0.3, 0.6, n_counties),
            "Unemployment": np.random.beta(2, 8, n_counties),
        }, index=[f"GEO_{i:04d}" for i in range(n_counties)])

        geo_ref = pd.DataFrame({
            "NAME": [f"County {i}" for i in range(n_counties)],
            "state_name": ["Alabama"] * n_counties,
            "state": [1] * n_counties
        }, index=indicators.index)

        aggregator = AggregateIndicator(geography="county", bins=5)

        results = aggregator.create_aggregate(
            indicators=indicators,
            reference=mock_reference_data,
            geo_reference=geo_ref,
            bin_indicators=True
        )

        # All counties should be processed
        assert len(results["agg"]) == n_counties

        # Verify binning worked
        assert not results["bin_labels"].empty

        # Verify aggregate scores are valid
        assert results["agg"]["cria_p"].min() >= 0
        assert results["agg"]["cria_p"].max() <= 1

    def test_workflow_with_special_cases(
        self,
        mock_reference_data
    ):
        """Test workflow handles special cases (CT, PR)."""
        from src.core.aggregator import AggregateIndicator

        # Create data with Connecticut and Puerto Rico
        indicators = pd.DataFrame({
            "Poverty": [0.15, 0.12, 0.20, 0.18],
            "GINI": [0.45, 0.42, 0.48, 0.50],
            "Unemployment": [0.08, 0.06, 0.10, 0.09],
        }, index=["GEO_001", "GEO_002", "GEO_003", "GEO_004"])

        geo_ref = pd.DataFrame({
            "NAME": ["AL County", "CT County", "PR County", "TX County"],
            "state_name": ["Alabama", "Connecticut", "Puerto Rico", "Texas"],
            "state": [1, 9, 72, 48]
        }, index=indicators.index)

        # Add CBP indicator to reference
        reference = mock_reference_data.copy()
        reference = pd.concat([
            reference,
            pd.DataFrame({
                "Indicator": ["Churches"],
                "Source": ["CBP"],
                "Function": ["divide"],
                "numerator": ["8131"],
                "denominator": ["B01001_001E"],
                "Units": ["ratio"],
                "Augment": ["none"],
                "Order_2023": [4]
            })
        ], ignore_index=True)

        # Add Churches to indicators
        indicators["Churches"] = [10, 5, 8, 12]

        # Add Limited English to reference
        reference = pd.concat([
            reference,
            pd.DataFrame({
                "Indicator": ["Limited English"],
                "Source": ["ACS"],
                "Function": ["divide"],
                "numerator": ["B16001_002E"],
                "denominator": ["B16001_001E"],
                "Units": ["fraction"],
                "Augment": ["reverse"],
                "Order_2023": [5]
            })
        ], ignore_index=True)

        # Add Limited English to indicators
        indicators["Limited English"] = [0.05, 0.04, 0.80, 0.06]

        aggregator = AggregateIndicator(geography="county", bins=5)

        results = aggregator.create_aggregate(
            indicators=indicators,
            reference=reference,
            geo_reference=geo_ref,
            bin_indicators=True
        )

        # Verify Connecticut CBP is handled
        # (Churches should be NaN for GEO_002)
        assert pd.isna(results["indicators"].loc["GEO_002", "Churches"])

        # Verify Puerto Rico Limited English is handled
        # (Limited English should be NaN for GEO_003)
        assert pd.isna(results["indicators"].loc["GEO_003", "Limited English"])

    def test_workflow_export_to_excel(
        self,
        mock_reference_data,
        mock_geography_data,
        tmp_path
    ):
        """Test complete workflow with Excel export."""
        from src.core.aggregator import AggregateIndicator

        indicators = pd.DataFrame({
            "Poverty": [0.15, 0.12, 0.20],
            "GINI": [0.45, 0.42, 0.48],
            "Unemployment": [0.08, 0.06, 0.10],
        }, index=["GEO_001", "GEO_002", "GEO_003"])

        aggregator = AggregateIndicator(geography="county", bins=5)

        results = aggregator.create_aggregate(
            indicators=indicators,
            reference=mock_reference_data,
            geo_reference=mock_geography_data,
            bin_indicators=True
        )

        # Save to Excel
        output_file = tmp_path / "test_workflow_results.xlsx"

        aggregator.save_to_excel(
            results=results,
            file_path=str(output_file),
            include_geo=True,
            geo_reference=mock_geography_data
        )

        # Verify file exists
        assert output_file.exists()

        # Verify file is readable
        saved_sheets = pd.read_excel(output_file, sheet_name=None)

        # Should have multiple sheets
        assert len(saved_sheets) > 0

        # Check key sheets exist
        expected_sheets = ["indicators", "pos", "scores", "agg"]
        for sheet in expected_sheets:
            assert sheet in saved_sheets

    def test_workflow_with_custom_bins(self, mock_reference_data):
        """Test workflow with different bin counts."""
        from src.core.aggregator import AggregateIndicator

        indicators = pd.DataFrame({
            "Poverty": np.random.rand(50),
            "GINI": np.random.rand(50),
            "Unemployment": np.random.rand(50),
        }, index=[f"GEO_{i:03d}" for i in range(50)])

        # County: 5 bins
        agg_county = AggregateIndicator(geography="county", bins=5)
        results_county = agg_county.create_aggregate(
            indicators=indicators,
            reference=mock_reference_data,
            bin_indicators=True
        )

        # Tract: 7 bins
        agg_tract = AggregateIndicator(geography="tract", bins=7)
        results_tract = agg_tract.create_aggregate(
            indicators=indicators,
            reference=mock_reference_data,
            bin_indicators=True
        )

        # Verify bins
        for col in indicators.columns:
            bin_col = f"{col}_bins"

            # County should have 5 bins
            if bin_col in results_county["bin_labels"].columns:
                assert results_county["bin_labels"][bin_col].max() <= 5

            # Tract should have 7 bins
            if bin_col in results_tract["bin_labels"].columns:
                assert results_tract["bin_labels"][bin_col].max() <= 7

    def test_workflow_with_exceptions(self, mock_reference_data):
        """Test workflow with binning exceptions."""
        from src.core.aggregator import AggregateIndicator

        # Create data that might challenge certain binning methods
        indicators = pd.DataFrame({
            "Poverty": [0] * 25 + list(np.random.rand(25)),  # Many zeros
            "GINI": np.random.rand(50),
            "Unemployment": np.random.rand(50),
        }, index=[f"GEO_{i:03d}" for i in range(50)])

        exceptions = {
            "Poverty": ["jenks_caspall", "fisher_jenks"],  # Skip slow methods
        }

        aggregator = AggregateIndicator(geography="county", bins=5)

        results = aggregator.create_aggregate(
            indicators=indicators,
            reference=mock_reference_data,
            bin_indicators=True,
            exceptions=exceptions
        )

        # Should complete successfully
        assert "bin_labels" in results
        assert "Poverty_bins" in results["bin_labels"].columns

    def test_workflow_handles_missing_data(self, mock_reference_data):
        """Test that workflow gracefully handles missing data."""
        from src.core.aggregator import AggregateIndicator

        # Create data with missing values
        indicators = pd.DataFrame({
            "Poverty": [np.nan if i % 5 == 0 else np.random.rand()
                       for i in range(30)],
            "GINI": [np.nan if i % 7 == 0 else np.random.rand()
                    for i in range(30)],
            "Unemployment": np.random.rand(30),
        }, index=[f"GEO_{i:03d}" for i in range(30)])

        aggregator = AggregateIndicator(geography="county", bins=5)

        results = aggregator.create_aggregate(
            indicators=indicators,
            reference=mock_reference_data,
            bin_indicators=True
        )

        # Should complete successfully with imputation
        assert "agg" in results

        # Cleaned indicators should have fewer NaN values
        original_nan_count = indicators.isna().sum().sum()
        cleaned_nan_count = results["indicators"].isna().sum().sum()

        assert cleaned_nan_count <= original_nan_count


@pytest.mark.slow
class TestLargeScaleWorkflow:
    """Tests for large-scale CRIA workflows."""

    def test_tract_level_workflow_large_dataset(self):
        """Test tract-level workflow with large dataset (~1000 tracts)."""
        from src.core.aggregator import AggregateIndicator

        np.random.seed(789)
        n_tracts = 1000

        # Create reference
        reference = pd.DataFrame({
            "Indicator": ["Poverty", "GINI", "Unemployment", "Median Income"],
            "Source": ["ACS", "ACS", "ACS", "ACS"],
            "Function": ["divide"] * 4,
            "numerator": ["B17001_002E", "B19083_001E", "B23025_005E", "B19013_001E"],
            "denominator": ["B17001_001E", "1", "B23025_002E", "1"],
            "Units": ["fraction", "index", "fraction", "dollars"],
            "Augment": ["reverse", "reverse", "reverse", "none"],
            "Order_2023": [1, 2, 3, 4]
        })

        # Create indicators
        indicators = pd.DataFrame({
            "Poverty": np.random.beta(2, 5, n_tracts),
            "GINI": np.random.uniform(0.3, 0.6, n_tracts),
            "Unemployment": np.random.beta(2, 8, n_tracts),
            "Median Income": np.random.normal(50000, 15000, n_tracts),
        }, index=[f"TRACT_{i:05d}" for i in range(n_tracts)])

        aggregator = AggregateIndicator(geography="tract", bins=7)

        results = aggregator.create_aggregate(
            indicators=indicators,
            reference=reference,
            bin_indicators=True
        )

        # Verify all tracts processed
        assert len(results["agg"]) == n_tracts

        # Verify bins are valid
        for col in indicators.columns:
            bin_col = f"{col}_bins"
            if bin_col in results["bin_labels"].columns:
                assert results["bin_labels"][bin_col].min() >= 1
                assert results["bin_labels"][bin_col].max() <= 7

        # Verify percentiles span full range
        assert results["agg"]["cria_p"].min() < 0.05
        assert results["agg"]["cria_p"].max() > 0.95
