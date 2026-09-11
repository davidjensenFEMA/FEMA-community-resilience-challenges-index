"""
Tests for tribal output fix: skip_aggregation behavior, GEO_ID filtering,
and bin_labels structure.

These tests verify the changes from the tribal output CONOP:
1. AggregateIndicator.create_aggregate(skip_aggregation=True) returns
   binning-only results (indicators, bin_labels, bin_meta).
2. Tribal GEO_IDs (2500000US prefix) are correctly isolated from county
   GEO_IDs (0500000US prefix) via index filtering.
3. bin_labels from skip_aggregation=True have the expected structure
   (indicator columns + _bins columns with values 1-k).
4. Regression guards ensuring county/tract still produce full output.
"""

import numpy as np
import pandas as pd
import pytest

from src.core.aggregator import AggregateIndicator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Indicator names drawn from config/indicators.yaml to be realistic
INDICATOR_NAMES = [
    "Mobile Homes", "Owner Occupied", "Education", "No Vehicle",
    "Age", "Disability", "Limited English", "Single Parent",
    "Low Access to Communications", "Poverty", "GINI",
    "Unemployment", "Unemployed Women", "Median Income",
    "Uninsured Population", "Medical",
]

# ACS-only subset (what tribal uses after dropping non-ACS columns)
ACS_INDICATOR_NAMES = [
    "Mobile Homes", "Owner Occupied", "Education", "No Vehicle",
    "Age", "Disability", "Limited English", "Single Parent",
    "Low Access to Communications", "Poverty", "GINI",
    "Unemployment", "Unemployed Women", "Median Income",
    "Uninsured Population", "Medical",
]

# Non-ACS indicators that tribal drops
NON_ACS_INDICATOR_NAMES = [
    "Civil Org", "Hospitals", "Inactive Voter", "Religion",
    "Population Change",
]


@pytest.fixture
def tribal_reference():
    """Reference DataFrame for ACS-only tribal indicators.

    Tribal drops non-ACS columns before aggregation, so the reference
    passed to create_aggregate only contains ACS indicators.
    """
    return pd.DataFrame({
        "Indicator": ACS_INDICATOR_NAMES,
        "Source": ["ACS"] * len(ACS_INDICATOR_NAMES),
        "Function": ["divide"] * len(ACS_INDICATOR_NAMES),
        "Units": [
            "fraction", "fraction", "fraction", "fraction",
            "fraction", "fraction", "fraction", "fraction",
            "fraction", "fraction", "index",
            "fraction", "fraction", "dollars",
            "fraction", "ratio",
        ],
        "Augment": [
            "reverse", "none", "reverse", "reverse",
            "reverse", "reverse", "reverse", "reverse",
            "reverse", "reverse", "reverse",
            "reverse", "reverse", "none",
            "reverse", "none",
        ],
    })


@pytest.fixture
def county_reference():
    """Reference DataFrame for full county indicators (ACS + non-ACS)."""
    all_indicators = ACS_INDICATOR_NAMES + NON_ACS_INDICATOR_NAMES
    sources = (
        ["ACS"] * len(ACS_INDICATOR_NAMES)
        + ["CBP", "CBP", "EAVS", "ARDA", "POP"]
    )
    return pd.DataFrame({
        "Indicator": all_indicators,
        "Source": sources,
        "Function": ["divide"] * len(all_indicators),
        "Units": (
            [
                "fraction", "fraction", "fraction", "fraction",
                "fraction", "fraction", "fraction", "fraction",
                "fraction", "fraction", "index",
                "fraction", "fraction", "dollars",
                "fraction", "ratio",
            ]
            + ["rate", "rate", "fraction", "fraction", "ratio"]
        ),
        "Augment": (
            [
                "reverse", "none", "reverse", "reverse",
                "reverse", "reverse", "reverse", "reverse",
                "reverse", "reverse", "reverse",
                "reverse", "reverse", "none",
                "reverse", "none",
            ]
            + ["none", "none", "reverse", "reverse", "none"]
        ),
    })


