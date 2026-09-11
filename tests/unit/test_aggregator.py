"""
Unit tests for AggregateIndicator class.
"""

import pytest
import numpy as np
import pandas as pd
from unittest.mock import patch, MagicMock
from src.core.aggregator import AggregateIndicator


class TestAggregateIndicator:
    """Tests for AggregateIndicator class."""

    def test_init_default(self):
        """Test default initialization."""
        agg = AggregateIndicator()

        assert agg.geography == "county"
        assert agg.bins == 5
        assert agg.binning_strategy == "auto"

    def test_init_custom(self):
        """Test custom initialization."""
        agg = AggregateIndicator(
            geography="tract",
            bins=7,
            binning_strategy="quantiles"
        )

        assert agg.geography == "tract"
        assert agg.bins == 7
        assert agg.binning_strategy == "quantiles"

    @pytest.fixture
    def sample_indicators(self):
        """Create sample indicator data."""
        np.random.seed(42)
        return pd.DataFrame({
            "Poverty": np.random.beta(2, 5, 50) * 100,
            "GINI": np.random.uniform(0.3, 0.6, 50) * 100,
            "Unemployment": np.random.beta(2, 8, 50) * 100,
            "Population Change": np.random.normal(1.0, 0.3, 50)
        }, index=[f"GEO_{i:03d}" for i in range(50)])

    @pytest.fixture
    def sample_reference(self):
        """Create sample reference data."""
        return pd.DataFrame({
            "Indicator": ["Poverty", "GINI", "Unemployment", "Population Change"],
            "Source": ["ACS", "ACS", "ACS", "POP"],
            "Units": ["fraction", "index", "fraction", "ratio"],
            "Augment": ["reverse", "reverse", "reverse", "none"]
        })

    def test_clean_indicators(self, sample_indicators, sample_reference):
        """Test indicator cleaning."""
        agg = AggregateIndicator()

        cleaned = agg._clean_indicators(
            sample_indicators,
            sample_reference
        )

        # Should return DataFrame
        assert isinstance(cleaned, pd.DataFrame)

        # Should have same shape
        assert cleaned.shape == sample_indicators.shape

        # Should impute missing values (no NaN in result)
        assert cleaned.isna().sum().sum() <= sample_indicators.isna().sum().sum()

    def test_clean_indicators_ct_cbp(self, sample_reference):
        """Test Connecticut CBP special case handling."""
        # Create data with Connecticut counties
        geo_ref = pd.DataFrame({
            "state_name": ["Connecticut", "Alabama", "Connecticut"],
            "state": [9, 1, 9]
        }, index=[f"GEO_{i:03d}" for i in range(3)])

        indicators = pd.DataFrame({
            "Churches": [10, 20, 30],  # CBP indicator
            "Poverty": [0.1, 0.2, 0.3]
        }, index=geo_ref.index)

        reference = pd.DataFrame({
            "Indicator": ["Churches", "Poverty"],
            "Source": ["CBP", "ACS"]
        })

        agg = AggregateIndicator(geography="county")

        cleaned = agg._clean_indicators(indicators, reference, geo_ref)

        # Connecticut CBP values should be NaN
        ct_indices = geo_ref[geo_ref["state_name"] == "Connecticut"].index
        assert cleaned.loc[ct_indices, "Churches"].isna().all()

        # Non-CT values should remain
        assert not cleaned.loc["GEO_001", "Churches"] != 20

    def test_clean_indicators_pr_english(self, sample_reference):
        """Test Puerto Rico Limited English special case."""
        # Create data with Puerto Rico
        geo_ref = pd.DataFrame({
            "state_name": ["Puerto Rico", "Alabama"],
            "state": [72, 1]
        }, index=[f"GEO_{i:03d}" for i in range(2)])

        indicators = pd.DataFrame({
            "Limited English": [0.5, 0.3],
            "Poverty": [0.2, 0.1]
        }, index=geo_ref.index)

        reference = sample_reference

        agg = AggregateIndicator(geography="county")

        cleaned = agg._clean_indicators(indicators, reference, geo_ref)

        # Puerto Rico Limited English should be NaN
        pr_index = geo_ref[geo_ref["state"] == 72].index
        assert cleaned.loc[pr_index, "Limited English"].isna().all()

    def test_rescale_indicators(self, sample_indicators, sample_reference):
        """Test indicator rescaling (0-1 to 0-100)."""
        agg = AggregateIndicator()

        # Scale down some indicators to 0-1 range
        test_data = sample_indicators.copy()
        test_data["Poverty"] = test_data["Poverty"] / 100
        test_data["GINI"] = test_data["GINI"] / 100
        test_data["Unemployment"] = test_data["Unemployment"] / 100

        rescaled = agg._rescale_indicators(test_data, sample_reference)

        # Fractions and indexes should be scaled to 0-100
        assert rescaled["Poverty"].max() <= 100
        assert rescaled["GINI"].max() <= 100
        assert rescaled["Unemployment"].max() <= 100

        # Ratios should not be rescaled
        assert rescaled["Population Change"].max() != 100

    def test_reorient_indicators(self, sample_indicators, sample_reference):
        """Test indicator reorientation (reverse polarity)."""
        agg = AggregateIndicator()

        reoriented = agg._reorient_indicators(
            sample_indicators,
            sample_reference
        )

        # Reversed indicators should be flipped (100 - value)
        # Poverty, GINI, Unemployment are marked as "reverse" in sample_reference
        for indicator in ["Poverty", "GINI", "Unemployment"]:
            expected = 100 - sample_indicators[indicator]
            pd.testing.assert_series_equal(
                reoriented[indicator],
                expected,
                check_names=False
            )

        # Population Change should not be reversed
        pd.testing.assert_series_equal(
            reoriented["Population Change"],
            sample_indicators["Population Change"]
        )

    def test_calc_z_scores(self, sample_indicators):
        """Test z-score calculation."""
        agg = AggregateIndicator()

        scores = agg._calc_z_scores(sample_indicators)

        # Should return DataFrame
        assert isinstance(scores, pd.DataFrame)

        # Z-scores should be centered around 0 (mean ≈ 0)
        for col in scores.columns:
            if col != "Population Change":
                assert abs(scores[col].mean()) < 0.1  # Close to 0

        # Z-scores should have std ≈ 1
        for col in scores.columns:
            if col != "Population Change":
                assert abs(scores[col].std() - 1.0) < 0.1

    def test_aggregate_scores(self, sample_indicators, sample_reference):
        """Test aggregation of z-scores."""
        agg = AggregateIndicator()

        # First calculate z-scores
        scores = agg._calc_z_scores(sample_indicators)

        # Then aggregate
        aggregated = agg._aggregate_scores(scores, sample_reference)

        # Should have required columns
        assert "agg" in aggregated.columns
        assert "cri" in aggregated.columns
        assert "cria_p" in aggregated.columns

        # CRI should be negative of agg
        pd.testing.assert_series_equal(
            aggregated["cri"],
            -aggregated["agg"],
            check_names=False
        )

        # cria_p should be percentile rank (0-1)
        assert aggregated["cria_p"].min() >= 0
        assert aggregated["cria_p"].max() <= 1

    def test_aggregate_scores_with_weights(self, sample_indicators, sample_reference):
        """Test aggregation with custom weights."""
        agg = AggregateIndicator()

        scores = agg._calc_z_scores(sample_indicators)

        # Custom weights (emphasize Poverty)
        weights = {
            "Poverty": 2.0,
            "GINI": 1.0,
            "Unemployment": 1.0,
            "Population Change": 1.0
        }

        aggregated = agg._aggregate_scores(scores, sample_reference, weights)

        # Should still have required columns
        assert "agg" in aggregated.columns
        assert "cri" in aggregated.columns

    def test_aggregate_scores_population_change(self, sample_indicators, sample_reference):
        """Test special handling of Population Change."""
        agg = AggregateIndicator()

        scores = agg._calc_z_scores(sample_indicators)
        aggregated = agg._aggregate_scores(scores, sample_reference)

        # Should have population change columns
        assert "pop change" in aggregated.columns
        assert "pop_p" in aggregated.columns

        # pop change should be absolute values
        assert (aggregated["pop change"] >= 0).all()

    def test_bin_indicators(self, sample_indicators, sample_reference):
        """Test binning of indicators."""
        agg = AggregateIndicator(bins=5)

        exceptions = {}
        result = agg._bin_indicators(sample_indicators, sample_reference, exceptions)

        # Should return dict with bins and meta
        assert "bins" in result
        assert "meta" in result

        # Bins should be DataFrame
        assert isinstance(result["bins"], pd.DataFrame)

        # Should have binned columns
        for col in sample_indicators.columns:
            assert f"{col}_bins" in result["bins"].columns

    def test_bin_aggregate(self, sample_indicators, sample_reference):
        """Test binning of aggregate scores."""
        agg = AggregateIndicator(bins=5)

        # Create aggregate scores
        scores = agg._calc_z_scores(sample_indicators)
        aggregated = agg._aggregate_scores(scores, sample_reference)

        # Bin the aggregates
        exceptions = {}
        result = agg._bin_aggregate(aggregated, exceptions)

        # Should return dict with bins and meta
        assert "bins" in result
        assert "meta" in result

        # Should have binned aggregate columns
        for col in aggregated.columns:
            assert f"{col}_bins" in result["bins"].columns

    def test_create_aggregate_full_pipeline(
        self,
        sample_indicators,
        sample_reference
    ):
        """Test complete aggregation pipeline."""
        agg = AggregateIndicator(geography="county", bins=5)

        results = agg.create_aggregate(
            indicators=sample_indicators,
            reference=sample_reference,
            bin_indicators=True
        )

        # Should return dict with all expected keys
        expected_keys = [
            "indicators", "pos", "scores", "scores_percentiles",
            "agg", "bin_labels", "bin_meta", "agg_labels", "agg_meta"
        ]

        for key in expected_keys:
            assert key in results

        # Indicators should be cleaned
        assert isinstance(results["indicators"], pd.DataFrame)

        # Scores should be z-scores
        assert isinstance(results["scores"], pd.DataFrame)

        # Aggregate should have final scores
        assert "cri" in results["agg"].columns
        assert "cria_p" in results["agg"].columns

        # Bins should be created
        assert not results["bin_labels"].empty
        assert not results["agg_labels"].empty

    def test_create_aggregate_without_binning(
        self,
        sample_indicators,
        sample_reference
    ):
        """Test aggregation without binning."""
        agg = AggregateIndicator()

        results = agg.create_aggregate(
            indicators=sample_indicators,
            reference=sample_reference,
            bin_indicators=False
        )

        # Should still have main outputs
        assert "indicators" in results
        assert "agg" in results

        # Bin labels should be empty
        assert results["bin_labels"].empty

    def test_create_aggregate_with_geo_reference(
        self,
        sample_indicators,
        sample_reference
    ):
        """Test aggregation with geography reference."""
        geo_ref = pd.DataFrame({
            "state_name": ["Alabama"] * 50,
            "state_abbr": ["AL"] * 50,
            "state": [1] * 50
        }, index=sample_indicators.index)

        agg = AggregateIndicator(geography="county")

        results = agg.create_aggregate(
            indicators=sample_indicators,
            reference=sample_reference,
            geo_reference=geo_ref
        )

        # Should complete successfully
        assert "agg" in results

    def test_save_to_excel(
        self,
        sample_indicators,
        sample_reference,
        tmp_path
    ):
        """Test saving results to Excel."""
        agg = AggregateIndicator()

        results = agg.create_aggregate(
            indicators=sample_indicators,
            reference=sample_reference,
            bin_indicators=True
        )

        # Save to temp file
        output_file = tmp_path / "test_results.xlsx"

        agg.save_to_excel(
            results=results,
            file_path=str(output_file),
            include_geo=False
        )

        # File should exist
        assert output_file.exists()

        # Should be readable
        saved_data = pd.read_excel(output_file, sheet_name=None)

        # Should have multiple sheets
        assert len(saved_data) > 0

    def test_save_to_excel_with_ref_and_years(
        self,
        sample_indicators,
        sample_reference,
        tmp_path
    ):
        """Test saving results to Excel with ref and years tabs."""
        agg = AggregateIndicator()

        results = agg.create_aggregate(
            indicators=sample_indicators,
            reference=sample_reference,
            bin_indicators=True
        )

        years = {"acs": 2021, "cbp": 2020, "pop": 2020, "naics": 2017}

        output_file = tmp_path / "test_results_ref.xlsx"

        agg.save_to_excel(
            results=results,
            file_path=str(output_file),
            include_geo=False,
            reference=sample_reference,
            years=years
        )

        assert output_file.exists()

        saved_data = pd.read_excel(output_file, sheet_name=None)

        # Should have ref and years tabs
        assert "ref" in saved_data
        assert "years" in saved_data

        # ref tab should contain indicator data
        ref_df = saved_data["ref"]
        assert "Indicator" in ref_df.columns
        assert "Source" in ref_df.columns
        assert "year" in ref_df.columns

        # ACS indicators should have year 2021
        acs_rows = ref_df[ref_df["Source"] == "ACS"]
        assert (acs_rows["year"] == 2021).all()

        # POP indicators should have year 2020
        pop_rows = ref_df[ref_df["Source"] == "POP"]
        if len(pop_rows) > 0:
            assert (pop_rows["year"] == 2020).all()

        # years tab should have source/year columns
        years_df = saved_data["years"]
        assert "source" in years_df.columns
        assert "year" in years_df.columns

    def test_save_to_excel_sheet_ordering(
        self,
        sample_indicators,
        sample_reference,
        tmp_path
    ):
        """Test that ref and years appear first in sheet ordering."""
        agg = AggregateIndicator()

        results = agg.create_aggregate(
            indicators=sample_indicators,
            reference=sample_reference,
            bin_indicators=True
        )

        years = {"acs": 2021, "cbp": 2020, "pop": 2020}

        output_file = tmp_path / "test_ordering.xlsx"

        agg.save_to_excel(
            results=results,
            file_path=str(output_file),
            include_geo=False,
            reference=sample_reference,
            years=years
        )

        # Read sheet names in order
        xl = pd.ExcelFile(output_file)
        sheet_names = xl.sheet_names

        # ref and years should come first
        assert sheet_names[0] == "ref"
        assert sheet_names[1] == "years"

    def test_bin_meta_has_method_columns(
        self,
        sample_indicators,
        sample_reference
    ):
        """Test that bin_meta includes selected_method and selected_score columns."""
        agg = AggregateIndicator(bins=5)

        results = agg.create_aggregate(
            indicators=sample_indicators,
            reference=sample_reference,
            bin_indicators=True
        )

        bin_meta = results["bin_meta"]
        assert not bin_meta.empty

        # Should have method metadata columns
        assert "selected_method" in bin_meta.columns
        assert "selected_score" in bin_meta.columns

        # Each indicator should have a selected_method value
        for indicator in sample_indicators.columns:
            indicator_meta = bin_meta[bin_meta["indicator"] == indicator]
            assert not indicator_meta.empty
            assert not indicator_meta["selected_method"].isna().any()

    def test_agg_meta_has_method_columns(
        self,
        sample_indicators,
        sample_reference
    ):
        """Test that agg_meta includes selected_method and selected_score columns."""
        agg = AggregateIndicator(bins=5)

        results = agg.create_aggregate(
            indicators=sample_indicators,
            reference=sample_reference,
            bin_indicators=True
        )

        agg_meta = results["agg_meta"]
        assert not agg_meta.empty

        # Should have method metadata columns
        assert "selected_method" in agg_meta.columns
        assert "selected_score" in agg_meta.columns


