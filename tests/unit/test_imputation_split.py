"""
Tests for the imputation split fix in AggregateIndicator.create_aggregate().

The fix calls _clean_indicators() twice when impute=True (non-tribal):
  - impute=True  -> df_clean  (used internally for z-scores, CRCI pipeline)
  - impute=False -> df_display (stored as results["indicators"])

This means the "indicators" tab preserves NaN (shown as gray on the map)
while the CRCI pipeline still uses mean-imputed values.

When skip_aggregation=True (tribal), behavior is unchanged:
  - impute=False for both display and pipeline (df_display = df_clean)
"""

import numpy as np
import pandas as pd
import pytest

from src.core.aggregator import AggregateIndicator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

INDICATOR_NAMES = [
    "Poverty", "GINI", "Unemployment", "Median Income",
    "Population Change",
]


@pytest.fixture
def reference():
    """Reference DataFrame with mixed Units and Augment values."""
    return pd.DataFrame({
        "Indicator": INDICATOR_NAMES,
        "Source": ["ACS", "ACS", "ACS", "ACS", "POP"],
        "Function": ["divide", "divide", "divide", "divide", "mean"],
        "Units": ["fraction", "index", "fraction", "dollars", "ratio"],
        "Augment": ["reverse", "reverse", "reverse", "none", "none"],
    })


@pytest.fixture
def indicators_with_nan():
    """Synthetic indicators with known NaN positions.

    NaN injected at rows 0, 10, 20 in Poverty and GINI.
    All other values are non-NaN.
    """
    np.random.seed(42)
    n = 50
    geo_ids = [f"0500000US{i:05d}" for i in range(n)]

    data = {
        "Poverty": np.random.beta(2, 5, n),
        "GINI": np.random.uniform(0.3, 0.6, n),
        "Unemployment": np.random.beta(2, 8, n),
        "Median Income": np.random.normal(50000, 15000, n),
        "Population Change": np.random.normal(1.0, 0.3, n),
    }
    # Inject NaN at known positions
    for col in ("Poverty", "GINI"):
        for idx in (0, 10, 20):
            data[col][idx] = np.nan

    df = pd.DataFrame(data, index=geo_ids)
    df.index.name = "GEO_ID"
    return df


@pytest.fixture
def indicators_all_valid():
    """Synthetic indicators with NO NaN values at all."""
    np.random.seed(99)
    n = 50
    geo_ids = [f"0500000US{i:05d}" for i in range(n)]
    data = {
        "Poverty": np.random.beta(2, 5, n),
        "GINI": np.random.uniform(0.3, 0.6, n),
        "Unemployment": np.random.beta(2, 8, n),
        "Median Income": np.random.normal(50000, 15000, n),
        "Population Change": np.random.normal(1.0, 0.3, n),
    }
    df = pd.DataFrame(data, index=geo_ids)
    df.index.name = "GEO_ID"
    return df


@pytest.fixture
def ct_cbp_reference():
    """Reference with a CBP-sourced indicator for CT special case."""
    return pd.DataFrame({
        "Indicator": ["Poverty", "Civil Org"],
        "Source": ["ACS", "CBP"],
        "Function": ["divide", "divide"],
        "Units": ["fraction", "rate"],
        "Augment": ["reverse", "none"],
    })


@pytest.fixture
def pr_reference():
    """Reference including Limited English for PR special case."""
    return pd.DataFrame({
        "Indicator": ["Poverty", "Limited English"],
        "Source": ["ACS", "ACS"],
        "Function": ["divide", "divide"],
        "Units": ["fraction", "fraction"],
        "Augment": ["reverse", "reverse"],
    })


# ======================================================================
# Test 1: Indicators tab preserves NaN
# ======================================================================