def _make_tribal_geo_ids(n):
    """Generate n tribal GEO_IDs with the 2500000US prefix."""
    return [f"2500000US{i:04d}" for i in range(n)]


def _make_county_geo_ids(n):
    """Generate n county GEO_IDs with the 0500000US prefix."""
    return [f"0500000US{i:05d}" for i in range(n)]


def _make_tract_geo_ids(n):
    """Generate n tract GEO_IDs with the 1400000US prefix."""
    return [f"1400000US{i:011d}" for i in range(n)]


@pytest.fixture
def tribal_indicators():
    """Synthetic indicator DataFrame for 80 tribal areas (ACS-only).

    Contains some NaN values to test imputation behavior.
    """
    np.random.seed(42)
    n = 80
    geo_ids = _make_tribal_geo_ids(n)

    data = {}
    for col in ACS_INDICATOR_NAMES:
        values = np.random.beta(2, 5, n)
        # Inject NaN at known positions so we can verify imputation
        nan_positions = list(range(0, n, 10))  # indices 0, 10, 20, ...
        for pos in nan_positions:
            values[pos] = np.nan
        data[col] = values

    df = pd.DataFrame(data, index=geo_ids)
    df.index.name = "GEO_ID"
    return df


@pytest.fixture
def county_indicators():
    """Synthetic indicator DataFrame for 100 counties (ACS + non-ACS)."""
    np.random.seed(123)
    n = 100
    geo_ids = _make_county_geo_ids(n)

    all_indicators = ACS_INDICATOR_NAMES + NON_ACS_INDICATOR_NAMES
    data = {}
    for col in all_indicators:
        if col == "Population Change":
            data[col] = np.random.normal(1.0, 0.3, n)
        elif col in ("Median Income",):
            data[col] = np.random.normal(50000, 15000, n)
        elif col in ("Civil Org", "Hospitals"):
            data[col] = np.random.exponential(2, n)
        elif col in ("GINI",):
            data[col] = np.random.uniform(0.3, 0.6, n)
        else:
            data[col] = np.random.beta(2, 5, n)
    # Inject some NaN
    for col in all_indicators:
        data[col][0] = np.nan

    df = pd.DataFrame(data, index=geo_ids)
    df.index.name = "GEO_ID"
    return df


@pytest.fixture
def mixed_geo_ids_df():
    """DataFrame with mixed county and tribal GEO_IDs in the index.

    Simulates the contamination pattern from DataPuller outer merge where
    both 0500000US (county) and 2500000US (tribal) rows appear.
    """
    tribal_ids = _make_tribal_geo_ids(20)
    county_ids = _make_county_geo_ids(10)
    all_ids = tribal_ids + county_ids

    np.random.seed(99)
    data = {col: np.random.rand(30) for col in ACS_INDICATOR_NAMES[:5]}
    df = pd.DataFrame(data, index=all_ids)
    df.index.name = "GEO_ID"
    return df


# ======================================================================
# Test Group 1: skip_aggregation behavior
# ======================================================================

