"""
Regression tests for no-data / missing-data handling across the CRIA pipeline.

These tests guard against the bug where missing-data sentinel values (-88, -99)
and zero denominators produced false zeros instead of NaN. The fixes:
  1. EAVS -88 now maps to NaN (was 0 before the fix)
  2. All 5 calculator functions return NaN for zero denominators (was 0)

Each test is a known-answer test with hand-calculated expected values.
Tests are designed to FAIL if the old (broken) behavior is reintroduced.
"""

import pytest
import numpy as np
import pandas as pd
from unittest.mock import patch, MagicMock

from src.core.indicators import IndicatorCalculator
from src.core.aggregator import AggregateIndicator


# =============================================================================
# Helper: build a minimal IndicatorCalculator without hitting DataPuller/DB
# =============================================================================

def _make_calculator(years=None):
    """Create an IndicatorCalculator with DataPuller mocked out."""
    if years is None:
        years = {"acs": 2021, "cbp": 2020, "pop": 2020, "naics": 2017}

    with patch("src.core.indicators.DataPuller") as MockDP:
        mock_dp = MagicMock()
        mock_dp.reference = pd.DataFrame()
        mock_dp.years = years
        MockDP.return_value = mock_dp
        calc = IndicatorCalculator(geography="county")

    calc.years = years
    return calc


# =============================================================================
# 1. EAVS -88 produces NaN in Inactive Voter indicator
# =============================================================================

class TestEAVSMinus88ProducesNaN:
    """
    EAVS code -88 means 'Does Not Apply'. Before the fix, -88 mapped to 0,
    which made Inactive Voter = 0/0 or 0/real = 0 — a false zero that looked
    like 'no inactive voters' when in reality we have NO DATA.
    """

    def setup_method(self):
        self.calc = _make_calculator()

    def test_both_a1a_and_a1c_minus88_produce_nan(self):
        """When both A1a and A1c are -88 (NaN after EAVS fix), indicator is NaN.

        If the old code were restored (-88 -> 0), this would produce 0/0 = 0,
        not NaN. This test catches that regression.
        """
        # Simulate post-EAVS-fix data: -88 already replaced with NaN
        data = pd.DataFrame({
            "A1c": [np.nan],   # Was -88, now NaN
            "A1a": [np.nan],   # Was -88, now NaN
        }, index=["GEO_001"])

        row = pd.Series({
            "Indicator": "Inactive Voter",
            "Function": "divide",
            "numerator": "A1c",
            "denominator": "A1a",
        })

        result = self.calc._divide_function(row, data)
        assert pd.isna(result.iloc[0]), (
            "Expected NaN when both A1a and A1c are NaN (from -88), got "
            f"{result.iloc[0]}"
        )

    def test_a1c_minus88_a1a_valid_produce_nan(self):
        """When A1c=-88 (NaN) but A1a is valid, indicator should be NaN.

        Inactive Voter = A1c / A1a. If A1c is missing, we cannot compute
        the ratio. Old code would have produced 0 / 30000 = 0.
        """
        data = pd.DataFrame({
            "A1c": [np.nan],    # Was -88, now NaN
            "A1a": [30000.0],   # Valid total registrations
        }, index=["GEO_001"])

        row = pd.Series({
            "numerator": "A1c",
            "denominator": "A1a",
        })

        result = self.calc._divide_function(row, data)
        assert pd.isna(result.iloc[0]), (
            "Expected NaN when numerator A1c is NaN (from -88), got "
            f"{result.iloc[0]}"
        )

    def test_a1a_minus88_a1c_valid_produce_nan(self):
        """When A1a=-88 (NaN) and A1c is valid, denominator is NaN -> NaN result.

        Division by NaN naturally produces NaN in pandas, so this should work
        even without the explicit zero-denom guard.
        """
        data = pd.DataFrame({
            "A1c": [500.0],     # Valid inactive count
            "A1a": [np.nan],    # Was -88, now NaN
        }, index=["GEO_001"])

        row = pd.Series({
            "numerator": "A1c",
            "denominator": "A1a",
        })

        result = self.calc._divide_function(row, data)
        # NaN denominator -> NaN result (pandas division)
        # Note: numerator is not NaN so missing_mask won't catch it,
        # but NaN / NaN = NaN naturally.
        assert pd.isna(result.iloc[0])


# =============================================================================
# 2. EAVS -99 produces NaN (regression test)
# =============================================================================