class TestIndicatorsTabPreservesNaN:
    """results["indicators"] must preserve NaN where input had NaN."""

    def test_display_indicators_preserve_nan_positions(
        self, indicators_with_nan, reference
    ):
        """NaN at rows 0, 10, 20 in Poverty and GINI must survive into
        results["indicators"] (the display copy)."""
        agg = AggregateIndicator(geography="county", bins=5)
        results = agg.create_aggregate(
            indicators=indicators_with_nan,
            reference=reference,
        )

        display = results["indicators"]

        for col in ("Poverty", "GINI"):
            for row_idx in (0, 10, 20):
                geo_id = f"0500000US{row_idx:05d}"
                assert pd.isna(display.loc[geo_id, col]), (
                    f"Expected NaN at ({geo_id}, {col}) in indicators tab "
                    f"but got {display.loc[geo_id, col]}"
                )

    def test_display_nan_count_matches_input(
        self, indicators_with_nan, reference
    ):
        """The number of NaN values in display must equal the number in input
        (for columns without special-case NaN injection)."""
        agg = AggregateIndicator(geography="county", bins=5)
        results = agg.create_aggregate(
            indicators=indicators_with_nan,
            reference=reference,
        )

        display = results["indicators"]

        for col in INDICATOR_NAMES:
            expected_nan = int(indicators_with_nan[col].isna().sum())
            actual_nan = int(display[col].isna().sum())
            assert actual_nan == expected_nan, (
                f"Column '{col}': expected {expected_nan} NaN in display "
                f"but got {actual_nan}"
            )

    def test_display_non_nan_values_are_float(
        self, indicators_with_nan, reference
    ):
        """Non-NaN values in display must be numeric (float), not strings."""
        agg = AggregateIndicator(geography="county", bins=5)
        results = agg.create_aggregate(
            indicators=indicators_with_nan,
            reference=reference,
        )

        display = results["indicators"]
        for col in INDICATOR_NAMES:
            non_null = display[col].dropna()
            assert non_null.dtype == np.float64, (
                f"Column '{col}' has dtype {non_null.dtype}, expected float64"
            )


# ======================================================================
# Test 2: CRCI pipeline uses imputed values
# ======================================================================

class TestCRCIPipelineUsesImputedValues:
    """z-scores, aggregate, percentiles must use imputed (no NaN) values."""

    def test_scores_have_no_nan(self, indicators_with_nan, reference):
        """Z-scores must NOT have NaN — imputed values were used."""
        agg = AggregateIndicator(geography="county", bins=5)
        results = agg.create_aggregate(
            indicators=indicators_with_nan,
            reference=reference,
        )

        scores = results["scores"]
        assert not scores.isna().any().any(), (
            f"Z-scores have NaN in columns: "
            f"{list(scores.columns[scores.isna().any()])}"
        )

    def test_agg_has_no_nan(self, indicators_with_nan, reference):
        """Aggregate scores must NOT have NaN."""
        agg = AggregateIndicator(geography="county", bins=5)
        results = agg.create_aggregate(
            indicators=indicators_with_nan,
            reference=reference,
        )

        agg_df = results["agg"]
        assert not agg_df.isna().any().any(), (
            f"Aggregate has NaN in columns: "
            f"{list(agg_df.columns[agg_df.isna().any()])}"
        )

    def test_scores_percentiles_have_no_nan(
        self, indicators_with_nan, reference
    ):
        """Score percentiles must NOT have NaN."""
        agg = AggregateIndicator(geography="county", bins=5)
        results = agg.create_aggregate(
            indicators=indicators_with_nan,
            reference=reference,
        )

        pct = results["scores_percentiles"]
        assert not pct.isna().any().any(), (
            f"Score percentiles have NaN in columns: "
            f"{list(pct.columns[pct.isna().any()])}"
        )

    def test_display_has_nan_while_scores_do_not(
        self, indicators_with_nan, reference
    ):
        """Core assertion: same row has NaN in display but NOT in scores.

        This is the key behavior the fix introduces. Row 0 has NaN in
        Poverty on the display tab, but the z-score for Poverty at
        row 0 must be non-NaN (it used the imputed mean).
        """
        agg = AggregateIndicator(geography="county", bins=5)
        results = agg.create_aggregate(
            indicators=indicators_with_nan,
            reference=reference,
        )

        geo_id = "0500000US00000"  # row 0

        # Display: Poverty is NaN
        assert pd.isna(results["indicators"].loc[geo_id, "Poverty"]), (
            "Display tab should show NaN for Poverty at row 0"
        )

        # Scores: Poverty z-score is NOT NaN
        assert not pd.isna(results["scores"].loc[geo_id, "Poverty"]), (
            "Scores should NOT have NaN for Poverty at row 0 — "
            "imputed mean should have been used"
        )


# ======================================================================
# Test 3: CT CBP special case applies to display
# ======================================================================

