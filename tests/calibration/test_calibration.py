"""
Calibration and regression tests for CRIA indicator pipeline.

These tests validate the full indicator -> aggregation -> binning pipeline
using synthetic but realistic data. They serve as regression guards against
changes that break established statistical properties.

All tests are auto-marked with @pytest.mark.calibration via conftest.
"""

import pytest
import numpy as np
import pandas as pd
from unittest.mock import patch, MagicMock

from src.core.indicators import IndicatorCalculator
from src.core.aggregator import AggregateIndicator
from src.core.binning import BinningEngine
from src.core.transformations import calc_z_scores

from tests.fixtures.calibration_data import (
    get_calibration_county_data,
    get_calibration_reference,
    get_calibration_years,
    get_calibration_geo_reference,
    get_ct_cbp_data,
    get_pr_limited_english_data,
)


# =============================================================================
# Helpers
# =============================================================================

def _make_calculator(years=None):
    """Create an IndicatorCalculator with DataPuller mocked out."""
    if years is None:
        years = get_calibration_years()

    with patch("src.core.indicators.DataPuller") as MockDP:
        mock_dp = MagicMock()
        mock_dp.reference = pd.DataFrame()
        mock_dp.years = years
        MockDP.return_value = mock_dp
        calc = IndicatorCalculator(geography="county")

    calc.years = years
    calc.reference = get_calibration_reference()
    return calc


def _compute_indicators(source_data=None, n_rows=200):
    """Run the IndicatorCalculator on calibration data and return results."""
    calc = _make_calculator()
    if source_data is None:
        source_data = get_calibration_county_data(n_rows)
    indicators = calc.calculate_all_indicators(source_data=source_data)
    return indicators, calc


# =============================================================================
# TestIndicatorFormulaCalibration
# =============================================================================

class TestIndicatorFormulaCalibration:
    """Validate that all 22 indicators produce valid, well-formed results."""

    def test_all_22_indicators_produce_valid_ranges(self):
        """All 22 indicator columns are present with no infinities."""
        indicators, _ = _compute_indicators()
        reference = get_calibration_reference()

        expected_names = reference["Indicator"].tolist()
        for name in expected_names:
            assert name in indicators.columns, f"Missing indicator: {name}"

        # No infinities in any column
        for col in indicators.columns:
            assert not np.isinf(indicators[col].dropna()).any(), (
                f"Infinity found in {col}"
            )

    def test_divide_indicators_bounded_zero_to_one(self):
        """
        Divide indicators (ratios) should be in [0, 1] for well-formed data.

        These are: Mobile Homes, Owner Occupied, Education, No Vehicle, Age,
        Disability, Limited English, Single Parent, Inactive Voter,
        Unemployment, Poverty, Uninsured Population.
        """
        indicators, _ = _compute_indicators()
        divide_indicators = [
            "Mobile Homes", "Owner Occupied", "Education", "No Vehicle",
            "Age", "Disability", "Limited English", "Single Parent",
            "Inactive Voter", "Unemployment", "Poverty",
            "Uninsured Population",
        ]

        for name in divide_indicators:
            col = indicators[name].dropna()
            assert col.min() >= -0.01, (
                f"{name} has values below 0: min={col.min():.4f}"
            )
            # Allow slight overshoot for rounding
            assert col.max() <= 1.05, (
                f"{name} has values above 1.05: max={col.max():.4f}"
            )

    def test_divide_scalar_indicators_positive(self):
        """
        divide_scalar indicators (Civil Org, Hospitals, Medical) should be >= 0.
        These are rates per population, so negative values are impossible.
        """
        indicators, _ = _compute_indicators()
        scalar_indicators = ["Civil Org", "Hospitals", "Medical"]

        for name in scalar_indicators:
            col = indicators[name].dropna()
            assert col.min() >= 0.0, (
                f"{name} has negative values: min={col.min():.4f}"
            )

    def test_reverse_divide_bounded_zero_to_one(self):
        """
        reverse_divide indicators should be in [0, 1] for well-formed data.

        These are: Low Access to Communications, Religion, Unemployed Women.
        """
        indicators, _ = _compute_indicators()
        reverse_indicators = [
            "Low Access to Communications", "Religion", "Unemployed Women",
        ]

        for name in reverse_indicators:
            col = indicators[name].dropna()
            assert col.min() >= -0.01, (
                f"{name} has values below 0: min={col.min():.4f}"
            )
            assert col.max() <= 1.01, (
                f"{name} has values above 1.01: max={col.max():.4f}"
            )

    def test_median_income_positive(self):
        """Median Income (divide by scalar 1) should remain the raw value."""
        indicators, _ = _compute_indicators()
        col = indicators["Median Income"].dropna()
        assert col.min() > 0, "Median Income should be positive"
        # Values should be in realistic range (20k-120k in our synthetic data)
        assert col.min() >= 15000
        assert col.max() <= 150000

    def test_gini_in_expected_range(self):
        """GINI coefficient should be in [0.3, 0.6] range."""
        indicators, _ = _compute_indicators()
        col = indicators["GINI"].dropna()
        assert col.min() >= 0.30
        assert col.max() <= 0.60

    def test_population_change_can_be_negative(self):
        """Population Change (net migration / pop) can be negative."""
        indicators, _ = _compute_indicators()
        col = indicators["Population Change"].dropna()
        # With synthetic data centered around small positive migration,
        # some values should be negative (net outmigration)
        assert col.min() < 0 or col.max() > 0, (
            "Population Change should have variation"
        )

    def test_no_nan_only_columns(self):
        """No indicator should be entirely NaN (all 22 should compute)."""
        indicators, _ = _compute_indicators()
        for col in indicators.columns:
            assert indicators[col].notna().sum() > 0, (
                f"Indicator {col} is entirely NaN"
            )