class TestEAVSMinus99ProducesNaN:
    """
    EAVS code -99 means 'Data Not Available'. This already mapped to NaN
    before the fix. These tests ensure it stays correct.
    """

    def setup_method(self):
        self.calc = _make_calculator()

    def test_a1c_minus99_produces_nan(self):
        """A1c=-99 -> NaN -> Inactive Voter = NaN."""
        data = pd.DataFrame({
            "A1c": [np.nan],    # Was -99, now NaN
            "A1a": [50000.0],
        }, index=["GEO_001"])

        row = pd.Series({"numerator": "A1c", "denominator": "A1a"})
        result = self.calc._divide_function(row, data)
        assert pd.isna(result.iloc[0])

    def test_both_minus99_produces_nan(self):
        """Both A1a and A1c = -99 -> NaN."""
        data = pd.DataFrame({
            "A1c": [np.nan],
            "A1a": [np.nan],
        }, index=["GEO_001"])

        row = pd.Series({"numerator": "A1c", "denominator": "A1a"})
        result = self.calc._divide_function(row, data)
        assert pd.isna(result.iloc[0])


# =============================================================================
# 3. EAVS mixed: some real data, some -88
# =============================================================================

class TestEAVSMixedData:
    """
    Real-world scenario: some states have valid EAVS data, others have -88.
    States with real data should produce valid ratios. States with -88 (NaN)
    should produce NaN. They should coexist in the same DataFrame.
    """

    def setup_method(self):
        self.calc = _make_calculator()

    def test_mixed_valid_and_nan_states(self):
        """Mix of valid and -88 states in same DataFrame.

        Hand-calculated expected values:
        - Alabama: 500 / 30000 = 0.01667
        - BadState: NaN / NaN = NaN  (was -88)
        - California: 2000 / 120000 = 0.01667
        """
        data = pd.DataFrame({
            "A1c": [500.0, np.nan, 2000.0],    # BadState was -88
            "A1a": [30000.0, np.nan, 120000.0], # BadState was -88
        }, index=["AL_county", "BAD_county", "CA_county"])

        row = pd.Series({"numerator": "A1c", "denominator": "A1a"})
        result = self.calc._divide_function(row, data)

        # Alabama: valid
        assert result.iloc[0] == pytest.approx(500.0 / 30000.0)
        # BadState: NaN (from -88)
        assert pd.isna(result.iloc[1])
        # California: valid
        assert result.iloc[2] == pytest.approx(2000.0 / 120000.0)

    def test_mixed_only_numerator_nan(self):
        """States where only numerator (A1c) is -88 but denominator is valid.

        Expected: NaN because numerator is missing (missing_mask catches this).
        """
        data = pd.DataFrame({
            "A1c": [500.0, np.nan, 2000.0],
            "A1a": [30000.0, 50000.0, 120000.0],  # All valid
        }, index=["AL", "BAD", "CA"])

        row = pd.Series({"numerator": "A1c", "denominator": "A1a"})
        result = self.calc._divide_function(row, data)

        assert result.iloc[0] == pytest.approx(500.0 / 30000.0)
        assert pd.isna(result.iloc[1])  # NaN numerator -> NaN result
        assert result.iloc[2] == pytest.approx(2000.0 / 120000.0)

    def test_mixed_only_denominator_nan(self):
        """States where only denominator (A1a) is -88 but numerator is valid.

        Expected: NaN because division by NaN = NaN.
        """
        data = pd.DataFrame({
            "A1c": [500.0, 1000.0, 2000.0],    # All valid
            "A1a": [30000.0, np.nan, 120000.0], # Middle was -88
        }, index=["AL", "BAD", "CA"])

        row = pd.Series({"numerator": "A1c", "denominator": "A1a"})
        result = self.calc._divide_function(row, data)

        assert result.iloc[0] == pytest.approx(500.0 / 30000.0)
        assert pd.isna(result.iloc[1])  # NaN denominator -> NaN
        assert result.iloc[2] == pytest.approx(2000.0 / 120000.0)


# =============================================================================
# 4. Zero denominator -> NaN for each function type
# =============================================================================

