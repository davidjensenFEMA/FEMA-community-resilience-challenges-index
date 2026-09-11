"""
Unit tests for BinningEngine class.
"""

import pytest
import numpy as np
import pandas as pd
from src.core.binning import BinningEngine, MANUAL_BINS


class TestBinningEngine:
    """Tests for BinningEngine class."""

    def test_init_default(self):
        """Test default initialization."""
        engine = BinningEngine()

        assert engine.strategy == "quantiles"
        assert engine.k == 5

    def test_init_custom(self):
        """Test custom initialization."""
        engine = BinningEngine(strategy="equal_interval", k=7)

        assert engine.strategy == "equal_interval"
        assert engine.k == 7

    def test_bin_series_quantiles(self):
        """Test binning with quantiles strategy."""
        engine = BinningEngine(strategy="quantiles", k=5)

        # Create test data (10 values)
        series = pd.Series(range(1, 11), name="test")

        # Bin the series
        binned = engine.bin_series(series)

        # Should have 5 bins (1-indexed: 1, 2, 3, 4, 5)
        assert binned.min() == 1
        assert binned.max() == 5
        assert len(binned) == 10

        # Each bin should have approximately equal count (quantiles)
        counts = binned.value_counts()
        assert len(counts) == 5

    def test_bin_series_equal_interval(self):
        """Test binning with equal intervals."""
        engine = BinningEngine(strategy="equal_interval", k=5)

        series = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], name="test")
        binned = engine.bin_series(series)

        # Should have 5 bins
        assert binned.min() == 1
        assert binned.max() == 5

    def test_bin_series_with_nan(self):
        """Test binning with NaN values."""
        engine = BinningEngine(strategy="quantiles", k=5)

        # Series with NaN values
        series = pd.Series([1, 2, np.nan, 4, 5, np.nan, 7, 8, 9, 10], name="test")
        binned = engine.bin_series(series)

        # NaN values should remain NaN in output
        assert binned.isna().sum() == 2

        # Non-NaN values should be binned
        assert binned.dropna().min() == 1
        assert binned.dropna().max() == 5

    def test_bin_series_all_nan(self):
        """Test binning with all NaN values."""
        engine = BinningEngine(strategy="quantiles", k=5)

        series = pd.Series([np.nan, np.nan, np.nan], name="test")
        binned = engine.bin_series(series)

        # All values should be NaN
        assert binned.isna().all()

    def test_bin_series_fewer_values_than_bins(self):
        """Test binning when fewer values than bins."""
        engine = BinningEngine(strategy="quantiles", k=5)

        # Only 3 values, but requesting 5 bins
        series = pd.Series([1, 2, 3], name="test")
        binned = engine.bin_series(series)

        # Should use 3 bins instead
        assert binned.max() <= 3

    def test_bin_dataframe(self):
        """Test binning entire DataFrame."""
        engine = BinningEngine(strategy="quantiles", k=5)

        df = pd.DataFrame({
            "poverty": np.random.rand(20),
            "gini": np.random.rand(20),
            "unemployment": np.random.rand(20)
        })

        result = engine.bin_dataframe(df)

        # Should have original columns plus binned columns
        assert "poverty" in result.columns
        assert "poverty_bins" in result.columns
        assert "gini_bins" in result.columns
        assert "unemployment_bins" in result.columns

        # Binned columns should be 1-indexed
        assert result["poverty_bins"].min() >= 1
        assert result["poverty_bins"].max() <= 5

    def test_bin_dataframe_with_exceptions(self):
        """Test binning DataFrame with method exceptions."""
        engine = BinningEngine(strategy="auto", k=5)

        df = pd.DataFrame({
            "poverty": np.random.rand(20),
            "hospitals": [0] * 10 + list(range(1, 11))  # Lots of zeros
        })

        exceptions = {
            "hospitals": ["jenks_caspall", "fisher_jenks"]
        }

        result = engine.bin_dataframe(df, exceptions_dict=exceptions)

        # Should complete without errors
        assert "poverty_bins" in result.columns
        assert "hospitals_bins" in result.columns

    def test_get_bin_edges(self):
        """Test getting bin edge values."""
        engine = BinningEngine(strategy="quantiles", k=5)

        series = pd.Series(range(1, 11))
        edges = engine.get_bin_edges(series)

        # Should have 5 edge values (for 5 bins)
        assert len(edges) == 5
        assert all(isinstance(x, (int, float)) for x in edges)

    def test_get_bin_counts(self):
        """Test getting bin counts."""
        engine = BinningEngine(strategy="quantiles", k=5)

        series = pd.Series(range(1, 11))
        counts = engine.get_bin_counts(series)

        # Should have counts for 5 bins
        assert len(counts) == 5
        assert sum(counts.values()) == 10  # Total values

    def test_get_metadata(self):
        """Test getting binning metadata."""
        engine = BinningEngine(strategy="quantiles", k=5)

        series = pd.Series(range(1, 11), name="test")
        metadata = engine.get_metadata(series)

        # Should be a DataFrame with metadata
        assert isinstance(metadata, pd.DataFrame)
        assert "bin" in metadata.columns
        assert "count" in metadata.columns
        assert "min" in metadata.columns
        assert "max" in metadata.columns
        assert "mean" in metadata.columns
        assert "median" in metadata.columns

        # Should have 5 rows (one per bin)
        assert len(metadata) == 5

    def test_auto_select_method(self):
        """Test auto method selection."""
        engine = BinningEngine(strategy="auto", k=5)

        # Create data that should work well with auto-selection
        series = pd.Series(
            [1, 1, 2, 3, 5, 8, 13, 21, 34, 55] +  # Fibonacci-like
            [60, 65, 70, 75, 80, 85, 90, 95, 100, 105],
            name="test"
        )

        binned = engine.bin_series(series)

        # Should successfully bin
        assert binned.min() >= 1
        assert binned.max() <= 5
        assert not binned.isna().all()

    def test_auto_select_with_exceptions(self):
        """Test auto selection with excluded methods."""
        engine = BinningEngine(strategy="auto", k=5)

        series = pd.Series(range(1, 21), name="test")

        # Exclude some methods
        exceptions = ["jenks_caspall", "natural_breaks"]

        binned = engine.bin_series(series, exceptions=exceptions)

        # Should still work with remaining methods
        assert binned.min() == 1
        assert binned.max() == 5

    def test_headtail_breaks_adjustment(self):
        """Test that HeadTail Breaks is adjusted to max k bins."""
        engine = BinningEngine(strategy="headtail_breaks", k=5)

        # Create data that might produce more than 5 bins with HeadTail
        series = pd.Series(
            [1] * 50 + [10] * 10 + [100] * 5 + [1000],
            name="test"
        )

        binned = engine.bin_series(series)

        # Should be capped at k=5 bins (actually k-1=4 in 0-index, so 5 in 1-index)
        assert binned.max() <= 5

    def test_bin_series_preserves_index(self):
        """Test that binning preserves original series index."""
        engine = BinningEngine(strategy="quantiles", k=5)

        # Create series with custom index
        series = pd.Series(
            range(1, 11),
            index=["GEO_" + str(i) for i in range(10)],
            name="test"
        )

        binned = engine.bin_series(series)

        # Index should be preserved
        assert list(binned.index) == list(series.index)

    def test_bin_dataframe_custom_suffix(self):
        """Test binning DataFrame with custom suffix."""
        engine = BinningEngine(strategy="quantiles", k=5)

        df = pd.DataFrame({
            "poverty": np.random.rand(10),
            "gini": np.random.rand(10)
        })

        result = engine.bin_dataframe(df, suffix="_class")

        # Should use custom suffix
        assert "poverty_class" in result.columns
        assert "gini_class" in result.columns

    def test_unknown_strategy_fallback(self):
        """Test that unknown strategy falls back to quantiles."""
        engine = BinningEngine(strategy="invalid_method", k=5)

        series = pd.Series(range(1, 11), name="test")
        binned = engine.bin_series(series)

        # Should fall back to quantiles and still work
        assert binned.min() == 1
        assert binned.max() == 5

    def test_bin_series_identical_values(self):
        """Test binning when all values are identical."""
        engine = BinningEngine(strategy="quantiles", k=5)

        # All same value
        series = pd.Series([5.0] * 10, name="test")
        binned = engine.bin_series(series)

        # Should assign to a single bin (or handle gracefully)
        # The exact behavior depends on mapclassify, but shouldn't error
        assert len(binned) == 10
        assert not binned.isna().all()