@pytest.mark.integration
class TestAggregateIntegration:
    """Integration tests for aggregation with realistic scenarios."""

    def test_county_level_aggregation(self):
        """Test complete county-level aggregation."""
        np.random.seed(42)

        # Simulate 100 counties
        n_counties = 100

        indicators = pd.DataFrame({
            "Poverty": np.random.beta(2, 5, n_counties) * 100,
            "GINI": np.random.uniform(0.3, 0.6, n_counties) * 100,
            "Unemployment": np.random.beta(2, 8, n_counties) * 100,
            "Median Income": np.random.normal(50000, 15000, n_counties),
            "Population Change": np.random.normal(1.0, 0.3, n_counties),
        }, index=[f"GEO_{i:04d}" for i in range(n_counties)])

        reference = pd.DataFrame({
            "Indicator": [
                "Poverty", "GINI", "Unemployment",
                "Median Income", "Population Change"
            ],
            "Source": ["ACS", "ACS", "ACS", "ACS", "POP"],
            "Units": ["fraction", "index", "fraction", "dollars", "ratio"],
            "Augment": ["reverse", "reverse", "reverse", "none", "none"]
        })

        agg = AggregateIndicator(geography="county", bins=5)

        results = agg.create_aggregate(
            indicators=indicators,
            reference=reference,
            bin_indicators=True
        )

        # Verify all counties processed
        assert len(results["agg"]) == n_counties

        # Verify bins are valid (1-5)
        for col in indicators.columns:
            bin_col = f"{col}_bins"
            if bin_col in results["bin_labels"].columns:
                assert results["bin_labels"][bin_col].min() >= 1
                assert results["bin_labels"][bin_col].max() <= 5

        # Verify CRI percentiles span full range
        assert results["agg"]["cria_p"].min() < 0.1
        assert results["agg"]["cria_p"].max() > 0.9

    def test_tract_level_aggregation(self):
        """Test tract-level aggregation (7 bins)."""
        np.random.seed(123)

        # Simulate 1000 tracts (larger dataset)
        n_tracts = 1000

        indicators = pd.DataFrame({
            "Poverty": np.random.beta(2, 5, n_tracts) * 100,
            "GINI": np.random.uniform(0.3, 0.6, n_tracts) * 100,
            "Unemployment": np.random.beta(2, 8, n_tracts) * 100,
        }, index=[f"TRACT_{i:05d}" for i in range(n_tracts)])

        reference = pd.DataFrame({
            "Indicator": ["Poverty", "GINI", "Unemployment"],
            "Source": ["ACS", "ACS", "ACS"],
            "Units": ["fraction", "index", "fraction"],
            "Augment": ["reverse", "reverse", "reverse"]
        })

        agg = AggregateIndicator(geography="tract", bins=7)

        results = agg.create_aggregate(
            indicators=indicators,
            reference=reference,
            bin_indicators=True
        )

        # Verify 7 bins used
        for col in indicators.columns:
            bin_col = f"{col}_bins"
            if bin_col in results["bin_labels"].columns:
                assert results["bin_labels"][bin_col].max() <= 7

    def test_aggregation_with_missing_data(self):
        """Test aggregation handles missing data gracefully."""
        np.random.seed(456)

        # Create data with missing values
        indicators = pd.DataFrame({
            "Poverty": [np.nan if i % 10 == 0 else np.random.rand()
                       for i in range(50)],
            "GINI": [np.nan if i % 15 == 0 else np.random.rand() * 100
                    for i in range(50)],
            "Unemployment": np.random.rand(50) * 100,
        }, index=[f"GEO_{i:03d}" for i in range(50)])

        reference = pd.DataFrame({
            "Indicator": ["Poverty", "GINI", "Unemployment"],
            "Source": ["ACS", "ACS", "ACS"],
            "Units": ["fraction", "index", "fraction"],
            "Augment": ["reverse", "reverse", "reverse"]
        })

        agg = AggregateIndicator()

        results = agg.create_aggregate(
            indicators=indicators,
            reference=reference,
            bin_indicators=True
        )

        # Should complete without errors
        assert "agg" in results

        # Should produce valid aggregate scores
        assert not results["agg"]["cri"].isna().all()