class TestCTCBPSpecialCase:
    """CT CBP zeros should become NaN on the indicators tab."""

    def test_ct_cbp_nan_on_display(self, ct_cbp_reference):
        """CT counties with CBP data should show NaN on indicators tab."""
        np.random.seed(55)
        n = 20
        geo_ids = [f"0500000US{i:05d}" for i in range(n)]

        # geo_reference: first 5 are Connecticut
        geo_ref = pd.DataFrame({
            "state_name": ["Connecticut"] * 5 + ["Alabama"] * 15,
            "state": [9] * 5 + [1] * 15,
        }, index=geo_ids)

        indicators = pd.DataFrame({
            "Poverty": np.random.beta(2, 5, n),
            "Civil Org": np.random.exponential(2, n),
        }, index=geo_ids)
        indicators.index.name = "GEO_ID"

        agg = AggregateIndicator(geography="county", bins=5)
        results = agg.create_aggregate(
            indicators=indicators,
            reference=ct_cbp_reference,
            geo_reference=geo_ref,
        )

        display = results["indicators"]

        # CT rows (first 5) should be NaN for Civil Org (CBP)
        ct_ids = geo_ids[:5]
        for geo_id in ct_ids:
            assert pd.isna(display.loc[geo_id, "Civil Org"]), (
                f"CT county {geo_id} should have NaN for CBP indicator "
                f"'Civil Org' on display tab, got {display.loc[geo_id, 'Civil Org']}"
            )

        # Non-CT rows should NOT be NaN for Civil Org
        non_ct_ids = geo_ids[5:]
        non_ct_nan = display.loc[non_ct_ids, "Civil Org"].isna().sum()
        assert non_ct_nan == 0, (
            f"Non-CT counties should not have NaN for Civil Org, "
            f"but {non_ct_nan} did"
        )

    def test_ct_cbp_does_not_affect_non_cbp_columns(self, ct_cbp_reference):
        """CT special case should only affect CBP-sourced columns."""
        np.random.seed(56)
        n = 10
        geo_ids = [f"0500000US{i:05d}" for i in range(n)]

        geo_ref = pd.DataFrame({
            "state_name": ["Connecticut"] * n,
            "state": [9] * n,
        }, index=geo_ids)

        indicators = pd.DataFrame({
            "Poverty": np.random.beta(2, 5, n),
            "Civil Org": np.random.exponential(2, n),
        }, index=geo_ids)
        indicators.index.name = "GEO_ID"

        agg = AggregateIndicator(geography="county", bins=5)
        results = agg.create_aggregate(
            indicators=indicators,
            reference=ct_cbp_reference,
            geo_reference=geo_ref,
        )

        display = results["indicators"]

        # Poverty (ACS) should NOT be NaN for CT
        assert not display["Poverty"].isna().any(), (
            "Poverty (ACS) should not be affected by CT CBP special case"
        )


# ======================================================================
# Test 4: PR Limited English special case applies to display
# ======================================================================

class TestPRLimitedEnglishSpecialCase:
    """PR Limited English should show NaN on indicators tab."""

    def test_pr_limited_english_nan_on_display(self, pr_reference):
        """PR rows should have NaN for Limited English on display tab."""
        np.random.seed(57)
        n = 20
        geo_ids = [f"0500000US{i:05d}" for i in range(n)]

        # First 3 are Puerto Rico (state code 72)
        geo_ref = pd.DataFrame({
            "state_name": ["Puerto Rico"] * 3 + ["Alabama"] * 17,
            "state": [72] * 3 + [1] * 17,
        }, index=geo_ids)

        indicators = pd.DataFrame({
            "Poverty": np.random.beta(2, 5, n),
            "Limited English": np.random.beta(3, 3, n),
        }, index=geo_ids)
        indicators.index.name = "GEO_ID"

        agg = AggregateIndicator(geography="county", bins=5)
        results = agg.create_aggregate(
            indicators=indicators,
            reference=pr_reference,
            geo_reference=geo_ref,
        )

        display = results["indicators"]

        # PR rows should be NaN for Limited English
        pr_ids = geo_ids[:3]
        for geo_id in pr_ids:
            assert pd.isna(display.loc[geo_id, "Limited English"]), (
                f"PR county {geo_id} should have NaN for 'Limited English' "
                f"on display tab"
            )

        # Non-PR rows should NOT be NaN for Limited English
        non_pr_ids = geo_ids[3:]
        non_pr_nan = display.loc[non_pr_ids, "Limited English"].isna().sum()
        assert non_pr_nan == 0, (
            f"Non-PR counties should not have NaN for Limited English, "
            f"but {non_pr_nan} did"
        )

    def test_pr_limited_english_does_not_affect_poverty(self, pr_reference):
        """PR special case should only affect Limited English column."""
        np.random.seed(58)
        n = 10
        geo_ids = [f"0500000US{i:05d}" for i in range(n)]

        geo_ref = pd.DataFrame({
            "state_name": ["Puerto Rico"] * n,
            "state": [72] * n,
        }, index=geo_ids)

        indicators = pd.DataFrame({
            "Poverty": np.random.beta(2, 5, n),
            "Limited English": np.random.beta(3, 3, n),
        }, index=geo_ids)
        indicators.index.name = "GEO_ID"

        agg = AggregateIndicator(geography="county", bins=5)
        results = agg.create_aggregate(
            indicators=indicators,
            reference=pr_reference,
            geo_reference=geo_ref,
        )

        display = results["indicators"]

        # Poverty should NOT be NaN for PR
        assert not display["Poverty"].isna().any(), (
            "Poverty should not be affected by PR Limited English special case"
        )