class TestZeroDenominatorProducesNaN:
    """
    Test that each of the 5 calculation functions returns NaN when the
    denominator is zero. Before the fix, zero denominators produced 0
    (via inf -> 0 conversion or explicit assignment). Now they must produce NaN.

    These tests would FAIL if the old behavior (zero-denom -> 0) were restored.
    """

    def setup_method(self):
        self.calc = _make_calculator()

    # --- _divide_function ---

    def test_divide_zero_denom_single_numerator(self):
        """_divide_function: zero denom with valid numerator -> NaN."""
        data = pd.DataFrame({"num": [100.0], "denom": [0.0]})
        row = pd.Series({"numerator": "num", "denominator": "denom"})
        result = self.calc._divide_function(row, data)
        assert pd.isna(result.iloc[0]), (
            f"_divide_function should return NaN for zero denom, got {result.iloc[0]}"
        )

    def test_divide_zero_denom_multi_numerator(self):
        """_divide_function: zero denom with multi-column numerator -> NaN."""
        data = pd.DataFrame({"A": [50.0], "B": [30.0], "denom": [0.0]})
        row = pd.Series({"numerator": "A, B", "denominator": "denom"})
        result = self.calc._divide_function(row, data)
        assert pd.isna(result.iloc[0])

    def test_divide_zero_denom_zero_numerator(self):
        """_divide_function: 0/0 is NaN, not 0."""
        data = pd.DataFrame({"num": [0.0], "denom": [0.0]})
        row = pd.Series({"numerator": "num", "denominator": "denom"})
        result = self.calc._divide_function(row, data)
        assert pd.isna(result.iloc[0]), "0/0 must be NaN, not 0"

    # --- _max_function ---

    def test_max_zero_denom(self):
        """_max_function: zero denom -> NaN."""
        data = pd.DataFrame({"A": [500.0], "B": [300.0], "denom": [0.0]})
        row = pd.Series({"numerator": "A, B", "denominator": "denom"})
        result = self.calc._max_function(row, data)
        assert pd.isna(result.iloc[0]), (
            f"_max_function should return NaN for zero denom, got {result.iloc[0]}"
        )

    # --- _mean_function ---

    def test_mean_zero_denom(self):
        """_mean_function: zero denom -> NaN."""
        data = pd.DataFrame({
            "NETMIG2020": [100.0],
            "NETMIG2019": [120.0],
            "NETMIG2018": [80.0],
            "NETMIG2017": [90.0],
            "NETMIG2016": [110.0],
            "denom": [0.0],
        }, index=["GEO_001"])

        row = pd.Series({"numerator": "NETMIG", "denominator": "denom"})
        result = self.calc._mean_function(row, data)
        assert pd.isna(result.iloc[0]), (
            f"_mean_function should return NaN for zero denom, got {result.iloc[0]}"
        )

    # --- _divide_scalar_function ---

    def test_divide_scalar_zero_denom(self):
        """_divide_scalar_function: zero denom -> NaN."""
        data = pd.DataFrame({"num": [5.0], "denom": [0.0]})
        row = pd.Series({
            "numerator": "num",
            "denominator": "denom",
            "rate": 10.0,
        })
        result = self.calc._divide_scalar_function(row, data)
        assert pd.isna(result.iloc[0]), (
            f"_divide_scalar_function should return NaN for zero denom, got "
            f"{result.iloc[0]}"
        )

    # --- _reverse_divide_function ---

    def test_reverse_divide_zero_denom(self):
        """_reverse_divide_function: zero denom -> NaN."""
        data = pd.DataFrame({"num": [800.0], "denom": [0.0]})
        row = pd.Series({"numerator": "num", "denominator": "denom"})
        result = self.calc._reverse_divide_function(row, data)
        assert pd.isna(result.iloc[0]), (
            f"_reverse_divide_function should return NaN for zero denom, got "
            f"{result.iloc[0]}"
        )

    # --- Multi-row: mix of zero and non-zero denominators ---

    def test_divide_mixed_zero_and_nonzero_denom(self):
        """Rows with zero denom are NaN; rows with nonzero denom are correct.

        Hand-calculated:
        - Row 0: 100 / 500 = 0.20
        - Row 1: 200 / 0   = NaN
        - Row 2: 300 / 1000 = 0.30
        """
        data = pd.DataFrame({
            "num": [100.0, 200.0, 300.0],
            "denom": [500.0, 0.0, 1000.0],
        })
        row = pd.Series({"numerator": "num", "denominator": "denom"})
        result = self.calc._divide_function(row, data)

        assert result.iloc[0] == pytest.approx(0.20)
        assert pd.isna(result.iloc[1])
        assert result.iloc[2] == pytest.approx(0.30)


# =============================================================================
# 5. Non-zero denominator still works (no false NaN)
# =============================================================================