class TestSkipAggregationBehavior:
    """Tests for create_aggregate(skip_aggregation=True) vs False."""

    SKIP_EXPECTED_KEYS = {"indicators", "bin_labels", "bin_meta"}

    FULL_EXPECTED_KEYS = {
        "indicators", "pos", "scores", "scores_percentiles",
        "lowest_ind", "agg", "bin_labels", "bin_meta",
        "agg_labels", "agg_meta", "corr", "p", "zero", "n",
    }

    SKIP_FORBIDDEN_KEYS = {
        "pos", "scores", "scores_percentiles",
        "agg", "agg_labels", "agg_meta",
    }

    def test_skip_aggregation_returns_only_binning_keys(
        self, tribal_indicators, tribal_reference
    ):
        """skip_aggregation=True must return ONLY indicators, bin_labels, bin_meta."""
        agg = AggregateIndicator(geography="tribal", bins=5)
        results = agg.create_aggregate(
            indicators=tribal_indicators,
            reference=tribal_reference,
            skip_aggregation=True,
        )
        assert set(results.keys()) == self.SKIP_EXPECTED_KEYS

    def test_skip_aggregation_excludes_aggregation_keys(
        self, tribal_indicators, tribal_reference
    ):
        """skip_aggregation=True must NOT contain pos, scores, agg, etc."""
        agg = AggregateIndicator(geography="tribal", bins=5)
        results = agg.create_aggregate(
            indicators=tribal_indicators,
            reference=tribal_reference,
            skip_aggregation=True,
        )
        for forbidden_key in self.SKIP_FORBIDDEN_KEYS:
            assert forbidden_key not in results, (
                f"Key '{forbidden_key}' must not be present when "
                f"skip_aggregation=True, but it was found in results"
            )

    def test_full_aggregation_returns_all_nine_keys(
        self, county_indicators, county_reference
    ):
        """Regression: skip_aggregation=False must return all 9 standard keys."""
        agg = AggregateIndicator(geography="county", bins=5)
        results = agg.create_aggregate(
            indicators=county_indicators,
            reference=county_reference,
            skip_aggregation=False,
        )
        assert set(results.keys()) == self.FULL_EXPECTED_KEYS

    def test_skip_aggregation_uses_impute_false(
        self, tribal_reference
    ):
        """When skip_aggregation=True, NaN must NOT be mean-imputed.

        We inject a known NaN at index 0 for every column.  With impute=False,
        NaN must survive into the cleaned output.
        """
        np.random.seed(0)
        n = 30
        geo_ids = _make_tribal_geo_ids(n)
        data = {col: np.random.rand(n) for col in ACS_INDICATOR_NAMES}
        # Set row 0 to NaN for all columns
        for col in ACS_INDICATOR_NAMES:
            data[col][0] = np.nan

        indicators = pd.DataFrame(data, index=geo_ids)
        indicators.index.name = "GEO_ID"

        agg = AggregateIndicator(geography="tribal", bins=5)
        results = agg.create_aggregate(
            indicators=indicators,
            reference=tribal_reference,
            skip_aggregation=True,
        )

        cleaned = results["indicators"]
        # Row 0 should still be NaN in EVERY column (not imputed)
        row_0 = cleaned.iloc[0]
        assert row_0.isna().all(), (
            f"Expected all NaN in row 0 with impute=False, "
            f"but got non-NaN in columns: "
            f"{list(row_0.dropna().index)}"
        )

    def test_full_aggregation_display_preserves_nan(
        self, county_reference
    ):
        """When skip_aggregation=False, results["indicators"] is the display
        copy (impute=False) and must PRESERVE NaN.  The CRCI pipeline
        (z-scores, aggregate) uses the imputed copy internally.

        We inject a known NaN at row 0.  The display tab must still have
        NaN at row 0, but the z-scores must NOT.
        """
        np.random.seed(1)
        n = 50
        geo_ids = _make_county_geo_ids(n)

        all_indicators = ACS_INDICATOR_NAMES + NON_ACS_INDICATOR_NAMES
        data = {}
        for col in all_indicators:
            if col == "Population Change":
                data[col] = np.random.normal(1.0, 0.3, n)
            else:
                data[col] = np.random.rand(n)
            # Set row 0 to NaN
            data[col][0] = np.nan

        indicators = pd.DataFrame(data, index=geo_ids)
        indicators.index.name = "GEO_ID"

        agg = AggregateIndicator(geography="county", bins=5)
        results = agg.create_aggregate(
            indicators=indicators,
            reference=county_reference,
            skip_aggregation=False,
        )

        display = results["indicators"]
        # Row 0 should STILL have NaN (display copy uses impute=False)
        row_0 = display.iloc[0]
        assert row_0.isna().all(), (
            f"Expected all NaN in row 0 on display tab (impute=False), "
            f"but got non-NaN in columns: "
            f"{list(row_0.dropna().index)}"
        )

        # But z-scores should NOT have NaN (pipeline uses imputed copy)
        scores = results["scores"]
        scores_row_0 = scores.iloc[0]
        assert not scores_row_0.isna().any(), (
            f"Expected no NaN in row 0 of scores (imputed pipeline), "
            f"but got NaN in columns: "
            f"{list(scores_row_0[scores_row_0.isna()].index)}"
        )

    def test_skip_aggregation_impute_false_preserves_interior_nan(
        self, tribal_reference
    ):
        """Verify scattered NaN throughout the dataframe survive with impute=False.

        This tests more than just row 0 -- ensures the impute flag propagates
        through _clean_indicators to clean_series for every column.
        """
        np.random.seed(77)
        n = 40
        geo_ids = _make_tribal_geo_ids(n)
        data = {}
        nan_count_per_col = {}
        for col in ACS_INDICATOR_NAMES:
            values = np.random.rand(n)
            # Inject NaN at 25% of positions (different for each column)
            nan_mask = np.random.rand(n) < 0.25
            values[nan_mask] = np.nan
            nan_count_per_col[col] = int(nan_mask.sum())
            data[col] = values

        indicators = pd.DataFrame(data, index=geo_ids)
        indicators.index.name = "GEO_ID"

        agg = AggregateIndicator(geography="tribal", bins=5)
        results = agg.create_aggregate(
            indicators=indicators,
            reference=tribal_reference,
            skip_aggregation=True,
        )

        cleaned = results["indicators"]
        for col in ACS_INDICATOR_NAMES:
            expected_nan = nan_count_per_col[col]
            actual_nan = int(cleaned[col].isna().sum())
            assert actual_nan == expected_nan, (
                f"Column '{col}': expected {expected_nan} NaN but got "
                f"{actual_nan} (impute=False should preserve all NaN)"
            )