# ======================================================================
# Test 5: Tribal unchanged (skip_aggregation=True)
# ======================================================================

class TestTribalUnchanged:
    """Tribal (skip_aggregation=True) should be unaffected by the fix."""

    def test_tribal_indicators_preserve_nan(self, reference):
        """With skip_aggregation=True, indicators tab preserves NaN
        (same as before the fix — df_display = df_clean)."""
        np.random.seed(60)
        n = 30
        geo_ids = [f"2500000US{i:04d}" for i in range(n)]

        data = {col: np.random.rand(n) for col in INDICATOR_NAMES}
        # Inject NaN at rows 0, 5, 15
        for col in ("Poverty", "GINI"):
            for idx in (0, 5, 15):
                data[col][idx] = np.nan

        indicators = pd.DataFrame(data, index=geo_ids)
        indicators.index.name = "GEO_ID"

        agg = AggregateIndicator(geography="tribal", bins=5)
        results = agg.create_aggregate(
            indicators=indicators,
            reference=reference,
            skip_aggregation=True,
        )

        display = results["indicators"]

        # NaN should be preserved
        for col in ("Poverty", "GINI"):
            for idx in (0, 5, 15):
                geo_id = f"2500000US{idx:04d}"
                assert pd.isna(display.loc[geo_id, col]), (
                    f"Tribal: NaN should be preserved at ({geo_id}, {col})"
                )

    def test_tribal_returns_three_keys_only(self, reference):
        """skip_aggregation=True must still return exactly 3 keys."""
        np.random.seed(61)
        n = 20
        geo_ids = [f"2500000US{i:04d}" for i in range(n)]

        data = {col: np.random.rand(n) for col in INDICATOR_NAMES}
        indicators = pd.DataFrame(data, index=geo_ids)
        indicators.index.name = "GEO_ID"

        agg = AggregateIndicator(geography="tribal", bins=5)
        results = agg.create_aggregate(
            indicators=indicators,
            reference=reference,
            skip_aggregation=True,
        )

        assert set(results.keys()) == {"indicators", "bin_labels", "bin_meta"}


# ======================================================================
# Test 6: All-valid indicator unchanged
# ======================================================================

class TestAllValidIndicatorUnchanged:
    """An indicator with no NaN should be identical regardless of the fix."""

    def test_all_valid_display_has_no_nan(
        self, indicators_all_valid, reference
    ):
        """When input has no NaN, display tab should also have no NaN."""
        agg = AggregateIndicator(geography="county", bins=5)
        results = agg.create_aggregate(
            indicators=indicators_all_valid,
            reference=reference,
        )

        display = results["indicators"]
        assert not display.isna().any().any(), (
            f"All-valid input should produce no NaN in display, "
            f"but NaN found in: {list(display.columns[display.isna().any()])}"
        )

    def test_all_valid_scores_match_display_row_count(
        self, indicators_all_valid, reference
    ):
        """Display and scores should have the same number of rows."""
        agg = AggregateIndicator(geography="county", bins=5)
        results = agg.create_aggregate(
            indicators=indicators_all_valid,
            reference=reference,
        )

        assert len(results["indicators"]) == len(results["scores"])


# ======================================================================
# Test 7: Indicator with ALL NaN
# ======================================================================