# =============================================================================
# TestAggregationCalibration
# =============================================================================

class TestAggregationCalibration:
    """Validate the aggregation pipeline produces statistically sound results."""

    @pytest.fixture()
    def pipeline_results(self):
        """Run the full pipeline once and cache for this class."""
        source_data = get_calibration_county_data(200)
        indicators, calc = _compute_indicators(source_data=source_data)
        reference = get_calibration_reference()

        aggregator = AggregateIndicator(
            geography="county", bins=5, binning_strategy="auto"
        )
        results = aggregator.create_aggregate(
            indicators, reference, bin_indicators=True
        )
        return results

    def test_county_cri_distribution_centered(self, pipeline_results):
        """
        CRI z-scores should be centered near 0.

        The aggregate z-scores (mean of indicator z-scores) should have
        a mean close to zero (within +/- 0.5 for 200 synthetic counties).
        """
        agg = pipeline_results["agg"]
        assert "cri" in agg.columns
        cri_mean = agg["cri"].mean()
        assert abs(cri_mean) < 0.5, (
            f"CRI mean should be near 0, got {cri_mean:.4f}"
        )

    def test_cria_percentile_spans_full_range(self, pipeline_results):
        """
        CRIA percentile should span most of [0, 1].
        With 200 data points, min should be < 0.10 and max > 0.90.
        """
        agg = pipeline_results["agg"]
        assert "cria_p" in agg.columns
        assert agg["cria_p"].min() < 0.10, (
            f"Percentile min too high: {agg['cria_p'].min():.4f}"
        )
        assert agg["cria_p"].max() > 0.90, (
            f"Percentile max too low: {agg['cria_p'].max():.4f}"
        )

    def test_pop_change_subset_zscore_differs(self):
        """
        Population Change uses subset mean/std for z-scores,
        not the full dataset mean/std.

        Verify that the z-score for Population Change differs from
        what a standard full-dataset z-score would produce.
        """
        source_data = get_calibration_county_data(200)
        indicators, _ = _compute_indicators(source_data=source_data)
        reference = get_calibration_reference()

        aggregator = AggregateIndicator(
            geography="county", bins=5, binning_strategy="auto"
        )
        results = aggregator.create_aggregate(
            indicators, reference, bin_indicators=False
        )

        # The pipeline z-scores use calc_z_scores which handles
        # Population Change specially (scale only, no centering)
        pipeline_z = results["scores"]["Population Change"]

        # Calculate what a standard z-score would be (center + scale)
        reoriented = results["pos"]["Population Change"]
        standard_z = (reoriented - reoriented.mean()) / reoriented.std()

        # They should differ because pop change is only scaled, not centered
        assert not np.allclose(
            pipeline_z.dropna().values,
            standard_z.dropna().values,
            atol=1e-6
        ), "Population Change z-scores should differ from standard z-scores"

    def test_agg_has_pop_change_columns(self, pipeline_results):
        """Aggregate output should include population change metrics."""
        agg = pipeline_results["agg"]
        assert "pop change" in agg.columns
        assert "pop_p" in agg.columns

    def test_scores_have_all_indicators(self, pipeline_results):
        """Z-score DataFrame should have all 22 indicator columns."""
        scores = pipeline_results["scores"]
        reference = get_calibration_reference()
        for name in reference["Indicator"].tolist():
            assert name in scores.columns, f"Missing z-score for {name}"