class TestBinningMethodMetadata:
    """Tests for binning method selection metadata storage."""

    def test_auto_select_stores_metadata(self):
        """Test that auto-selection stores method metadata."""
        engine = BinningEngine(strategy="auto", k=5)

        series = pd.Series(
            [1, 1, 2, 3, 5, 8, 13, 21, 34, 55] +
            [60, 65, 70, 75, 80, 85, 90, 95, 100, 105],
            name="test_indicator"
        )

        engine.bin_series(series)

        meta = engine.get_selection_metadata("test_indicator")
        assert meta is not None
        assert "selected_method" in meta
        assert "selection_type" in meta
        assert "selected_score" in meta
        assert "all_scores" in meta

        assert meta["selection_type"] == "auto"
        assert meta["selected_method"] in [
            "equal_interval", "fisher_jenks", "headtail_breaks",
            "maximum_breaks", "quantiles", "std_mean"
        ]
        assert isinstance(meta["selected_score"], float)
        assert not np.isnan(meta["selected_score"])
        assert len(meta["all_scores"]) > 0

    def test_direct_strategy_stores_metadata(self):
        """Test that a directly-specified strategy records 'direct' selection."""
        engine = BinningEngine(strategy="quantiles", k=5)

        series = pd.Series(range(1, 21), name="direct_test")
        engine.bin_series(series)

        meta = engine.get_selection_metadata("direct_test")
        assert meta is not None
        assert meta["selected_method"] == "quantiles"
        assert meta["selection_type"] == "direct"
        assert np.isnan(meta["selected_score"])
        assert meta["all_scores"] == {}

    def test_bin_dataframe_clears_stale_metadata(self):
        """Test that bin_dataframe clears metadata from previous runs."""
        engine = BinningEngine(strategy="quantiles", k=5)

        # First run
        df1 = pd.DataFrame({"col_a": range(1, 21)})
        engine.bin_dataframe(df1)
        assert engine.get_selection_metadata("col_a") is not None

        # Second run with different columns
        df2 = pd.DataFrame({"col_b": range(1, 21)})
        engine.bin_dataframe(df2)

        # col_a metadata should be cleared
        assert engine.get_selection_metadata("col_a") is None
        # col_b metadata should be present
        assert engine.get_selection_metadata("col_b") is not None

    def test_bin_dataframe_stores_all_columns(self):
        """Test that bin_dataframe stores metadata for all columns."""
        engine = BinningEngine(strategy="auto", k=5)

        np.random.seed(42)
        df = pd.DataFrame({
            "Poverty": np.random.rand(50) * 100,
            "GINI": np.random.rand(50) * 100,
        })

        engine.bin_dataframe(df)

        for col in df.columns:
            meta = engine.get_selection_metadata(col)
            assert meta is not None, f"No metadata for column '{col}'"
            assert meta["selection_type"] == "auto"

    def test_get_metadata_includes_method_columns(self):
        """Test that get_metadata() includes selected_method and selected_score."""
        engine = BinningEngine(strategy="auto", k=5)

        series = pd.Series(range(1, 21), name="test_meta")
        metadata = engine.get_metadata(series)

        assert "selected_method" in metadata.columns
        assert "selected_score" in metadata.columns

        # All rows should have the same method and score
        assert metadata["selected_method"].nunique() == 1
        assert not metadata["selected_method"].isna().any()

    def test_get_metadata_direct_strategy_columns(self):
        """Test that get_metadata() for direct strategy has NaN score."""
        engine = BinningEngine(strategy="quantiles", k=5)

        series = pd.Series(range(1, 21), name="direct_meta_test")
        metadata = engine.get_metadata(series)

        assert "selected_method" in metadata.columns
        assert "selected_score" in metadata.columns

        assert (metadata["selected_method"] == "quantiles").all()
        assert metadata["selected_score"].isna().all()

    def test_no_metadata_for_unknown_column(self):
        """Test that get_selection_metadata returns None for unknown column."""
        engine = BinningEngine()
        assert engine.get_selection_metadata("nonexistent") is None

    def test_auto_select_with_exceptions_stores_metadata(self):
        """Test metadata storage when exceptions are used in auto mode."""
        engine = BinningEngine(strategy="auto", k=5)

        series = pd.Series(range(1, 21), name="exception_test")
        engine.bin_series(series, exceptions=["fisher_jenks", "maximum_breaks"])

        meta = engine.get_selection_metadata("exception_test")
        assert meta is not None
        assert meta["selection_type"] == "auto"
        # The selected method should not be one of the excluded methods
        assert meta["selected_method"] not in ["fisher_jenks", "maximum_breaks"]