# ======================================================================
# Test Group 2: Tribal GEO_ID filtering (D10)
# ======================================================================

class TestTribalGeoIdFiltering:
    """Tests for D10: filtering tribal GEO_IDs from mixed DataFrames."""

    def test_filter_keeps_only_tribal_prefix(self, mixed_geo_ids_df):
        """Filtering with startswith('2500000US') keeps only tribal rows."""
        mask = mixed_geo_ids_df.index.str.startswith("2500000US")
        filtered = mixed_geo_ids_df.loc[mask]

        assert len(filtered) == 20
        assert all(
            geo_id.startswith("2500000US") for geo_id in filtered.index
        )

    def test_filter_removes_county_geo_ids(self, mixed_geo_ids_df):
        """Filtering removes all 0500000US (county) rows."""
        mask = mixed_geo_ids_df.index.str.startswith("2500000US")
        filtered = mixed_geo_ids_df.loc[mask]

        county_remaining = [
            gid for gid in filtered.index
            if gid.startswith("0500000US")
        ]
        assert county_remaining == [], (
            f"County GEO_IDs should be removed but found: {county_remaining}"
        )

    def test_filter_preserves_all_tribal_geo_ids(self, mixed_geo_ids_df):
        """Filtering must not lose any tribal GEO_IDs."""
        all_tribal = [
            gid for gid in mixed_geo_ids_df.index
            if gid.startswith("2500000US")
        ]
        mask = mixed_geo_ids_df.index.str.startswith("2500000US")
        filtered = mixed_geo_ids_df.loc[mask]

        assert sorted(filtered.index.tolist()) == sorted(all_tribal)

    def test_consistent_filtering_across_dataframes(self):
        """source_data, indicators, and geo_reference filter consistently.

        When the same mask logic is applied to all three DataFrames, the
        resulting indices must be identical -- as done in run_full_pipeline.py D10.
        """
        tribal_ids = _make_tribal_geo_ids(15)
        county_ids = _make_county_geo_ids(5)
        all_ids = tribal_ids + county_ids

        np.random.seed(88)
        indicators = pd.DataFrame(
            {"Poverty": np.random.rand(20), "GINI": np.random.rand(20)},
            index=all_ids,
        )
        source_data = pd.DataFrame(
            {"S0101_C01_001E": np.random.randint(1, 10000, 20)},
            index=all_ids,
        )
        geo_reference = pd.DataFrame(
            {"state_name": ["State"] * 20, "state": [1] * 20},
            index=all_ids,
        )

        # Apply the same filter as run_full_pipeline.py D10
        tribal_mask_ind = indicators.index.str.startswith("2500000US")
        tribal_mask_src = source_data.index.str.startswith("2500000US")
        tribal_mask_geo = geo_reference.index.str.startswith("2500000US")

        filtered_ind = indicators.loc[tribal_mask_ind]
        filtered_src = source_data.loc[tribal_mask_src]
        filtered_geo = geo_reference.loc[tribal_mask_geo]

        # All three must have the same index after filtering
        pd.testing.assert_index_equal(filtered_ind.index, filtered_src.index)
        pd.testing.assert_index_equal(filtered_ind.index, filtered_geo.index)
        assert len(filtered_ind) == 15

    def test_filter_on_empty_tribal_subset(self):
        """If no tribal GEO_IDs exist, the filter returns empty DataFrame."""
        county_ids = _make_county_geo_ids(10)
        df = pd.DataFrame(
            {"Poverty": np.random.rand(10)},
            index=county_ids,
        )
        mask = df.index.str.startswith("2500000US")
        filtered = df.loc[mask]
        assert len(filtered) == 0
        assert list(filtered.columns) == ["Poverty"]