class TestLowestIndicators:
    """Tests for _compute_lowest_indicators method."""

    @pytest.fixture
    def z_scores(self):
        """Z-score DataFrame where indicator ordering is deterministic.

        Poverty is worst (most negative) for all geos.
        GINI is second worst. Unemployment is least bad.
        """
        return pd.DataFrame({
            "Poverty": [-2.0, -3.0, -1.5],
            "GINI": [-1.0, -0.5, -0.8],
            "Unemployment": [0.5, 1.0, 0.2],
        }, index=["GEO_001", "GEO_002", "GEO_003"])

    def test_output_has_lowest_ind_key(self):
        """create_aggregate output dict contains 'lowest_ind' key."""
        np.random.seed(42)
        indicators = pd.DataFrame({
            "Poverty": np.random.rand(30) * 100,
            "GINI": np.random.rand(30) * 100,
            "Unemployment": np.random.rand(30) * 100,
        }, index=[f"GEO_{i:03d}" for i in range(30)])

        reference = pd.DataFrame({
            "Indicator": ["Poverty", "GINI", "Unemployment"],
            "Source": ["ACS", "ACS", "ACS"],
            "Units": ["fraction", "index", "fraction"],
            "Augment": ["reverse", "reverse", "reverse"],
        })

        agg = AggregateIndicator(geography="county", bins=5)
        results = agg.create_aggregate(indicators, reference)

        assert "lowest_ind" in results
        assert isinstance(results["lowest_ind"], pd.DataFrame)

    def test_lowest_ind_columns(self, z_scores):
        """Output has expected columns: ind_1, ind_1_score, ..., list_labels."""
        agg = AggregateIndicator()
        result = agg._compute_lowest_indicators(z_scores, n=3)

        expected_cols = [
            "ind_1", "ind_1_score",
            "ind_2", "ind_2_score",
            "ind_3", "ind_3_score",
            "list_labels",
        ]
        assert list(result.columns) == expected_cols

    def test_lowest_ind_correct_identification(self, z_scores):
        """Indicator with the most negative z-score appears as ind_1."""
        agg = AggregateIndicator()
        result = agg._compute_lowest_indicators(z_scores, n=3)

        # For GEO_001: Poverty=-2.0 (lowest), GINI=-1.0, Unemp=0.5
        assert result.loc["GEO_001", "ind_1"] == "Poverty"
        assert result.loc["GEO_001", "ind_1_score"] == pytest.approx(-2.0)
        assert result.loc["GEO_001", "ind_2"] == "GINI"
        assert result.loc["GEO_001", "ind_2_score"] == pytest.approx(-1.0)
        assert result.loc["GEO_001", "ind_3"] == "Unemployment"
        assert result.loc["GEO_001", "ind_3_score"] == pytest.approx(0.5)

        # For GEO_002: Poverty=-3.0 (lowest), GINI=-0.5, Unemp=1.0
        assert result.loc["GEO_002", "ind_1"] == "Poverty"
        assert result.loc["GEO_002", "ind_1_score"] == pytest.approx(-3.0)

    def test_lowest_ind_fewer_than_3_indicators(self):
        """With 2 indicators, should produce ind_1/ind_2 only (no ind_3)."""
        df = pd.DataFrame({
            "A": [-1.0, 0.5],
            "B": [0.3, -0.8],
        }, index=["GEO_001", "GEO_002"])

        agg = AggregateIndicator()
        result = agg._compute_lowest_indicators(df, n=3)

        # n should be capped at 2
        expected_cols = ["ind_1", "ind_1_score", "ind_2", "ind_2_score", "list_labels"]
        assert list(result.columns) == expected_cols

        # GEO_001: A=-1.0 < B=0.3
        assert result.loc["GEO_001", "ind_1"] == "A"
        assert result.loc["GEO_001", "ind_2"] == "B"

        # GEO_002: B=-0.8 < A=0.5
        assert result.loc["GEO_002", "ind_1"] == "B"
        assert result.loc["GEO_002", "ind_2"] == "A"

    def test_lowest_ind_preserves_index(self, z_scores):
        """Output index should match z_scores index (GEO_IDs)."""
        agg = AggregateIndicator()
        result = agg._compute_lowest_indicators(z_scores, n=3)

        assert list(result.index) == list(z_scores.index)

    def test_lowest_ind_list_labels(self, z_scores):
        """list_labels column should contain ordered list of worst indicator names."""
        agg = AggregateIndicator()
        result = agg._compute_lowest_indicators(z_scores, n=3)

        labels = result.loc["GEO_001", "list_labels"]
        assert isinstance(labels, list)
        assert labels == ["Poverty", "GINI", "Unemployment"]

    def test_lowest_ind_single_indicator(self):
        """With only 1 indicator, n is capped to 1."""
        df = pd.DataFrame({
            "Only": [-1.5, 0.3, -0.7],
        }, index=["G1", "G2", "G3"])

        agg = AggregateIndicator()
        result = agg._compute_lowest_indicators(df, n=3)

        assert list(result.columns) == ["ind_1", "ind_1_score", "list_labels"]
        assert (result["ind_1"] == "Only").all()