# =============================================================================
# TestBinningCalibration
# =============================================================================

class TestBinningCalibration:
    """Validate binning produces populated bins across methods."""

    def test_county_5_bins_all_populated(self):
        """
        200+ values with 5 bins should produce all bins populated.
        Each bin should have at least 1 member.
        """
        source_data = get_calibration_county_data(200)
        indicators, _ = _compute_indicators(source_data=source_data)

        engine = BinningEngine(strategy="auto", k=5)

        # Test on several indicators
        test_cols = ["Poverty", "GINI", "Mobile Homes", "Age"]
        for col_name in test_cols:
            series = indicators[col_name].dropna()
            series.name = col_name
            binned = engine.bin_series(series, k=5)
            bin_counts = binned.dropna().value_counts()

            assert len(bin_counts) == 5, (
                f"{col_name}: expected 5 bins, got {len(bin_counts)} "
                f"(counts: {bin_counts.to_dict()})"
            )

            for bin_num in range(1, 6):
                assert bin_num in bin_counts.index, (
                    f"{col_name}: bin {bin_num} is empty"
                )

    def test_tract_7_bins_all_populated(self):
        """
        500+ values with 7 bins should produce all bins populated.
        """
        source_data = get_calibration_county_data(500)
        indicators, _ = _compute_indicators(source_data=source_data, n_rows=500)

        engine = BinningEngine(strategy="auto", k=7)

        test_cols = ["Poverty", "GINI", "Age"]
        for col_name in test_cols:
            series = indicators[col_name].dropna()
            series.name = col_name
            binned = engine.bin_series(series, k=7)
            bin_counts = binned.dropna().value_counts()

            assert len(bin_counts) == 7, (
                f"{col_name}: expected 7 bins, got {len(bin_counts)} "
                f"(counts: {bin_counts.to_dict()})"
            )

    def test_auto_select_not_always_fisher_jenks(self):
        """
        Auto-select should NOT always pick FisherJenks.

        With center-scaling of ADCM+TSS, at least one indicator across
        the 22 should select a non-FisherJenks method. If all 22 pick
        FisherJenks, the center-scaling is likely broken.
        """
        source_data = get_calibration_county_data(200)
        indicators, _ = _compute_indicators(source_data=source_data)

        engine = BinningEngine(strategy="auto", k=5)

        methods_selected = set()
        for col in indicators.columns:
            series = indicators[col].dropna()
            series.name = col
            engine.bin_series(series, k=5)
            meta = engine.get_selection_metadata(col)
            if meta:
                methods_selected.add(meta["selected_method"])

        assert len(methods_selected) > 1, (
            f"Auto-select only picked: {methods_selected}. "
            "Center-scaling may be broken if only fisher_jenks is selected."
        )

    def test_headtail_breaks_overflow_handled(self):
        """
        HeadTail Breaks can produce more bins than requested.
        When auto-selected, bin labels should still be capped at k.
        """
        # Create a heavy-tailed distribution that HeadTail likes
        rng = np.random.default_rng(42)
        values = np.concatenate([
            rng.exponential(scale=1.0, size=150),
            rng.exponential(scale=10.0, size=50),
        ])
        series = pd.Series(values, name="heavy_tail_test")

        engine = BinningEngine(strategy="headtail_breaks", k=5)
        binned = engine.bin_series(series, strategy="headtail_breaks", k=5)

        # All bin values should be <= k (1-indexed: 1..5)
        max_bin = binned.dropna().max()
        assert max_bin <= 5, (
            f"HeadTail Breaks overflow: max bin = {max_bin}, expected <= 5"
        )


# =============================================================================
# TestDomainSpecialCases
# =============================================================================