# ======================================================================
# Test Group 3: Tribal bin_labels structure
# ======================================================================

class TestTribalBinLabelsStructure:
    """Tests for bin_labels produced by skip_aggregation=True."""

    def test_bin_labels_has_indicator_and_bins_columns(
        self, tribal_indicators, tribal_reference
    ):
        """bin_labels must contain both original indicator columns and _bins columns."""
        agg = AggregateIndicator(geography="tribal", bins=5)
        results = agg.create_aggregate(
            indicators=tribal_indicators,
            reference=tribal_reference,
            skip_aggregation=True,
        )

        bin_labels = results["bin_labels"]
        for col in ACS_INDICATOR_NAMES:
            assert col in bin_labels.columns, (
                f"Indicator column '{col}' missing from bin_labels"
            )
            bins_col = f"{col}_bins"
            assert bins_col in bin_labels.columns, (
                f"Bins column '{bins_col}' missing from bin_labels"
            )

    def test_bins_values_range_1_to_5(
        self, tribal_indicators, tribal_reference
    ):
        """_bins columns must contain only values in [1, 5] (or NaN)."""
        agg = AggregateIndicator(geography="tribal", bins=5)
        results = agg.create_aggregate(
            indicators=tribal_indicators,
            reference=tribal_reference,
            skip_aggregation=True,
        )

        bin_labels = results["bin_labels"]
        for col in ACS_INDICATOR_NAMES:
            bins_col = f"{col}_bins"
            non_null = bin_labels[bins_col].dropna()
            if len(non_null) == 0:
                continue
            assert non_null.min() >= 1, (
                f"{bins_col} has min value {non_null.min()} < 1"
            )
            assert non_null.max() <= 5, (
                f"{bins_col} has max value {non_null.max()} > 5"
            )

    def test_bins_values_are_integers(
        self, tribal_indicators, tribal_reference
    ):
        """_bins column values must be integer-valued (whole numbers)."""
        agg = AggregateIndicator(geography="tribal", bins=5)
        results = agg.create_aggregate(
            indicators=tribal_indicators,
            reference=tribal_reference,
            skip_aggregation=True,
        )

        bin_labels = results["bin_labels"]
        for col in ACS_INDICATOR_NAMES:
            bins_col = f"{col}_bins"
            non_null = bin_labels[bins_col].dropna()
            if len(non_null) == 0:
                continue
            # Check all values are whole numbers
            assert (non_null == non_null.astype(int).astype(float)).all(), (
                f"{bins_col} contains non-integer values"
            )

    def test_bin_meta_has_expected_columns(
        self, tribal_indicators, tribal_reference
    ):
        """bin_meta must have bin, count, min, max, mean, median,
        selected_method, and indicator columns."""
        agg = AggregateIndicator(geography="tribal", bins=5)
        results = agg.create_aggregate(
            indicators=tribal_indicators,
            reference=tribal_reference,
            skip_aggregation=True,
        )

        bin_meta = results["bin_meta"]
        expected_columns = {
            "bin", "count", "min", "max", "mean", "median",
            "selected_method", "indicator",
        }
        actual_columns = set(bin_meta.columns)
        for col in expected_columns:
            assert col in actual_columns, (
                f"Expected column '{col}' in bin_meta but only found: "
                f"{sorted(actual_columns)}"
            )

    def test_bin_meta_covers_all_indicators(
        self, tribal_indicators, tribal_reference
    ):
        """bin_meta must have rows for every indicator column."""
        agg = AggregateIndicator(geography="tribal", bins=5)
        results = agg.create_aggregate(
            indicators=tribal_indicators,
            reference=tribal_reference,
            skip_aggregation=True,
        )

        bin_meta = results["bin_meta"]
        indicators_in_meta = set(bin_meta["indicator"].unique())
        for col in ACS_INDICATOR_NAMES:
            assert col in indicators_in_meta, (
                f"Indicator '{col}' missing from bin_meta"
            )

    def test_bin_meta_counts_sum_to_non_nan_rows(
        self, tribal_indicators, tribal_reference
    ):
        """For each indicator, the sum of bin counts must equal the number
        of non-NaN values in that indicator column.

        This is a known-answer check: the binning engine only bins non-NaN
        rows, so the metadata must account for exactly that many.
        """
        agg = AggregateIndicator(geography="tribal", bins=5)
        results = agg.create_aggregate(
            indicators=tribal_indicators,
            reference=tribal_reference,
            skip_aggregation=True,
        )

        bin_meta = results["bin_meta"]
        # The binning operates on df_scale (rescaled clean indicators).
        # With impute=False, NaN count = input NaN count.
        for col in ACS_INDICATOR_NAMES:
            indicator_meta = bin_meta[bin_meta["indicator"] == col]
            total_binned = indicator_meta["count"].sum()
            n_non_nan = int(tribal_indicators[col].notna().sum())
            assert total_binned == n_non_nan, (
                f"Indicator '{col}': bin counts sum to {total_binned} "
                f"but expected {n_non_nan} non-NaN values"
            )