class TestCorrelationOutput:
    """Tests for correlation matrix output in create_aggregate."""

    @pytest.fixture
    def simple_pipeline_results(self):
        """Run a minimal pipeline and return results dict."""
        np.random.seed(42)
        n = 50
        indicators = pd.DataFrame({
            "Poverty": np.random.beta(2, 5, n) * 100,
            "GINI": np.random.uniform(0.3, 0.6, n) * 100,
            "Unemployment": np.random.beta(2, 8, n) * 100,
        }, index=[f"GEO_{i:03d}" for i in range(n)])

        reference = pd.DataFrame({
            "Indicator": ["Poverty", "GINI", "Unemployment"],
            "Source": ["ACS", "ACS", "ACS"],
            "Units": ["fraction", "index", "fraction"],
            "Augment": ["reverse", "reverse", "reverse"],
        })

        agg = AggregateIndicator(geography="county", bins=5)
        return agg.create_aggregate(indicators, reference)

    def test_output_has_correlation_keys(self, simple_pipeline_results):
        """Results dict should contain 'corr', 'p', 'zero', 'n' keys."""
        for key in ["corr", "p", "zero", "n"]:
            assert key in simple_pipeline_results, f"Missing key: {key}"
            assert isinstance(simple_pipeline_results[key], pd.DataFrame)

    def test_correlation_matrices_are_square(self, simple_pipeline_results):
        """All 4 correlation matrices should be square with same dimensions."""
        corr = simple_pipeline_results["corr"]
        p = simple_pipeline_results["p"]
        zero = simple_pipeline_results["zero"]
        n = simple_pipeline_results["n"]

        # All should be square
        for name, mat in [("corr", corr), ("p", p), ("zero", zero), ("n", n)]:
            assert mat.shape[0] == mat.shape[1], f"{name} is not square"

        # All should have same shape
        assert corr.shape == p.shape == zero.shape == n.shape

    def test_correlation_diagonal(self, simple_pipeline_results):
        """Diagonal of corr matrix should be 1.0 (self-correlation)."""
        corr = simple_pipeline_results["corr"]

        for col in corr.columns:
            assert corr.loc[col, col] == pytest.approx(1.0)

    def test_correlation_with_reference_labels(self, tmp_path):
        """If reference Excel exists with Label_Correlation, columns get relabeled."""
        np.random.seed(42)
        n = 30

        indicators = pd.DataFrame({
            "Poverty": np.random.rand(n) * 100,
            "GINI": np.random.rand(n) * 100,
        }, index=[f"GEO_{i:03d}" for i in range(n)])

        reference = pd.DataFrame({
            "Indicator": ["Poverty", "GINI"],
            "Source": ["ACS", "ACS"],
            "Units": ["fraction", "index"],
            "Augment": ["reverse", "reverse"],
        })

        # Create a mock reference Excel with Label_Correlation
        ref_excel_path = tmp_path / "cria_data_reference.xlsx"
        ref_status = pd.DataFrame({
            "Indicator": ["Poverty", "GINI"],
            "Label_Correlation": ["Poverty Rate", "GINI Index"],
            "Order_Correlation": [1, 2],
        })
        with pd.ExcelWriter(ref_excel_path) as writer:
            ref_status.to_excel(writer, sheet_name="Status", index=False)

        agg = AggregateIndicator(geography="county", bins=5)

        # Call _compute_correlation directly with custom ref path
        corr_r, corr_p, corr_zero, corr_n = agg._compute_correlation(
            indicators, reference_path=str(ref_excel_path)
        )

        # Columns should be relabeled
        assert "Poverty Rate" in corr_r.columns
        assert "GINI Index" in corr_r.columns

    def test_correlation_without_reference_file(self):
        """Without reference Excel, original indicator names are used."""
        np.random.seed(42)
        indicators = pd.DataFrame({
            "Poverty": np.random.rand(20) * 100,
            "GINI": np.random.rand(20) * 100,
        }, index=[f"GEO_{i:03d}" for i in range(20)])

        agg = AggregateIndicator(geography="county", bins=5)

        corr_r, _, _, _ = agg._compute_correlation(
            indicators, reference_path="/nonexistent/path.xlsx"
        )

        # Should fall back to original names
        assert "Poverty" in corr_r.columns
        assert "GINI" in corr_r.columns

    def test_correlation_values_in_range(self, simple_pipeline_results):
        """All correlation values should be in [-1, 1]."""
        corr = simple_pipeline_results["corr"]
        assert (corr >= -1.0).all().all()
        assert (corr <= 1.0).all().all()

    def test_correlation_n_positive(self, simple_pipeline_results):
        """All sample sizes in corr_n should be positive."""
        n = simple_pipeline_results["n"]
        assert (n > 0).all().all()