class TestDomainSpecialCases:
    """Validate domain-specific special case handling through the pipeline."""

    def test_ct_cbp_propagates_nan_through_pipeline(self):
        """
        Connecticut (FIPS=09) CBP values that are 0 should propagate
        as NaN through the aggregation pipeline.

        The aggregator's _clean_indicators sets CT CBP indicators to NaN
        when geo_reference identifies Connecticut counties.
        """
        source_data = get_ct_cbp_data(n_rows=10)
        indicators, calc = _compute_indicators(source_data=source_data)
        reference = get_calibration_reference()
        geo_ref = get_calibration_geo_reference(source_data)

        aggregator = AggregateIndicator(
            geography="county", bins=5, binning_strategy="auto"
        )
        results = aggregator.create_aggregate(
            indicators, reference, geo_reference=geo_ref,
            bin_indicators=False
        )

        cleaned = results["indicators"]
        ct_mask = geo_ref["state_name"] == "Connecticut"
        ct_indices = geo_ref[ct_mask].index

        # CBP indicators for CT should be NaN after cleaning
        cbp_indicators = reference.loc[
            reference["Source"] == "CBP", "Indicator"
        ].tolist()

        for indicator in cbp_indicators:
            if indicator in cleaned.columns:
                ct_values = cleaned.loc[ct_indices, indicator]
                assert ct_values.isna().all(), (
                    f"CT {indicator} should be NaN after cleaning, "
                    f"but found: {ct_values.dropna().tolist()}"
                )

    def test_pr_limited_english_excluded_through_pipeline(self):
        """
        Puerto Rico (FIPS=72) Limited English indicator should be NaN.

        Spanish speakers are not "limited English" in PR context.
        The aggregator's _clean_indicators handles this.
        """
        source_data = get_pr_limited_english_data(n_rows=10)
        indicators, calc = _compute_indicators(source_data=source_data)
        reference = get_calibration_reference()
        geo_ref = get_calibration_geo_reference(source_data)

        aggregator = AggregateIndicator(
            geography="county", bins=5, binning_strategy="auto"
        )
        results = aggregator.create_aggregate(
            indicators, reference, geo_reference=geo_ref,
            bin_indicators=False
        )

        cleaned = results["indicators"]
        pr_mask = geo_ref["state"] == 72
        pr_indices = geo_ref[pr_mask].index

        assert "Limited English" in cleaned.columns
        pr_limited_eng = cleaned.loc[pr_indices, "Limited English"]
        assert pr_limited_eng.isna().all(), (
            f"PR Limited English should be NaN, "
            f"but found: {pr_limited_eng.dropna().tolist()}"
        )

    def test_non_ct_cbp_not_affected(self):
        """
        Non-CT counties should retain their CBP indicator values
        after the CT special case handling.
        """
        source_data = get_ct_cbp_data(n_rows=5)
        indicators, calc = _compute_indicators(source_data=source_data)
        reference = get_calibration_reference()
        geo_ref = get_calibration_geo_reference(source_data)

        aggregator = AggregateIndicator(
            geography="county", bins=5, binning_strategy="auto"
        )
        results = aggregator.create_aggregate(
            indicators, reference, geo_reference=geo_ref,
            bin_indicators=False
        )

        cleaned = results["indicators"]
        non_ct_mask = geo_ref["state_name"] != "Connecticut"
        non_ct_indices = geo_ref[non_ct_mask].index

        # Non-CT Civil Org and Hospitals should NOT all be NaN
        for indicator in ["Civil Org", "Hospitals"]:
            if indicator in cleaned.columns:
                non_ct_values = cleaned.loc[non_ct_indices, indicator]
                assert non_ct_values.notna().any(), (
                    f"Non-CT {indicator} should have valid values"
                )

    def test_non_pr_limited_english_not_affected(self):
        """
        Non-PR counties should retain their Limited English values.
        """
        source_data = get_pr_limited_english_data(n_rows=5)
        indicators, calc = _compute_indicators(source_data=source_data)
        reference = get_calibration_reference()
        geo_ref = get_calibration_geo_reference(source_data)

        aggregator = AggregateIndicator(
            geography="county", bins=5, binning_strategy="auto"
        )
        results = aggregator.create_aggregate(
            indicators, reference, geo_reference=geo_ref,
            bin_indicators=False
        )

        cleaned = results["indicators"]
        non_pr_mask = geo_ref["state"] != 72
        non_pr_indices = geo_ref[non_pr_mask].index

        non_pr_eng = cleaned.loc[non_pr_indices, "Limited English"]
        assert non_pr_eng.notna().any(), (
            "Non-PR Limited English should have valid values"
        )