class TestAllNaNIndicator:
    """Edge case: what happens when an entire indicator column is NaN?"""

    def test_all_nan_column_preserved_in_display(self, reference):
        """A column that is entirely NaN should remain NaN in display."""
        np.random.seed(70)
        n = 30
        geo_ids = [f"0500000US{i:05d}" for i in range(n)]

        data = {
            "Poverty": [np.nan] * n,  # entirely NaN
            "GINI": np.random.uniform(0.3, 0.6, n),
            "Unemployment": np.random.beta(2, 8, n),
            "Median Income": np.random.normal(50000, 15000, n),
            "Population Change": np.random.normal(1.0, 0.3, n),
        }
        indicators = pd.DataFrame(data, index=geo_ids)
        indicators.index.name = "GEO_ID"

        agg = AggregateIndicator(geography="county", bins=5)
        results = agg.create_aggregate(
            indicators=indicators,
            reference=reference,
        )

        display = results["indicators"]

        # Poverty should be entirely NaN in display
        assert display["Poverty"].isna().all(), (
            "All-NaN Poverty column should remain all NaN in display"
        )

    def test_all_nan_column_is_nan_in_scores_too(self, reference):
        """When an entire column is NaN, imputing with mean gives NaN
        (mean of all-NaN = NaN), so scores will also be NaN for that column.
        This is expected — imputation cannot conjure values from nothing."""
        np.random.seed(71)
        n = 30
        geo_ids = [f"0500000US{i:05d}" for i in range(n)]

        data = {
            "Poverty": [np.nan] * n,
            "GINI": np.random.uniform(0.3, 0.6, n),
            "Unemployment": np.random.beta(2, 8, n),
            "Median Income": np.random.normal(50000, 15000, n),
            "Population Change": np.random.normal(1.0, 0.3, n),
        }
        indicators = pd.DataFrame(data, index=geo_ids)
        indicators.index.name = "GEO_ID"

        agg = AggregateIndicator(geography="county", bins=5)
        results = agg.create_aggregate(
            indicators=indicators,
            reference=reference,
        )

        scores = results["scores"]

        # Poverty scores should also be NaN (mean of NaN = NaN, so
        # imputation with mean still gives NaN, and z-score of NaN = NaN)
        assert scores["Poverty"].isna().all(), (
            "All-NaN column cannot be imputed — scores should also be NaN"
        )

        # But other columns should NOT be NaN
        for col in ("GINI", "Unemployment", "Median Income"):
            assert not scores[col].isna().any(), (
                f"Column '{col}' should not have NaN in scores"
            )


# ======================================================================
# Test 8: Bin labels unchanged (binning uses df_clean, not df_display)
# ======================================================================

class TestBinLabelsUnchanged:
    """Binning uses df_clean (imputed), so bin_labels should be unaffected."""

    def test_bin_labels_have_no_nan_for_partially_nan_input(
        self, indicators_with_nan, reference
    ):
        """Bin labels should NOT have NaN for rows that had NaN in input,
        because binning operates on the imputed df_clean (via df_scale)."""
        agg = AggregateIndicator(geography="county", bins=5)
        results = agg.create_aggregate(
            indicators=indicators_with_nan,
            reference=reference,
        )

        bin_labels = results["bin_labels"]

        # Poverty had NaN at rows 0, 10, 20 in input, but bins should
        # be assigned because binning used the imputed copy
        for row_idx in (0, 10, 20):
            geo_id = f"0500000US{row_idx:05d}"
            bin_val = bin_labels.loc[geo_id, "Poverty_bins"]
            assert not pd.isna(bin_val), (
                f"Bin label for Poverty at {geo_id} should NOT be NaN "
                f"(binning uses imputed values)"
            )

    def test_bin_labels_values_in_valid_range(
        self, indicators_with_nan, reference
    ):
        """All bin values should be in [1, 5] for county (5-bin mode)."""
        agg = AggregateIndicator(geography="county", bins=5)
        results = agg.create_aggregate(
            indicators=indicators_with_nan,
            reference=reference,
        )

        bin_labels = results["bin_labels"]
        for col in INDICATOR_NAMES:
            bins_col = f"{col}_bins"
            if bins_col in bin_labels.columns:
                non_null = bin_labels[bins_col].dropna()
                if len(non_null) > 0:
                    assert non_null.min() >= 1
                    assert non_null.max() <= 5