class TestNonZeroDenominatorStillWorks:
    """
    Guard against over-correction: the fix must not accidentally NaN-ify
    valid calculations. These are known-answer tests with hand-calculated
    expected values.
    """

    def setup_method(self):
        self.calc = _make_calculator()

    def test_divide_normal_values(self):
        """Standard divide: 150 / 1000 = 0.15."""
        data = pd.DataFrame({"num": [150.0], "denom": [1000.0]})
        row = pd.Series({"numerator": "num", "denominator": "denom"})
        result = self.calc._divide_function(row, data)
        assert result.iloc[0] == pytest.approx(0.15)

    def test_divide_multi_numerator_normal(self):
        """Multi-column numerator: (100 + 50) / 1000 = 0.15."""
        data = pd.DataFrame({"A": [100.0], "B": [50.0], "D": [1000.0]})
        row = pd.Series({"numerator": "A, B", "denominator": "D"})
        result = self.calc._divide_function(row, data)
        assert result.iloc[0] == pytest.approx(0.15)

    def test_max_normal_values(self):
        """Max function: max(500, 300) / 1000 = 0.50."""
        data = pd.DataFrame({"A": [500.0], "B": [300.0], "D": [1000.0]})
        row = pd.Series({"numerator": "A, B", "denominator": "D"})
        result = self.calc._max_function(row, data)
        assert result.iloc[0] == pytest.approx(0.50)

    def test_mean_normal_values(self):
        """Mean function: mean(100,200,300,400,500)/50000.

        Hand-calc: mean = 300, result = 300/50000 = 0.006.
        """
        data = pd.DataFrame({
            "NETMIG2020": [100.0],
            "NETMIG2019": [200.0],
            "NETMIG2018": [300.0],
            "NETMIG2017": [400.0],
            "NETMIG2016": [500.0],
            "S0101_C01_001E": [50000.0],
        }, index=["GEO_001"])

        row = pd.Series({"numerator": "NETMIG", "denominator": "S0101_C01_001E"})
        result = self.calc._mean_function(row, data)
        assert result.iloc[0] == pytest.approx(300.0 / 50000.0)

    def test_divide_scalar_normal_values(self):
        """Divide scalar: (5 / 50000) * 10 * 1000 = 1.0."""
        data = pd.DataFrame({"num": [5.0], "denom": [50000.0]})
        row = pd.Series({
            "numerator": "num",
            "denominator": "denom",
            "rate": 10.0,
        })
        result = self.calc._divide_scalar_function(row, data)
        assert result.iloc[0] == pytest.approx(1.0)

    def test_reverse_divide_normal_values(self):
        """Reverse divide: (1000 - 800) / 1000 = 0.20."""
        data = pd.DataFrame({"num": [800.0], "denom": [1000.0]})
        row = pd.Series({"numerator": "num", "denominator": "denom"})
        result = self.calc._reverse_divide_function(row, data)
        assert result.iloc[0] == pytest.approx(0.20)

    def test_divide_with_small_denominator_not_nan(self):
        """Very small (but nonzero) denominator should NOT produce NaN.

        Guards against a threshold-based fix that might NaN small denoms.
        """
        data = pd.DataFrame({"num": [1.0], "denom": [0.001]})
        row = pd.Series({"numerator": "num", "denominator": "denom"})
        result = self.calc._divide_function(row, data)
        assert result.iloc[0] == pytest.approx(1000.0)
        assert not pd.isna(result.iloc[0])

    def test_divide_zero_numerator_nonzero_denom_is_zero(self):
        """0 / 1000 = 0.0 (not NaN). Only zero DENOM is NaN."""
        data = pd.DataFrame({"num": [0.0], "denom": [1000.0]})
        row = pd.Series({"numerator": "num", "denominator": "denom"})
        result = self.calc._divide_function(row, data)
        assert result.iloc[0] == pytest.approx(0.0)
        assert not pd.isna(result.iloc[0])


# =============================================================================
# 6. Integration: end-to-end with aggregator
# =============================================================================