@pytest.mark.integration
class TestBinningIntegration:
    """Integration tests for binning with realistic data."""

    def test_cria_indicators_binning(self):
        """Test binning realistic CRIA indicator data."""
        engine = BinningEngine(strategy="auto", k=5)

        # Simulate CRIA indicators
        np.random.seed(42)
        df = pd.DataFrame({
            "Poverty": np.random.beta(2, 5, 100) * 100,        # Right-skewed
            "GINI": np.random.uniform(0.3, 0.6, 100) * 100,    # Uniform
            "Unemployment": np.random.beta(2, 8, 100) * 100,   # Right-skewed
            "Median Income": np.random.normal(50000, 15000, 100)  # Normal
        })

        exceptions = {
            "Poverty": ["jenks_caspall"],  # Might be slow
        }

        result = engine.bin_dataframe(df, k=5, exceptions_dict=exceptions)

        # All indicators should be binned
        for col in df.columns:
            assert f"{col}_bins" in result.columns

        # Bins should be 1-5
        for col in df.columns:
            bin_col = f"{col}_bins"
            assert result[bin_col].min() >= 1
            assert result[bin_col].max() <= 5

    def test_geography_specific_bins(self):
        """Test that different geographies use different bin counts."""
        # County: 5 bins
        engine_county = BinningEngine(k=5)

        # Tract: 7 bins
        engine_tract = BinningEngine(k=7)

        series = pd.Series(range(1, 101), name="test")

        bins_county = engine_county.bin_series(series)
        bins_tract = engine_tract.bin_series(series)

        # County should have 5 bins
        assert bins_county.max() == 5

        # Tract should have 7 bins
        assert bins_tract.max() == 7