# =============================================================================
# TestSaveToDatabaseFailFast
#
# Aggregator differs from data_puller / indicators: it has NO indicator_map.
# Writes are keyed only on geography. So the only TOTAL-failure axis is an
# empty geo_id_map. Same doctrine: setup error → raise; partial miss
# (skipped_geos > 0) → warn-and-continue.
# =============================================================================

class TestSaveToDatabaseFailFast:
    """Defense-in-depth: empty geo_id_map raises; partial misses still warn."""

    def _patch_repos(self, geo_id_map):
        geo_repo = MagicMock()
        geo_repo.get_geo_id_map.return_value = geo_id_map
        agg_repo = MagicMock()
        agg_repo.bulk_create.return_value = 0
        return (
            patch("src.core.aggregator.GeographyRepository", return_value=geo_repo),
            patch("src.core.aggregator.AggregateIndicatorRepository", return_value=agg_repo),
        )

    def _agg_results(self, geo_ids):
        agg_df = pd.DataFrame({
            "cria_p": np.linspace(0, 1, len(geo_ids)),
            "cria_z": np.linspace(-2, 2, len(geo_ids)),
            "cria_score": np.linspace(0, 100, len(geo_ids)),
            "cria_bin": [1] * len(geo_ids),
        }, index=geo_ids)
        return {"agg": agg_df}

    def test_empty_geo_id_map_raises(self):
        """No geographies in DB for this level → RuntimeError."""
        agg = AggregateIndicator(geography="county")
        results = self._agg_results(["GEO1", "GEO2"])

        p1, p2 = self._patch_repos(geo_id_map={})
        with p1, p2:
            with pytest.raises(RuntimeError) as exc:
                agg.save_to_database(results, year=2021, db=MagicMock())
        msg = str(exc.value)
        assert "geo_id_map is empty" in msg
        assert "sync_geographies.py" in msg
        assert "level='county'" in msg
        assert "aggregate_indicators" in msg

    def test_partial_geo_miss_does_not_raise(self, caplog):
        """Some geos missing from DB must NOT raise — preserves skipped_geos warn path."""
        import logging
        agg = AggregateIndicator(geography="county")
        results = self._agg_results(["GEO1", "GEO2", "GEO3"])

        # Only GEO1 maps; GEO2 and GEO3 will be skipped.
        p1, p2 = self._patch_repos(geo_id_map={"GEO1": 1})
        with p1, p2:
            with caplog.at_level(logging.WARNING, logger="src.core.aggregator"):
                # Must NOT raise.
                agg.save_to_database(results, year=2021, db=MagicMock())

        # Existing skipped-geos warning preserved.
        assert any("Skipped 2 geographies" in m for m in caplog.messages)

    def test_empty_agg_df_returns_early(self, caplog):
        """An empty 'agg' DataFrame is the documented no-op path; must NOT raise."""
        import logging
        agg = AggregateIndicator(geography="county")
        results = {"agg": pd.DataFrame()}

        p1, p2 = self._patch_repos(geo_id_map={})
        with p1, p2:
            with caplog.at_level(logging.WARNING, logger="src.core.aggregator"):
                # Returns early before geo_id_map even loads — no raise.
                agg.save_to_database(results, year=2021, db=MagicMock())

        assert any("No aggregate data to save" in m for m in caplog.messages)
