"""
Regression tests for bin_labels output issue.

Root causes diagnosed (CONOP_bin_labels_diagnosis.md):
  D1: Tract non-ACS indicators (Civil Org, Hospitals, Pop Change) were all-zero
      because no county imputation occurred. All-zero columns bin to a single
      value, producing "same numbers" in the output.
  D4: geo_reference not passed to create_aggregate() in the pipeline, so
      Connecticut CBP NaN-out and Puerto Rico Limited English NaN-out are dead code.
  D7: Tract defaults to 5 bins instead of 7 when bins= is not explicitly set.

Each test is designed to FAIL on the pre-fix code.

D6 addendum (auditor finding): _nullify_zero_vote_states() uses pandas
  groupby().sum() with default min_count=0, which treats all-NaN A1a/A1c as 0.
  For tract geography (where EAVS data is all NaN), every state is incorrectly
  flagged as a zero-vote state, NaN-ing out the entire Inactive Voter_bins column.
"""

import pytest
import numpy as np
import pandas as pd
from src.core.aggregator import AggregateIndicator
from scripts.run_full_pipeline import (
    _nullify_zero_vote_states,
    _impute_tract_from_county,
    DEFAULT_BINS,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# The 22 CRIA indicators by source
ACS_INDICATORS = [
    "Mobile Homes", "Owner Occupied", "Education", "No Vehicle", "Age",
    "Disability", "Limited English", "Single Parent",
    "Low Access to Communications", "Unemployment", "Unemployed Women",
    "Median Income", "GINI", "Lack of Economic Diversity", "Poverty",
    "Medical", "Uninsured Population",
]
NON_ACS_INDICATORS = [
    "Inactive Voter",   # EAVS
    "Civil Org",        # CBP
    "Population Change", # POP
    "Religion",          # ARDA
    "Hospitals",         # CBP
]
CBP_INDICATORS = ["Civil Org", "Hospitals"]
ALL_INDICATORS = ACS_INDICATORS + NON_ACS_INDICATORS


def _make_reference(indicators=None):
    """Build a minimal reference DataFrame matching config/indicators.yaml."""
    indicators = indicators or ALL_INDICATORS
    source_map = {i: "ACS" for i in ACS_INDICATORS}
    source_map.update({
        "Inactive Voter": "EAVS",
        "Civil Org": "CBP",
        "Population Change": "POP",
        "Religion": "ARDA",
        "Hospitals": "CBP",
    })
    units_map = {i: "fraction" for i in indicators}
    units_map["Median Income"] = "dollars"
    units_map["Population Change"] = "ratio"
    units_map["Civil Org"] = "rate"
    units_map["Hospitals"] = "rate"
    units_map["GINI"] = "index"

    augment_map = {i: "none" for i in indicators}
    for i in ["Poverty", "GINI", "Unemployment", "Mobile Homes",
              "No Vehicle", "Age", "Disability", "Education",
              "Single Parent", "Uninsured Population"]:
        if i in indicators:
            augment_map[i] = "reverse"

    rows = []
    for i in indicators:
        rows.append({
            "Indicator": i,
            "Source": source_map.get(i, "ACS"),
            "Units": units_map.get(i, "fraction"),
            "Augment": augment_map.get(i, "none"),
        })
    return pd.DataFrame(rows)


def _make_indicator_data(n_rows, indicators=None, seed=42):
    """
    Build synthetic indicator data with realistic variance.

    Every indicator gets a distinct distribution to ensure bins are
    differentiated (non-degenerate).
    """
    rng = np.random.RandomState(seed)
    indicators = indicators or ALL_INDICATORS
    data = {}
    for i, name in enumerate(indicators):
        if name == "Median Income":
            # Realistic income values spanning manual bin boundaries
            # [25000, 50000, 75000, 100000]
            data[name] = rng.normal(55000, 20000, n_rows).clip(10000, 150000)
        else:
            # Shift each indicator's distribution so they differ
            loc = 0.3 + 0.02 * i
            scale = 0.05 + 0.01 * i
            data[name] = rng.beta(2 + i * 0.3, 5, n_rows) * scale + loc
    idx = [f"GEO_{j:05d}" for j in range(n_rows)]
    return pd.DataFrame(data, index=idx)


def _make_geo_reference(index, states=None):
    """Build a geography reference DataFrame aligned to indicator index."""
    n = len(index)
    if states is None:
        states = [1] * n  # Alabama default
    return pd.DataFrame({
        "state_name": ["Alabama"] * n,
        "state_abbr": ["AL"] * n,
        "state": states,
    }, index=index)


# ---------------------------------------------------------------------------
# D1: Non-ACS indicators must NOT be all-zero for tract
# ---------------------------------------------------------------------------

class TestNonAcsIndicatorsNotAllZero:
    """
    D1 regression: tract non-ACS indicators (Civil Org, Hospitals,
    Pop Change) were all-zero because the current pipeline has no
    county-to-tract imputation.  If these columns have zero variance,
    binning produces a degenerate single-bin result.
    """

    @pytest.fixture
    def tract_data_with_zeros(self):
        """
        Simulate pre-fix tract data: ACS indicators have variance,
        non-ACS indicators are all zero.
        """
        n = 200
        rng = np.random.RandomState(99)
        data = {}
        for name in ACS_INDICATORS:
            data[name] = rng.uniform(0.05, 0.95, n)
        for name in NON_ACS_INDICATORS:
            data[name] = np.zeros(n)  # all-zero: the bug
        idx = [f"TRACT_{j:05d}" for j in range(n)]
        return pd.DataFrame(data, index=idx)

    def test_all_zero_column_bins_to_single_value(self, tract_data_with_zeros):
        """
        Demonstrate the bug: an all-zero column produces bin values
        that are all identical (degenerate).  This test documents the
        failure mode and will PASS both before and after the fix
        (it is a characterization test).
        """
        agg = AggregateIndicator(geography="tract", bins=7)
        reference = _make_reference()

        results = agg.create_aggregate(
            indicators=tract_data_with_zeros,
            reference=reference,
            bin_indicators=True,
        )

        # For each non-ACS indicator whose raw data is all-zero,
        # the _bins column will have at most 1 unique value (degenerate).
        bin_labels = results["bin_labels"]
        for name in NON_ACS_INDICATORS:
            bin_col = f"{name}_bins"
            if bin_col in bin_labels.columns:
                n_unique = bin_labels[bin_col].dropna().nunique()
                # All-zero -> degenerate bin (1 unique value)
                assert n_unique <= 1, (
                    f"{name} has zero-variance input but produced "
                    f"{n_unique} distinct bins"
                )

    def test_non_acs_indicators_with_variance_produce_multiple_bins(self):
        """
        After the fix, non-ACS indicators should have variance
        (via county imputation or another mechanism) and therefore
        produce multiple distinct bins.

        This test will FAIL on pre-fix code if the input data has
        variance but the pipeline zeros it out.
        """
        n = 200
        indicators = _make_indicator_data(n, seed=77)
        reference = _make_reference()

        agg = AggregateIndicator(geography="tract", bins=7)
        results = agg.create_aggregate(
            indicators=indicators,
            reference=reference,
            bin_indicators=True,
        )

        bin_labels = results["bin_labels"]
        for name in NON_ACS_INDICATORS:
            bin_col = f"{name}_bins"
            if bin_col in bin_labels.columns:
                n_unique = bin_labels[bin_col].dropna().nunique()
                assert n_unique > 1, (
                    f"{name} should have multiple bins when input has variance, "
                    f"got {n_unique}"
                )


# ---------------------------------------------------------------------------
# D4: geo_reference must be passed for CT CBP and PR Limited English
# ---------------------------------------------------------------------------

class TestGeoReferenceEnablesSpecialCases:
    """
    D4 regression: geo_reference was not passed to create_aggregate()
    in the pipeline, so Connecticut CBP NaN-out and Puerto Rico
    Limited English NaN-out were dead code.
    """

    def test_geo_reference_enables_ct_cbp_handling(self):
        """
        When geo_reference IS passed and geography is county,
        Connecticut rows should have NaN for CBP indicators
        (Civil Org, Hospitals).

        FAILS on pre-fix pipeline where geo_reference=None.
        """
        n = 50
        rng = np.random.RandomState(42)
        indicators = _make_indicator_data(n, seed=42)

        # Make a reference that has CBP indicators
        reference = _make_reference()

        # Build geo_reference: first 10 rows are Connecticut
        states = [9] * 10 + [1] * 40  # CT=9, AL=1
        state_names = ["Connecticut"] * 10 + ["Alabama"] * 40
        geo_ref = pd.DataFrame({
            "state_name": state_names,
            "state_abbr": ["CT"] * 10 + ["AL"] * 40,
            "state": states,
        }, index=indicators.index)

        agg = AggregateIndicator(geography="county", bins=5)

        results = agg.create_aggregate(
            indicators=indicators,
            reference=reference,
            geo_reference=geo_ref,
            bin_indicators=True,
        )

        # After cleaning, CT rows should have NaN for CBP indicators
        ct_idx = geo_ref[geo_ref["state_name"] == "Connecticut"].index
        cleaned = results["indicators"]
        for cbp_ind in CBP_INDICATORS:
            if cbp_ind in cleaned.columns:
                assert cleaned.loc[ct_idx, cbp_ind].isna().all(), (
                    f"CT {cbp_ind} should be NaN when geo_reference is passed"
                )

    def test_without_geo_reference_ct_cbp_not_handled(self):
        """
        When geo_reference is NOT passed, CT CBP values remain
        unchanged (bug behavior).  This is the pre-fix state.
        """
        n = 50
        indicators = _make_indicator_data(n, seed=42)
        reference = _make_reference()

        agg = AggregateIndicator(geography="county", bins=5)

        results = agg.create_aggregate(
            indicators=indicators,
            reference=reference,
            geo_reference=None,  # NOT passed
            bin_indicators=True,
        )

        # Without geo_reference, CT handling is skipped.
        # CBP columns should NOT have NaN from the CT special case.
        cleaned = results["indicators"]
        for cbp_ind in CBP_INDICATORS:
            if cbp_ind in cleaned.columns:
                # No NaN introduced by CT handling (imputation may introduce NaN
                # for other reasons, but there should be no wholesale NaN-out)
                assert not cleaned[cbp_ind].isna().all(), (
                    f"{cbp_ind} should not be all-NaN when geo_reference is absent"
                )

    def test_geo_reference_enables_pr_limited_english(self):
        """
        When geo_reference IS passed, Puerto Rico rows should have
        NaN for Limited English.

        FAILS on pre-fix pipeline where geo_reference=None.
        """
        n = 50
        indicators = _make_indicator_data(n, seed=42)
        reference = _make_reference()

        # Build geo_reference: first 5 rows are Puerto Rico
        states = [72] * 5 + [1] * 45
        state_names = ["Puerto Rico"] * 5 + ["Alabama"] * 45
        geo_ref = pd.DataFrame({
            "state_name": state_names,
            "state_abbr": ["PR"] * 5 + ["AL"] * 45,
            "state": states,
        }, index=indicators.index)

        agg = AggregateIndicator(geography="county", bins=5)

        results = agg.create_aggregate(
            indicators=indicators,
            reference=reference,
            geo_reference=geo_ref,
            bin_indicators=True,
        )

        # PR rows should have NaN for Limited English
        pr_idx = geo_ref[geo_ref["state"] == 72].index
        cleaned = results["indicators"]
        assert cleaned.loc[pr_idx, "Limited English"].isna().all(), (
            "PR Limited English should be NaN when geo_reference is passed"
        )

    def test_without_geo_reference_pr_english_not_handled(self):
        """
        When geo_reference is NOT passed, PR Limited English values
        remain unchanged (bug behavior).
        """
        n = 50
        indicators = _make_indicator_data(n, seed=42)
        reference = _make_reference()

        agg = AggregateIndicator(geography="county", bins=5)

        results = agg.create_aggregate(
            indicators=indicators,
            reference=reference,
            geo_reference=None,
            bin_indicators=True,
        )

        cleaned = results["indicators"]
        # Without geo_reference, no NaN-out occurs for Limited English
        assert not cleaned["Limited English"].isna().all(), (
            "Limited English should not be all-NaN without geo_reference"
        )


# ---------------------------------------------------------------------------
# D7: Tract must use 7 bins, not 5
# ---------------------------------------------------------------------------

class TestTractUses7Bins:
    """
    D7 regression: AggregateIndicator defaults to bins=5.
    Tract geography should use 7 bins per domain requirements.
    The pipeline must explicitly pass bins=7 for tract.
    """

    def test_tract_with_7_bins_produces_bins_up_to_7(self):
        """
        When bins=7 is explicitly set (the fix), tract bin values
        should range from 1 to 7.
        """
        n = 500  # Need enough rows for 7 bins
        indicators = _make_indicator_data(n, indicators=ACS_INDICATORS[:5], seed=55)
        reference = _make_reference(indicators=ACS_INDICATORS[:5])

        agg = AggregateIndicator(geography="tract", bins=7)
        results = agg.create_aggregate(
            indicators=indicators,
            reference=reference,
            bin_indicators=True,
        )

        bin_labels = results["bin_labels"]
        max_bin_seen = 0
        for col in indicators.columns:
            bin_col = f"{col}_bins"
            if bin_col in bin_labels.columns:
                col_max = bin_labels[bin_col].dropna().max()
                max_bin_seen = max(max_bin_seen, col_max)

        assert max_bin_seen == pytest.approx(7.0), (
            f"Tract with bins=7 should produce bins up to 7, got {max_bin_seen}"
        )

    def test_default_bins_is_5(self):
        """
        Verify that AggregateIndicator defaults to bins=5.
        This documents the default that must be overridden for tract.
        """
        agg = AggregateIndicator()
        assert agg.bins == 5

    def test_tract_with_default_5_bins_maxes_at_5(self):
        """
        If tract is run with default bins=5 (the bug), bin values
        max at 5 instead of the required 7.

        This test demonstrates the pre-fix failure mode.
        """
        n = 300
        indicators = _make_indicator_data(n, indicators=ACS_INDICATORS[:4], seed=33)
        reference = _make_reference(indicators=ACS_INDICATORS[:4])

        agg = AggregateIndicator(geography="tract", bins=5)  # BUG: should be 7
        results = agg.create_aggregate(
            indicators=indicators,
            reference=reference,
            bin_indicators=True,
        )

        bin_labels = results["bin_labels"]
        for col in indicators.columns:
            bin_col = f"{col}_bins"
            if bin_col in bin_labels.columns:
                col_max = bin_labels[bin_col].dropna().max()
                assert col_max <= 5.0, (
                    f"With bins=5, {col} should not exceed 5, got {col_max}"
                )


# ---------------------------------------------------------------------------
# Bin labels indicators must have distinct distributions
# ---------------------------------------------------------------------------

class TestBinLabelsDistinctDistributions:
    """
    When input data has variance across all indicators, the resulting
    bin_labels should show different distributions per indicator.
    If all indicators show the same distribution, something is wrong.
    """

    def test_bin_labels_indicators_have_distinct_distributions(self):
        """
        No two indicator bin columns should have identical value
        distributions when the input data has distinct distributions.

        This test would catch the symptom of the bug: "all indicators
        show the same numbers" in the bin_labels tab.
        """
        n = 200
        indicators = _make_indicator_data(n, indicators=ACS_INDICATORS[:6], seed=42)
        reference = _make_reference(indicators=ACS_INDICATORS[:6])

        agg = AggregateIndicator(geography="county", bins=5)
        results = agg.create_aggregate(
            indicators=indicators,
            reference=reference,
            bin_indicators=True,
        )

        bin_labels = results["bin_labels"]
        bin_cols = [f"{c}_bins" for c in indicators.columns
                    if f"{c}_bins" in bin_labels.columns]

        # At least some pairs of indicators should have different distributions
        n_identical_pairs = 0
        n_total_pairs = 0
        for i in range(len(bin_cols)):
            for j in range(i + 1, len(bin_cols)):
                n_total_pairs += 1
                col_i = bin_labels[bin_cols[i]].dropna().values
                col_j = bin_labels[bin_cols[j]].dropna().values
                if len(col_i) == len(col_j) and np.array_equal(col_i, col_j):
                    n_identical_pairs += 1

        # Allow some pairs to be identical by coincidence, but not ALL
        assert n_identical_pairs < n_total_pairs, (
            f"All {n_total_pairs} indicator bin pairs are identical. "
            "This indicates degenerate binning."
        )

    def test_no_indicator_100_pct_in_one_bin(self):
        """
        With synthetic data that has variance, no indicator should
        have 100% of its values in a single bin.
        """
        n = 200
        indicators = _make_indicator_data(n, indicators=ACS_INDICATORS[:6], seed=42)
        reference = _make_reference(indicators=ACS_INDICATORS[:6])

        agg = AggregateIndicator(geography="county", bins=5)
        results = agg.create_aggregate(
            indicators=indicators,
            reference=reference,
            bin_indicators=True,
        )

        bin_labels = results["bin_labels"]
        for col in indicators.columns:
            bin_col = f"{col}_bins"
            if bin_col in bin_labels.columns:
                values = bin_labels[bin_col].dropna()
                if len(values) > 0:
                    n_unique = values.nunique()
                    assert n_unique > 1, (
                        f"{col} has all values in a single bin "
                        f"({values.iloc[0]}). Data has variance, so "
                        "this indicates a binning bug."
                    )


# ---------------------------------------------------------------------------
# Tribal non-ACS indicators must be handled (dropped or imputed)
# ---------------------------------------------------------------------------

class TestTribalNonAcsHandling:
    """
    Tribal non-ACS indicators (Civil Org, Hospitals, Pop Change,
    Religion, Inactive Voter) should be either dropped entirely
    or imputed with meaningful values before binning.

    The deprecated code dropped them. If the new code keeps them
    as all-NaN or all-zero, binning will be degenerate.
    """

    def test_tribal_non_acs_zero_columns_degenerate(self):
        """
        Characterize the bug: tribal non-ACS columns that are all-zero
        produce degenerate (single-value) bins.
        """
        n = 100
        rng = np.random.RandomState(88)

        data = {}
        for name in ACS_INDICATORS[:5]:
            data[name] = rng.uniform(0.05, 0.95, n)
        # Simulate tribal: non-ACS indicators are all zero (the bug)
        for name in NON_ACS_INDICATORS:
            data[name] = np.zeros(n)

        idx = [f"TRIBAL_{j:04d}" for j in range(n)]
        indicators = pd.DataFrame(data, index=idx)
        reference = _make_reference(indicators=ACS_INDICATORS[:5] + NON_ACS_INDICATORS)

        agg = AggregateIndicator(geography="tribal", bins=5)
        results = agg.create_aggregate(
            indicators=indicators,
            reference=reference,
            bin_indicators=True,
        )

        bin_labels = results["bin_labels"]
        for name in NON_ACS_INDICATORS:
            bin_col = f"{name}_bins"
            if bin_col in bin_labels.columns:
                n_unique = bin_labels[bin_col].dropna().nunique()
                # All-zero -> at most 1 unique bin value (degenerate)
                assert n_unique <= 1, (
                    f"Tribal {name} (all-zero input) should produce "
                    f"degenerate bins, got {n_unique} unique values"
                )

    def test_tribal_with_valid_non_acs_data_bins_correctly(self):
        """
        If non-ACS data is provided with variance, tribal binning
        should produce multiple bins.
        """
        n = 100
        indicators = _make_indicator_data(
            n,
            indicators=ACS_INDICATORS[:5] + NON_ACS_INDICATORS,
            seed=88,
        )
        # Relabel index for tribal
        indicators.index = [f"TRIBAL_{j:04d}" for j in range(n)]
        reference = _make_reference(indicators=ACS_INDICATORS[:5] + NON_ACS_INDICATORS)

        agg = AggregateIndicator(geography="tribal", bins=5)
        results = agg.create_aggregate(
            indicators=indicators,
            reference=reference,
            bin_indicators=True,
        )

        bin_labels = results["bin_labels"]
        for name in ACS_INDICATORS[:5]:
            bin_col = f"{name}_bins"
            if bin_col in bin_labels.columns:
                n_unique = bin_labels[bin_col].dropna().nunique()
                assert n_unique > 1, (
                    f"Tribal ACS indicator {name} should have multiple bins"
                )


# ---------------------------------------------------------------------------
# County bin labels structure regression test
# ---------------------------------------------------------------------------

class TestCountyBinLabelsStructure:
    """
    Regression: county output should continue to work correctly
    after the fix.  County is the "known good" geography.
    """

    @pytest.fixture
    def county_results(self):
        """Run county aggregation with realistic synthetic data."""
        n = 200
        indicators = _make_indicator_data(n, indicators=ALL_INDICATORS, seed=42)
        reference = _make_reference()

        agg = AggregateIndicator(geography="county", bins=5)
        return agg.create_aggregate(
            indicators=indicators,
            reference=reference,
            bin_indicators=True,
        )

    def test_county_bin_labels_not_empty(self, county_results):
        """bin_labels DataFrame should not be empty."""
        assert not county_results["bin_labels"].empty

    def test_county_bin_labels_has_bins_columns(self, county_results):
        """bin_labels should contain _bins suffixed columns."""
        bin_labels = county_results["bin_labels"]
        bins_cols = [c for c in bin_labels.columns if c.endswith("_bins")]
        assert len(bins_cols) > 0, "No _bins columns found in bin_labels"

    def test_county_bin_values_in_range_1_to_5(self, county_results):
        """All bin values should be integers in [1, 5]."""
        bin_labels = county_results["bin_labels"]
        bins_cols = [c for c in bin_labels.columns if c.endswith("_bins")]

        for col in bins_cols:
            values = bin_labels[col].dropna()
            if len(values) > 0:
                assert values.min() >= 1.0, f"{col} has bins below 1"
                assert values.max() <= 5.0, f"{col} has bins above 5"

    def test_county_bin_labels_preserves_index(self, county_results):
        """bin_labels index should match original indicator index."""
        bin_labels = county_results["bin_labels"]
        expected_idx = county_results["indicators"].index
        assert list(bin_labels.index) == list(expected_idx)

    def test_county_all_expected_keys_present(self, county_results):
        """create_aggregate should return all expected output keys."""
        expected_keys = [
            "indicators", "pos", "scores", "scores_percentiles",
            "agg", "bin_labels", "bin_meta", "agg_labels", "agg_meta"
        ]
        for key in expected_keys:
            assert key in county_results, f"Missing key: {key}"

    def test_county_cri_percentiles_span_range(self, county_results):
        """CRI percentiles should span most of [0, 1]."""
        p = county_results["agg"]["cria_p"]
        assert p.min() < 0.1, "CRI percentiles do not reach low end"
        assert p.max() > 0.9, "CRI percentiles do not reach high end"

    def test_county_bin_meta_has_all_indicators(self, county_results):
        """bin_meta should have entries for all indicators."""
        bin_meta = county_results["bin_meta"]
        indicators_in_meta = bin_meta["indicator"].unique()
        for ind in ALL_INDICATORS:
            assert ind in indicators_in_meta, (
                f"Indicator '{ind}' missing from bin_meta"
            )

    def test_county_multiple_bins_per_indicator(self, county_results):
        """Each indicator should use multiple bins (data has variance)."""
        bin_labels = county_results["bin_labels"]
        for ind in ALL_INDICATORS:
            bin_col = f"{ind}_bins"
            if bin_col in bin_labels.columns:
                n_unique = bin_labels[bin_col].dropna().nunique()
                assert n_unique > 1, (
                    f"County indicator '{ind}' is degenerate "
                    f"(only {n_unique} unique bin value)"
                )


# ---------------------------------------------------------------------------
# Agg labels structure
# ---------------------------------------------------------------------------

class TestAggLabelsStructure:
    """
    Verify that agg_labels (aggregate score bins) are structured
    correctly and use the expected number of bins.
    """

    def test_agg_labels_has_bins_columns(self):
        """agg_labels should contain _bins suffixed columns."""
        n = 200
        indicators = _make_indicator_data(n, indicators=ACS_INDICATORS[:4], seed=42)
        reference = _make_reference(indicators=ACS_INDICATORS[:4])

        agg = AggregateIndicator(geography="county", bins=5)
        results = agg.create_aggregate(
            indicators=indicators,
            reference=reference,
            bin_indicators=True,
        )

        agg_labels = results["agg_labels"]
        bins_cols = [c for c in agg_labels.columns if c.endswith("_bins")]
        assert len(bins_cols) > 0, "No _bins columns in agg_labels"

    def test_agg_labels_bin_values_in_range(self):
        """Aggregate bin values should be in [1, k]."""
        n = 200
        indicators = _make_indicator_data(n, indicators=ACS_INDICATORS[:4], seed=42)
        reference = _make_reference(indicators=ACS_INDICATORS[:4])

        agg = AggregateIndicator(geography="county", bins=5)
        results = agg.create_aggregate(
            indicators=indicators,
            reference=reference,
            bin_indicators=True,
        )

        agg_labels = results["agg_labels"]
        bins_cols = [c for c in agg_labels.columns if c.endswith("_bins")]
        for col in bins_cols:
            values = agg_labels[col].dropna()
            if len(values) > 0:
                assert values.min() >= 1.0, f"agg {col} below 1"
                assert values.max() <= 5.0, f"agg {col} above 5"


# ---------------------------------------------------------------------------
# D6: _nullify_zero_vote_states NaN vote data bug
# ---------------------------------------------------------------------------

class TestNullifyZeroVoteStates:
    """
    D6 regression: _nullify_zero_vote_states() uses groupby().sum()
    with default min_count=0.  Pandas sum() with min_count=0 treats
    all-NaN groups as 0, not NaN.  For tract geography, EAVS data
    (A1a/A1c) is typically all NaN at the tract level.  This causes
    every state to be flagged as zero-vote, NaN-ing out the entire
    Inactive Voter_bins column.

    The fix is to use .sum(min_count=1) so that all-NaN groups
    produce NaN (not 0), and NaN * NaN = NaN != 0, so they are
    NOT flagged as zero-vote states.
    """

    @pytest.fixture
    def _base_results_and_geo(self):
        """
        Build a minimal results dict and geo_reference for
        _nullify_zero_vote_states testing.

        50 rows across 3 states (AL, WY, CT).  Inactive Voter_bins
        has valid bin values 1-5.
        """
        n = 50
        rng = np.random.RandomState(42)

        index = [f"GEO_{i:05d}" for i in range(n)]

        # Assign states: 20 AL, 15 WY, 15 CT
        state_abbrs = ["AL"] * 20 + ["WY"] * 15 + ["CT"] * 15

        geo_reference = pd.DataFrame({
            "state_abbr": state_abbrs,
            "state": [1] * 20 + [56] * 15 + [9] * 15,
            "state_name": ["Alabama"] * 20 + ["Wyoming"] * 15 + ["Connecticut"] * 15,
        }, index=index)

        # Build bin_labels with valid Inactive Voter_bins
        bin_labels = pd.DataFrame({
            "Poverty_bins": rng.randint(1, 6, n).astype(float),
            "Inactive Voter_bins": rng.randint(1, 6, n).astype(float),
        }, index=index)

        results = {
            "bin_labels": bin_labels,
        }

        return results, geo_reference, index, state_abbrs

    def test_nullify_nan_vote_data_not_treated_as_zero(self, _base_results_and_geo):
        """
        When A1a/A1c are all NaN for a geography (e.g. tract),
        _nullify_zero_vote_states should NOT NaN out Inactive Voter_bins
        for any state.

        PRE-FIX BEHAVIOR (FAILS): pandas sum(min_count=0) treats
        all-NaN as 0, so A1a*A1c=0 for every state, and the function
        NaN-ifies every row's Inactive Voter_bins.

        POST-FIX BEHAVIOR (PASSES): sum(min_count=1) produces NaN
        for all-NaN groups, so NaN*NaN=NaN != 0, and no states are
        flagged.
        """
        results, geo_reference, index, _ = _base_results_and_geo

        # Source data where A1a/A1c are ALL NaN (tract-level: no EAVS data)
        source_data = pd.DataFrame({
            "A1a": [np.nan] * 50,
            "A1c": [np.nan] * 50,
        }, index=index)

        original_bins = results["bin_labels"]["Inactive Voter_bins"].copy()

        modified = _nullify_zero_vote_states(
            results=results,
            source_data=source_data,
            geo_reference=geo_reference,
            geographies={"state": pd.DataFrame()},  # not used in this path
        )

        modified_bins = modified["bin_labels"]["Inactive Voter_bins"]

        # After the fix, NO rows should have been NaN'd out because
        # all-NaN sums to NaN (not 0), so no zero-vote states are found.
        n_nan_original = original_bins.isna().sum()
        n_nan_modified = modified_bins.isna().sum()

        assert n_nan_modified == n_nan_original, (
            f"All-NaN A1a/A1c should not cause any NaN-ification, "
            f"but {n_nan_modified - n_nan_original} additional rows were NaN'd. "
            "This indicates sum(min_count=0) is treating NaN as 0."
        )

    def test_actual_zero_vote_states_still_nullified(self, _base_results_and_geo):
        """
        States with ACTUAL zero values in A1a or A1c should still
        have their Inactive Voter_bins NaN'd out.

        This ensures the fix (min_count=1) doesn't break the
        legitimate zero-vote-state detection.
        """
        results, geo_reference, index, state_abbrs = _base_results_and_geo

        # WY has actual zero A1c values (zero-vote state)
        # AL and CT have normal non-zero values
        a1a = []
        a1c = []
        for abbr in state_abbrs:
            if abbr == "WY":
                a1a.append(1000.0)
                a1c.append(0.0)  # actual zero
            else:
                a1a.append(5000.0)
                a1c.append(3000.0)

        source_data = pd.DataFrame({
            "A1a": a1a,
            "A1c": a1c,
        }, index=index)

        modified = _nullify_zero_vote_states(
            results=results,
            source_data=source_data,
            geo_reference=geo_reference,
            geographies={"state": pd.DataFrame()},
        )

        modified_bins = modified["bin_labels"]["Inactive Voter_bins"]

        # WY rows (index 20-34) should be NaN
        wy_idx = geo_reference[geo_reference["state_abbr"] == "WY"].index
        assert modified_bins.loc[wy_idx].isna().all(), (
            "WY (actual zero A1c) should have Inactive Voter_bins NaN'd"
        )

        # AL rows should NOT be NaN
        al_idx = geo_reference[geo_reference["state_abbr"] == "AL"].index
        assert not modified_bins.loc[al_idx].isna().any(), (
            "AL (non-zero votes) should NOT have Inactive Voter_bins NaN'd"
        )

    def test_mixed_nan_and_real_values(self, _base_results_and_geo):
        """
        When some states have real data and others have all-NaN
        (mixed scenario like a partial EAVS dataset), only states
        with actual zeros should be NaN'd.  States with all-NaN
        should be left alone.
        """
        results, geo_reference, index, state_abbrs = _base_results_and_geo

        # AL: real non-zero data; WY: actual zeros; CT: all NaN
        a1a = []
        a1c = []
        for abbr in state_abbrs:
            if abbr == "AL":
                a1a.append(5000.0)
                a1c.append(3000.0)
            elif abbr == "WY":
                a1a.append(1000.0)
                a1c.append(0.0)  # actual zero
            else:  # CT
                a1a.append(np.nan)
                a1c.append(np.nan)

        source_data = pd.DataFrame({
            "A1a": a1a,
            "A1c": a1c,
        }, index=index)

        modified = _nullify_zero_vote_states(
            results=results,
            source_data=source_data,
            geo_reference=geo_reference,
            geographies={"state": pd.DataFrame()},
        )

        modified_bins = modified["bin_labels"]["Inactive Voter_bins"]

        # WY (actual zero): should be NaN'd
        wy_idx = geo_reference[geo_reference["state_abbr"] == "WY"].index
        assert modified_bins.loc[wy_idx].isna().all(), (
            "WY (actual zero) should be NaN'd"
        )

        # AL (non-zero): should NOT be NaN'd
        al_idx = geo_reference[geo_reference["state_abbr"] == "AL"].index
        assert not modified_bins.loc[al_idx].isna().any(), (
            "AL (non-zero votes) should NOT be NaN'd"
        )

        # CT (all-NaN): should NOT be NaN'd (this is the bug!)
        ct_idx = geo_reference[geo_reference["state_abbr"] == "CT"].index
        assert not modified_bins.loc[ct_idx].isna().any(), (
            "CT (all-NaN A1a/A1c) should NOT be NaN'd. "
            "NaN data means 'missing', not 'zero votes'. "
            "This fails when sum(min_count=0) treats NaN as 0."
        )


# ---------------------------------------------------------------------------
# _impute_tract_from_county unit tests
# ---------------------------------------------------------------------------

class TestImputeTractFromCounty:
    """
    Unit tests for _impute_tract_from_county() verifying correct
    county-to-tract FIPS mapping, orphan handling, column preservation,
    and row count invariants.
    """

    @pytest.fixture
    def imputation_setup(self):
        """
        Build a minimal tract + county dataset for imputation testing.

        3 counties (state=1, county=1/3/5) with 6 tracts (2 per county).
        ACS indicators have tract-level values; non-ACS are initially zero.
        County data has real non-ACS values to impute from.
        """
        rng = np.random.RandomState(42)

        # 6 tracts: 2 in each of 3 counties
        tract_idx = [f"TRACT_{i:05d}" for i in range(6)]
        tract_states = [1, 1, 1, 1, 1, 1]
        tract_counties = [1, 1, 3, 3, 5, 5]

        # Tract indicators: ACS have real values, non-ACS are zero
        tract_data = {}
        for name in ACS_INDICATORS[:3]:
            tract_data[name] = rng.uniform(0.1, 0.9, 6)
        for name in NON_ACS_INDICATORS:
            tract_data[name] = np.zeros(6)
        tract_indicators = pd.DataFrame(tract_data, index=tract_idx)

        tract_geo = pd.DataFrame({
            "state": tract_states,
            "county": tract_counties,
        }, index=tract_idx)

        # 3 counties
        county_idx = [f"COUNTY_{i:05d}" for i in range(3)]
        county_states = [1, 1, 1]
        county_counties_vals = [1, 3, 5]

        county_data = {}
        for name in ACS_INDICATORS[:3]:
            county_data[name] = rng.uniform(0.1, 0.9, 3)
        for name in NON_ACS_INDICATORS:
            county_data[name] = rng.uniform(0.01, 0.5, 3)
        county_indicators = pd.DataFrame(county_data, index=county_idx)

        county_geo = pd.DataFrame({
            "state": county_states,
            "county": county_counties_vals,
        }, index=county_idx)

        reference = _make_reference(
            indicators=ACS_INDICATORS[:3] + NON_ACS_INDICATORS
        )

        return {
            "tract_indicators": tract_indicators,
            "reference": reference,
            "tract_geo": tract_geo,
            "county_indicators": county_indicators,
            "county_geo": county_geo,
        }

    def test_correct_county_to_tract_fips_mapping(self, imputation_setup):
        """Non-ACS values should come from the matching (state, county) pair."""
        s = imputation_setup
        result = _impute_tract_from_county(
            indicators=s["tract_indicators"],
            reference=s["reference"],
            geo_reference=s["tract_geo"],
            county_indicators=s["county_indicators"],
            county_geo_reference=s["county_geo"],
        )

        # Tracts 0,1 are in county=1 -> should get county_indicators row 0 values
        # Tracts 2,3 are in county=3 -> should get county_indicators row 1 values
        # Tracts 4,5 are in county=5 -> should get county_indicators row 2 values
        for col in NON_ACS_INDICATORS:
            if col in s["county_indicators"].columns:
                county_vals = s["county_indicators"][col].values
                # Tract 0 and 1 should match county 0
                assert result.loc["TRACT_00000", col] == pytest.approx(county_vals[0])
                assert result.loc["TRACT_00001", col] == pytest.approx(county_vals[0])
                # Tract 2 and 3 should match county 1
                assert result.loc["TRACT_00002", col] == pytest.approx(county_vals[1])
                assert result.loc["TRACT_00003", col] == pytest.approx(county_vals[1])
                # Tract 4 and 5 should match county 2
                assert result.loc["TRACT_00004", col] == pytest.approx(county_vals[2])
                assert result.loc["TRACT_00005", col] == pytest.approx(county_vals[2])

    def test_orphan_tracts_get_nan(self, imputation_setup):
        """Tracts whose (state, county) has no match in county data get NaN."""
        s = imputation_setup

        # Change tract 4,5 to county=99 which doesn't exist in county data
        modified_tract_geo = s["tract_geo"].copy()
        modified_tract_geo.loc["TRACT_00004", "county"] = 99
        modified_tract_geo.loc["TRACT_00005", "county"] = 99

        result = _impute_tract_from_county(
            indicators=s["tract_indicators"],
            reference=s["reference"],
            geo_reference=modified_tract_geo,
            county_indicators=s["county_indicators"],
            county_geo_reference=s["county_geo"],
        )

        for col in NON_ACS_INDICATORS:
            if col in result.columns:
                assert pd.isna(result.loc["TRACT_00004", col]), (
                    f"Orphan tract should get NaN for {col}"
                )
                assert pd.isna(result.loc["TRACT_00005", col]), (
                    f"Orphan tract should get NaN for {col}"
                )

    def test_acs_columns_untouched(self, imputation_setup):
        """ACS indicator columns should not be modified by imputation."""
        s = imputation_setup
        original_acs = s["tract_indicators"][ACS_INDICATORS[:3]].copy()

        result = _impute_tract_from_county(
            indicators=s["tract_indicators"],
            reference=s["reference"],
            geo_reference=s["tract_geo"],
            county_indicators=s["county_indicators"],
            county_geo_reference=s["county_geo"],
        )

        for col in ACS_INDICATORS[:3]:
            pd.testing.assert_series_equal(
                result[col], original_acs[col],
                check_names=True,
                obj=f"ACS column '{col}' should be unchanged after imputation",
            )

    def test_row_count_preserved(self, imputation_setup):
        """Output row count must equal input row count."""
        s = imputation_setup
        result = _impute_tract_from_county(
            indicators=s["tract_indicators"],
            reference=s["reference"],
            geo_reference=s["tract_geo"],
            county_indicators=s["county_indicators"],
            county_geo_reference=s["county_geo"],
        )
        assert len(result) == len(s["tract_indicators"]), (
            f"Row count changed: {len(result)} vs {len(s['tract_indicators'])}"
        )

    def test_no_non_acs_indicators_returns_unchanged(self):
        """When all indicators are ACS, function returns input unchanged."""
        idx = [f"T_{i}" for i in range(3)]
        indicators = pd.DataFrame({
            "Poverty": [0.1, 0.2, 0.3],
        }, index=idx)
        reference = pd.DataFrame({
            "Indicator": ["Poverty"],
            "Source": ["ACS"],
        })
        geo_ref = pd.DataFrame({"state": [1, 1, 1], "county": [1, 1, 1]}, index=idx)
        county_idx = ["C_0"]
        county_ind = pd.DataFrame({"Poverty": [0.15]}, index=county_idx)
        county_geo = pd.DataFrame({"state": [1], "county": [1]}, index=county_idx)

        result = _impute_tract_from_county(
            indicators=indicators,
            reference=reference,
            geo_reference=geo_ref,
            county_indicators=county_ind,
            county_geo_reference=county_geo,
        )
        pd.testing.assert_frame_equal(result, indicators)


# ---------------------------------------------------------------------------
# _nullify_zero_vote_states additional unit tests
# ---------------------------------------------------------------------------

class TestNullifyZeroVoteStatesEdgeCases:
    """Additional edge case tests for _nullify_zero_vote_states."""

    def test_source_data_none_returns_results_unchanged(self):
        """When source_data is None, results should be returned as-is."""
        results = {
            "bin_labels": pd.DataFrame({
                "Inactive Voter_bins": [1.0, 2.0, 3.0],
            }),
        }
        geo_ref = pd.DataFrame({"state_abbr": ["AL", "AL", "AL"]})
        out = _nullify_zero_vote_states(
            results=results,
            source_data=None,
            geo_reference=geo_ref,
            geographies={},
        )
        pd.testing.assert_frame_equal(out["bin_labels"], results["bin_labels"])

    def test_missing_a1a_a1c_returns_results_unchanged(self):
        """When source_data lacks A1a/A1c columns, results returned as-is."""
        idx = [f"G_{i}" for i in range(3)]
        results = {
            "bin_labels": pd.DataFrame({
                "Inactive Voter_bins": [1.0, 2.0, 3.0],
            }, index=idx),
        }
        source_data = pd.DataFrame({"other_col": [1, 2, 3]}, index=idx)
        geo_ref = pd.DataFrame({"state_abbr": ["AL", "AL", "AL"]}, index=idx)
        out = _nullify_zero_vote_states(
            results=results,
            source_data=source_data,
            geo_reference=geo_ref,
            geographies={},
        )
        pd.testing.assert_frame_equal(out["bin_labels"], results["bin_labels"])

    def test_no_inactive_voter_bins_returns_unchanged(self):
        """When bin_labels has no Inactive Voter_bins column, skip gracefully."""
        idx = [f"G_{i}" for i in range(3)]
        results = {
            "bin_labels": pd.DataFrame({
                "Poverty_bins": [1.0, 2.0, 3.0],
            }, index=idx),
        }
        source_data = pd.DataFrame({
            "A1a": [100, 200, 300],
            "A1c": [50, 60, 70],
        }, index=idx)
        geo_ref = pd.DataFrame({"state_abbr": ["AL", "AL", "AL"]}, index=idx)
        out = _nullify_zero_vote_states(
            results=results,
            source_data=source_data,
            geo_reference=geo_ref,
            geographies={},
        )
        pd.testing.assert_frame_equal(out["bin_labels"], results["bin_labels"])


# ---------------------------------------------------------------------------
# Pre-fix regression: DEFAULT_BINS and pipeline configuration
# ---------------------------------------------------------------------------

class TestPreFixRegressionGuards:
    """
    Tests that would FAIL on pre-fix code, serving as regression guards.
    """

    def test_default_bins_tract_is_7(self):
        """
        DEFAULT_BINS["tract"] must be 7.

        Pre-fix code did not set this, defaulting to 5. This test
        catches any regression back to the wrong default.
        """
        assert DEFAULT_BINS["tract"] == 7, (
            f"Tract must use 7 bins, got {DEFAULT_BINS['tract']}"
        )

    def test_default_bins_county_is_5(self):
        """County default should remain 5 bins."""
        assert DEFAULT_BINS["county"] == 5

    def test_default_bins_tribal_is_5(self):
        """Tribal default should remain 5 bins."""
        assert DEFAULT_BINS["tribal"] == 5

    def test_default_bins_state_is_5(self):
        """State default should remain 5 bins."""
        assert DEFAULT_BINS["state"] == 5