class TestManualBins:
    """Tests for manual bin boundaries restored from deprecated code."""

    def test_cria_p_uses_manual_bins_bell_curve(self):
        """cria_p should use manual bins [0.1, 0.3, 0.7, 0.9] producing a bell curve."""
        engine = BinningEngine(strategy="auto", k=5)
        # Uniform percentile data (0 to 1)
        np.random.seed(42)
        series = pd.Series(np.random.uniform(0, 1, 3000), name="cria_p")
        binned = engine.bin_series(series)

        counts = binned.value_counts().sort_index()
        # Bell curve: bin 3 (0.3-0.7) should be largest (~40%)
        assert counts[3] > counts[1]
        assert counts[3] > counts[5]
        # Edge bins (~10% each) should be smallest
        assert counts[1] < counts[2]
        assert counts[5] < counts[4]

    def test_cria_p_metadata_is_manual(self):
        """cria_p should record selection_type='manual'."""
        engine = BinningEngine(strategy="auto", k=5)
        series = pd.Series(np.random.uniform(0, 1, 100), name="cria_p")
        engine.bin_series(series)

        meta = engine.get_selection_metadata("cria_p")
        assert meta is not None
        assert meta["selected_method"] == "manual"
        assert meta["selection_type"] == "manual"

    def test_pop_change_uses_manual_bins_ascending(self):
        """pop change should use manual bins with ascending labels (most change = bin 5)."""
        engine = BinningEngine(strategy="auto", k=5)
        # Pop change data centered around 0.5 (typical range 0 to ~3)
        np.random.seed(42)
        series = pd.Series(np.random.exponential(0.5, 3000), name="pop change")
        binned = engine.bin_series(series)

        # Ascending labels: highest values get bin 5, lowest get bin 1
        # A value > 1.5 should be bin 5 (most change)
        high_val_idx = series[series > 1.5].index
        if len(high_val_idx) > 0:
            assert (binned.loc[high_val_idx] == 5).all()

        # A value < 0.1 should be bin 1 (least change)
        low_val_idx = series[series < 0.1].index
        if len(low_val_idx) > 0:
            assert (binned.loc[low_val_idx] == 1).all()

    def test_agg_uses_manual_bins_reversed(self):
        """agg should use manual bins [-0.75, -0.25, 0.25, 0.75] with reversed labels."""
        engine = BinningEngine(strategy="auto", k=5)
        np.random.seed(42)
        series = pd.Series(np.random.normal(0, 0.5, 1000), name="agg")
        binned = engine.bin_series(series)

        # Reversed: high agg values → bin 1, low agg values → bin 5
        high_val_idx = series[series > 0.75].index
        if len(high_val_idx) > 0:
            assert (binned.loc[high_val_idx] == 1).all()

        low_val_idx = series[series < -0.75].index
        if len(low_val_idx) > 0:
            assert (binned.loc[low_val_idx] == 5).all()

    def test_median_income_uses_manual_bins(self):
        """Median Income should use manual bins [25k, 50k, 75k, 100k], not reversed."""
        engine = BinningEngine(strategy="auto", k=5)
        np.random.seed(42)
        series = pd.Series(
            np.random.normal(55000, 20000, 1000), name="Median Income"
        )
        binned = engine.bin_series(series)

        # Not reversed: low income → bin 1, high income → bin 5
        low_val_idx = series[series < 25000].index
        if len(low_val_idx) > 0:
            assert (binned.loc[low_val_idx] == 1).all()

        high_val_idx = series[series > 100000].index
        if len(high_val_idx) > 0:
            assert (binned.loc[high_val_idx] == 5).all()

    def test_cri_uses_manual_bins_not_reversed(self):
        """cri should use manual bins [0.1, 0.3, 0.7, 0.9], not reversed."""
        engine = BinningEngine(strategy="auto", k=5)
        series = pd.Series(np.random.uniform(0, 1, 1000), name="cri")
        binned = engine.bin_series(series)

        # Not reversed: low values → bin 1
        low_val_idx = series[series < 0.1].index
        if len(low_val_idx) > 0:
            assert (binned.loc[low_val_idx] == 1).all()

    def test_pop_p_uses_manual_bins_ascending(self):
        """pop_p should use manual bins with ascending labels (most change = bin 5)."""
        engine = BinningEngine(strategy="auto", k=5)
        series = pd.Series(np.random.uniform(0, 1, 1000), name="pop_p")
        binned = engine.bin_series(series)

        # Ascending: high percentile → bin 5
        high_val_idx = series[series > 0.9].index
        if len(high_val_idx) > 0:
            assert (binned.loc[high_val_idx] == 5).all()

        meta = engine.get_selection_metadata("pop_p")
        assert meta["selected_method"] == "manual"

    def test_non_manual_column_uses_auto_select(self):
        """Columns not in MANUAL_BINS should use auto-select as before."""
        engine = BinningEngine(strategy="auto", k=5)
        series = pd.Series(np.random.rand(100), name="Poverty")
        engine.bin_series(series)

        meta = engine.get_selection_metadata("Poverty")
        assert meta is not None
        assert meta["selection_type"] == "auto"
        assert meta["selected_method"] != "manual"

    def test_manual_bins_7_bins_tract(self):
        """Manual bins should work with k=7 (tract geography)."""
        engine = BinningEngine(strategy="auto", k=7)
        series = pd.Series(np.random.uniform(0, 1, 3000), name="cria_p")
        binned = engine.bin_series(series)

        # Should use 7-bin boundaries [0.05, 0.15, 0.3, 0.7, 0.85, 0.95]
        assert binned.min() == 1
        assert binned.max() == 7

        meta = engine.get_selection_metadata("cria_p")
        assert meta["selected_method"] == "manual"

    def test_manual_bins_preserves_nan(self):
        """Manual bins should preserve NaN values in the output."""
        engine = BinningEngine(strategy="auto", k=5)
        data = list(np.random.uniform(0, 1, 50)) + [np.nan, np.nan, np.nan]
        series = pd.Series(data, name="cria_p")
        binned = engine.bin_series(series)

        assert binned.isna().sum() == 3
        assert binned.dropna().min() >= 1
        assert binned.dropna().max() <= 5

    def test_manual_bins_unconfigured_k_falls_through(self):
        """If k is not in MANUAL_BINS config, fall through to auto-select."""
        engine = BinningEngine(strategy="auto", k=3)
        series = pd.Series(np.random.uniform(0, 1, 100), name="cria_p")
        engine.bin_series(series)

        # k=3 not in MANUAL_BINS["cria_p"], should use auto
        meta = engine.get_selection_metadata("cria_p")
        assert meta["selection_type"] == "auto"

    @pytest.mark.parametrize("col_name", list(MANUAL_BINS.keys()))
    def test_all_manual_columns_recognized(self, col_name):
        """Every MANUAL_BINS entry should be recognized and applied."""
        engine = BinningEngine(strategy="auto", k=5)

        # Generate appropriate data for each column
        if col_name == "Median Income":
            data = np.random.normal(55000, 20000, 200)
        elif col_name == "agg":
            data = np.random.normal(0, 0.5, 200)
        else:
            data = np.random.uniform(0, 1, 200)

        series = pd.Series(data, name=col_name)
        engine.bin_series(series)

        meta = engine.get_selection_metadata(col_name)
        assert meta is not None
        assert meta["selected_method"] == "manual"
        assert meta["selection_type"] == "manual"

    def test_pop_change_7bin_ascending(self):
        """pop change 7-bin (tract) should use ascending labels: least change = 1, most = 7."""
        engine = BinningEngine(strategy="auto", k=7)
        np.random.seed(42)
        series = pd.Series(np.random.exponential(0.5, 3000), name="pop change")
        binned = engine.bin_series(series)

        # 7-bin boundaries: [0.05, 0.15, 0.3, 0.9, 1.3, 2.25]
        assert binned.min() == 1
        assert binned.max() == 7

        # Ascending: values > 2.25 should be bin 7 (most change)
        high_val_idx = series[series > 2.25].index
        if len(high_val_idx) > 0:
            assert (binned.loc[high_val_idx] == 7).all()

        # Values < 0.05 should be bin 1 (least change)
        low_val_idx = series[series < 0.05].index
        if len(low_val_idx) > 0:
            assert (binned.loc[low_val_idx] == 1).all()

        meta = engine.get_selection_metadata("pop change")
        assert meta["selected_method"] == "manual"

    def test_pop_p_7bin_ascending(self):
        """pop_p 7-bin (tract) should use ascending labels: low percentile = 1, high = 7."""
        engine = BinningEngine(strategy="auto", k=7)
        np.random.seed(42)
        series = pd.Series(np.random.uniform(0, 1, 3000), name="pop_p")
        binned = engine.bin_series(series)

        # 7-bin boundaries: [0.05, 0.15, 0.3, 0.7, 0.85, 0.95]
        assert binned.min() == 1
        assert binned.max() == 7

        # Ascending: values > 0.95 should be bin 7
        high_val_idx = series[series > 0.95].index
        if len(high_val_idx) > 0:
            assert (binned.loc[high_val_idx] == 7).all()

        # Values < 0.05 should be bin 1
        low_val_idx = series[series < 0.05].index
        if len(low_val_idx) > 0:
            assert (binned.loc[low_val_idx] == 1).all()

        meta = engine.get_selection_metadata("pop_p")
        assert meta["selected_method"] == "manual"

    @pytest.mark.parametrize("col_name,k", [
        ("pop change", 5),
        ("pop change", 7),
        ("pop_p", 5),
        ("pop_p", 7),
    ])
    def test_pop_columns_ascending_all_k(self, col_name, k):
        """Pop change and pop_p should use ascending labels for both k=5 and k=7.

        Ascending means: small values -> low bin number, large values -> high bin number.
        This verifies the fix from reverse=True to reverse=False.
        """
        engine = BinningEngine(strategy="auto", k=k)
        np.random.seed(42)

        if col_name == "pop change":
            series = pd.Series(np.random.exponential(0.5, 3000), name=col_name)
        else:
            series = pd.Series(np.random.uniform(0, 1, 3000), name=col_name)

        binned = engine.bin_series(series)

        assert binned.min() == 1
        assert binned.max() == k

        # Core ascending property: median bin of upper quartile > median bin of lower quartile
        lower_q = series.quantile(0.25)
        upper_q = series.quantile(0.75)
        lower_bins = binned[series < lower_q].median()
        upper_bins = binned[series > upper_q].median()
        assert upper_bins > lower_bins, (
            f"{col_name} k={k}: upper quartile bins ({upper_bins}) should exceed "
            f"lower quartile bins ({lower_bins}) for ascending order"
        )

        meta = engine.get_selection_metadata(col_name)
        assert meta["selected_method"] == "manual"
        assert meta["selection_type"] == "manual"