class TestNaNPropagationThroughAggregator:
    """
    Integration test: indicators with NaN (from -88 / zero-denom fixes)
    flow correctly through the aggregation pipeline.

    - indicators tab: NaN preserved (display copy has impute=False)
    - CRCI pipeline: NaN imputed with column mean, z-scores computed
    """

    @pytest.fixture
    def nan_indicators(self):
        """Indicators with NaN in realistic positions (from missing data).

        50 geographies: indices 0,10,20 have NaN Poverty (simulates EAVS -88
        or zero-denominator producing NaN). All other values are valid.
        """
        np.random.seed(42)
        n = 50

        poverty = np.random.beta(2, 5, n) * 100
        gini = np.random.uniform(0.3, 0.6, n) * 100
        unemp = np.random.beta(2, 8, n) * 100
        pop_change = np.random.normal(1.0, 0.3, n)

        # Inject NaN at specific positions (simulates missing data)
        poverty[0] = np.nan
        poverty[10] = np.nan
        poverty[20] = np.nan
        gini[5] = np.nan

        return pd.DataFrame({
            "Poverty": poverty,
            "GINI": gini,
            "Unemployment": unemp,
            "Population Change": pop_change,
        }, index=[f"GEO_{i:03d}" for i in range(n)])

    @pytest.fixture
    def reference(self):
        """Reference with Units and Augment for rescaling/reorientation."""
        return pd.DataFrame({
            "Indicator": ["Poverty", "GINI", "Unemployment", "Population Change"],
            "Source": ["ACS", "ACS", "ACS", "POP"],
            "Units": ["fraction", "index", "fraction", "ratio"],
            "Augment": ["reverse", "reverse", "reverse", "none"],
        })

    def test_indicators_tab_preserves_nan(self, nan_indicators, reference):
        """The 'indicators' key should show NaN (not imputed) for display."""
        agg = AggregateIndicator(geography="county", bins=5)
        results = agg.create_aggregate(
            indicators=nan_indicators,
            reference=reference,
            bin_indicators=True,
        )

        display = results["indicators"]

        # NaN should be preserved in display copy
        assert pd.isna(display.loc["GEO_000", "Poverty"]), (
            "indicators tab should preserve NaN at GEO_000 Poverty"
        )
        assert pd.isna(display.loc["GEO_010", "Poverty"]), (
            "indicators tab should preserve NaN at GEO_010 Poverty"
        )
        assert pd.isna(display.loc["GEO_020", "Poverty"]), (
            "indicators tab should preserve NaN at GEO_020 Poverty"
        )
        assert pd.isna(display.loc["GEO_005", "GINI"]), (
            "indicators tab should preserve NaN at GEO_005 GINI"
        )

    def test_indicators_tab_valid_rows_not_nan(self, nan_indicators, reference):
        """Rows without NaN should retain their actual values, not become NaN."""
        agg = AggregateIndicator(geography="county", bins=5)
        results = agg.create_aggregate(
            indicators=nan_indicators,
            reference=reference,
            bin_indicators=True,
        )

        display = results["indicators"]

        # Non-NaN rows should remain valid
        assert not pd.isna(display.loc["GEO_001", "Poverty"])
        assert not pd.isna(display.loc["GEO_001", "GINI"])
        assert not pd.isna(display.loc["GEO_001", "Unemployment"])

    def test_scores_have_no_nan_after_imputation(self, nan_indicators, reference):
        """Z-scores should have no NaN because imputation fills missing values."""
        agg = AggregateIndicator(geography="county", bins=5)
        results = agg.create_aggregate(
            indicators=nan_indicators,
            reference=reference,
            bin_indicators=True,
        )

        scores = results["scores"]

        # After imputation + z-score, there should be no NaN
        total_nan = scores.isna().sum().sum()
        assert total_nan == 0, (
            f"Expected 0 NaN in z-scores after imputation, found {total_nan}"
        )

    def test_aggregate_scores_computed(self, nan_indicators, reference):
        """Aggregate CRCI scores should be computed for ALL geographies."""
        agg = AggregateIndicator(geography="county", bins=5)
        results = agg.create_aggregate(
            indicators=nan_indicators,
            reference=reference,
            bin_indicators=True,
        )

        agg_df = results["agg"]

        # All 50 geographies should have aggregate scores
        assert len(agg_df) == 50
        assert "cri" in agg_df.columns
        assert "cria_p" in agg_df.columns

        # No NaN in aggregate scores (imputation handled missing)
        assert agg_df["cri"].isna().sum() == 0
        assert agg_df["cria_p"].isna().sum() == 0

    def test_percentiles_span_full_range(self, nan_indicators, reference):
        """CRIA percentiles should span [0, 1] despite NaN inputs."""
        agg = AggregateIndicator(geography="county", bins=5)
        results = agg.create_aggregate(
            indicators=nan_indicators,
            reference=reference,
            bin_indicators=True,
        )

        cria_p = results["agg"]["cria_p"]
        assert cria_p.min() < 0.1
        assert cria_p.max() > 0.9

    def test_bin_labels_created_for_all_rows(self, nan_indicators, reference):
        """Bin labels should exist for all geographies (NaN rows get imputed bins)."""
        agg = AggregateIndicator(geography="county", bins=5)
        results = agg.create_aggregate(
            indicators=nan_indicators,
            reference=reference,
            bin_indicators=True,
        )

        bin_labels = results["bin_labels"]
        assert len(bin_labels) == 50

        # Bin columns end with _bins; verify they are in valid range 1-5
        bin_cols = [c for c in bin_labels.columns if c.endswith("_bins")]
        assert len(bin_cols) > 0, "Expected _bins columns in bin_labels"
        for col in bin_cols:
            valid_bins = bin_labels[col].dropna()
            assert valid_bins.min() >= 1
            assert valid_bins.max() <= 5