# ======================================================================
# Test Group 4: Regression guards
# ======================================================================

class TestRegressionGuards:
    """Regression guards to prevent future regressions in output structure."""

    def test_county_returns_agg_keys(
        self, county_indicators, county_reference
    ):
        """County create_aggregate must return 'agg', 'agg_labels', 'agg_meta'."""
        agg = AggregateIndicator(geography="county", bins=5)
        results = agg.create_aggregate(
            indicators=county_indicators,
            reference=county_reference,
            skip_aggregation=False,
        )

        for key in ("agg", "agg_labels", "agg_meta"):
            assert key in results, (
                f"Key '{key}' missing from county results"
            )
            assert isinstance(results[key], pd.DataFrame), (
                f"results['{key}'] should be a DataFrame"
            )
            assert not results[key].empty, (
                f"results['{key}'] should not be empty for county"
            )

    def test_county_agg_has_cri_and_percentile(
        self, county_indicators, county_reference
    ):
        """County agg DataFrame must contain 'cri' and 'cria_p' columns."""
        agg = AggregateIndicator(geography="county", bins=5)
        results = agg.create_aggregate(
            indicators=county_indicators,
            reference=county_reference,
        )

        assert "cri" in results["agg"].columns
        assert "cria_p" in results["agg"].columns

    @pytest.mark.parametrize(
        "geography,prefix",
        [
            ("county", "0500000US"),
            ("tract", "1400000US"),
            ("tribal", "2500000US"),
        ],
        ids=["county", "tract", "tribal"],
    )
    def test_geo_id_prefix_consistency(self, geography, prefix):
        """GEO_IDs for each geography must consistently use the expected prefix.

        This parametrized test ensures the prefix convention is maintained
        across county, tract, and tribal geographies.
        """
        n = 30
        if geography == "county":
            geo_ids = _make_county_geo_ids(n)
        elif geography == "tract":
            geo_ids = _make_tract_geo_ids(n)
        elif geography == "tribal":
            geo_ids = _make_tribal_geo_ids(n)
        else:
            pytest.fail(f"Unknown geography: {geography}")

        for geo_id in geo_ids:
            assert geo_id.startswith(prefix), (
                f"GEO_ID '{geo_id}' does not start with expected "
                f"prefix '{prefix}' for geography '{geography}'"
            )

        # Filtering with the prefix must keep all rows
        df = pd.DataFrame({"val": range(n)}, index=geo_ids)
        mask = df.index.str.startswith(prefix)
        assert mask.all(), (
            f"Not all GEO_IDs matched prefix '{prefix}' for {geography}"
        )

    def test_skip_aggregation_default_is_false(
        self, county_indicators, county_reference
    ):
        """Default skip_aggregation must be False (full pipeline).

        This ensures a caller who does not pass skip_aggregation gets the
        full 9-key output, not the reduced 3-key tribal output.
        """
        agg = AggregateIndicator(geography="county", bins=5)
        results = agg.create_aggregate(
            indicators=county_indicators,
            reference=county_reference,
        )
        # Must contain aggregation keys
        assert "agg" in results
        assert "pos" in results
        assert "scores" in results

    def test_skip_aggregation_true_indicators_row_count_matches_input(
        self, tribal_indicators, tribal_reference
    ):
        """The 'indicators' DataFrame in skip_aggregation results must have
        the same row count as the input, proving no rows were dropped."""
        agg = AggregateIndicator(geography="tribal", bins=5)
        results = agg.create_aggregate(
            indicators=tribal_indicators,
            reference=tribal_reference,
            skip_aggregation=True,
        )

        assert len(results["indicators"]) == len(tribal_indicators)

    def test_skip_aggregation_true_indicators_column_count_matches_input(
        self, tribal_indicators, tribal_reference
    ):
        """The 'indicators' DataFrame must have the same columns as input."""
        agg = AggregateIndicator(geography="tribal", bins=5)
        results = agg.create_aggregate(
            indicators=tribal_indicators,
            reference=tribal_reference,
            skip_aggregation=True,
        )

        pd.testing.assert_index_equal(
            results["indicators"].columns,
            tribal_indicators.columns,
        )

    def test_full_aggregation_bin_labels_not_empty(
        self, county_indicators, county_reference
    ):
        """Regression: county bin_labels must not be empty."""
        agg = AggregateIndicator(geography="county", bins=5)
        results = agg.create_aggregate(
            indicators=county_indicators,
            reference=county_reference,
        )
        assert not results["bin_labels"].empty

    def test_full_aggregation_agg_labels_not_empty(
        self, county_indicators, county_reference
    ):
        """Regression: county agg_labels must not be empty."""
        agg = AggregateIndicator(geography="county", bins=5)
        results = agg.create_aggregate(
            indicators=county_indicators,
            reference=county_reference,
        )
        assert not results["agg_labels"].empty

    def test_pipeline_guard_clause_for_missing_agg(
        self, tribal_indicators, tribal_reference
    ):
        """Verify that results.get('agg') returns None for tribal.

        The pipeline uses `results.get('agg')` rather than `results['agg']`
        to avoid KeyError when skip_aggregation=True.  This test proves
        the guard clause is necessary.
        """
        agg = AggregateIndicator(geography="tribal", bins=5)
        results = agg.create_aggregate(
            indicators=tribal_indicators,
            reference=tribal_reference,
            skip_aggregation=True,
        )

        # Must not raise KeyError
        agg_df = results.get("agg")
        assert agg_df is None

        # Direct access WOULD raise KeyError
        with pytest.raises(KeyError):
            _ = results["agg"]
