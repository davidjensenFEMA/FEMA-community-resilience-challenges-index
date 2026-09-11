"""
Unit tests for IndicatorCalculator (src/core/indicators.py).

Tests cover all 5 function types (divide, max, mean, divide_scalar, reverse_divide),
the numerator parser, and the calculate_all_indicators orchestration. Tests prioritize
failure modes and known-answer verification over structure checks.
"""

import pytest
import numpy as np
import pandas as pd
from unittest.mock import patch, MagicMock

from src.core.indicators import IndicatorCalculator


# =============================================================================
# Helper: build a minimal IndicatorCalculator without hitting DataPuller/DB
# =============================================================================

def _make_calculator(years=None):
    """
    Create an IndicatorCalculator with DataPuller mocked out.
    Returns the calculator instance with controllable .reference and .years.
    """
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
# TestParseNumerator
# =============================================================================

class TestParseNumerator:
    """Tests for _parse_numerator — converts numerator spec to column list."""

    def setup_method(self):
        self.calc = _make_calculator()

    def test_single_column_string(self):
        """Single ACS variable returns a one-element list."""
        result = self.calc._parse_numerator("DP04_0014E")
        assert result == ["DP04_0014E"]

    def test_multi_column_string(self):
        """Comma-separated variables produce a list with each element."""
        result = self.calc._parse_numerator("S1501_C01_007E, S1501_C01_008E")
        assert result == ["S1501_C01_007E", "S1501_C01_008E"]

    def test_numeric_naics_code(self):
        """Numeric NAICS code (e.g. 813410) is converted to string list."""
        result = self.calc._parse_numerator(813410)
        assert result == ["813410"]

    def test_numeric_naics_float(self):
        """Float NAICS code (e.g. 813410.0 from pandas) is truncated to int string."""
        result = self.calc._parse_numerator(813410.0)
        assert result == ["813410"]

    def test_whitespace_handling(self):
        """Leading/trailing whitespace around column names is stripped."""
        result = self.calc._parse_numerator(" DP04_0014E , DP04_0001E ")
        assert result == ["DP04_0014E", "DP04_0001E"]

    def test_many_columns(self):
        """13-column numerator (Economic Diversity) parses correctly."""
        cols = "DP03_0033E, DP03_0034E, DP03_0035E, DP03_0036E, DP03_0037E, DP03_0038E, DP03_0039E, DP03_0040E, DP03_0041E, DP03_0042E, DP03_0043E, DP03_0044E, DP03_0045E"
        result = self.calc._parse_numerator(cols)
        assert len(result) == 13
        assert result[0] == "DP03_0033E"
        assert result[-1] == "DP03_0045E"


# =============================================================================
# TestDivideFunction
# =============================================================================

class TestDivideFunction:
    """Tests for _divide_function: sum(numerators) / denominator."""

    def setup_method(self):
        self.calc = _make_calculator()

    # --- Failure modes first ---

    def test_zero_denominator_returns_nan(self):
        """When denominator is 0, result should be NaN (undefined, not zero)."""
        data = pd.DataFrame({"DP04_0014E": [150.0], "DP04_0001E": [0.0]})
        row = pd.Series({"numerator": "DP04_0014E", "denominator": "DP04_0001E"})
        result = self.calc._divide_function(row, data)
        assert pd.isna(result.iloc[0])

    def test_nan_numerator_returns_nan(self):
        """NaN in numerator column propagates to NaN result."""
        data = pd.DataFrame({"DP04_0014E": [np.nan], "DP04_0001E": [1000.0]})
        row = pd.Series({"numerator": "DP04_0014E", "denominator": "DP04_0001E"})
        result = self.calc._divide_function(row, data)
        assert pd.isna(result.iloc[0])

    def test_nan_in_one_of_multiple_numerators_returns_nan(self):
        """If any numerator col is NaN, result is NaN (uses .any())."""
        data = pd.DataFrame({
            "S1501_C01_007E": [np.nan],
            "S1501_C01_008E": [20.0],
            "S1501_C01_006E": [500.0],
        })
        row = pd.Series({
            "numerator": "S1501_C01_007E, S1501_C01_008E",
            "denominator": "S1501_C01_006E",
        })
        result = self.calc._divide_function(row, data)
        assert pd.isna(result.iloc[0])

    def test_empty_dataframe(self):
        """Empty DataFrame produces empty Series without errors."""
        data = pd.DataFrame({"DP04_0014E": pd.Series(dtype=float),
                             "DP04_0001E": pd.Series(dtype=float)})
        row = pd.Series({"numerator": "DP04_0014E", "denominator": "DP04_0001E"})
        result = self.calc._divide_function(row, data)
        assert len(result) == 0

    # --- Known-answer tests ---

    def test_known_answer_mobile_homes(self):
        """Mobile Homes: 150 / 1000 = 0.15."""
        data = pd.DataFrame({"DP04_0014E": [150.0], "DP04_0001E": [1000.0]})
        row = pd.Series({"numerator": "DP04_0014E", "denominator": "DP04_0001E"})
        result = self.calc._divide_function(row, data)
        assert result.iloc[0] == pytest.approx(0.15)

    def test_known_answer_owner_occupied(self):
        """Owner Occupied: 600 / 1000 = 0.60."""
        data = pd.DataFrame({"DP04_0046E": [600.0], "DP04_0001E": [1000.0]})
        row = pd.Series({"numerator": "DP04_0046E", "denominator": "DP04_0001E"})
        result = self.calc._divide_function(row, data)
        assert result.iloc[0] == pytest.approx(0.60)

    def test_known_answer_education_multi_numerator(self):
        """Education: (80 + 20) / 500 = 0.20 (multi-column numerator)."""
        data = pd.DataFrame({
            "S1501_C01_007E": [80.0],
            "S1501_C01_008E": [20.0],
            "S1501_C01_006E": [500.0],
        })
        row = pd.Series({
            "numerator": "S1501_C01_007E, S1501_C01_008E",
            "denominator": "S1501_C01_006E",
        })
        result = self.calc._divide_function(row, data)
        assert result.iloc[0] == pytest.approx(0.20)

    def test_known_answer_scalar_denominator_gini(self):
        """GINI: 0.45 / 1 = 0.45 (scalar denominator)."""
        data = pd.DataFrame({"B19083_001E": [0.45]})
        row = pd.Series({"numerator": "B19083_001E", "denominator": 1})
        result = self.calc._divide_function(row, data)
        assert result.iloc[0] == pytest.approx(0.45)

    def test_multiple_rows_vectorized(self):
        """Verify vectorized operation across 4 rows."""
        data = pd.DataFrame({
            "DP04_0014E": [150.0, 200.0, 0.0, 500.0],
            "DP04_0001E": [1000.0, 1000.0, 1000.0, 1000.0],
        })
        row = pd.Series({"numerator": "DP04_0014E", "denominator": "DP04_0001E"})
        result = self.calc._divide_function(row, data)
        expected = [0.15, 0.20, 0.0, 0.50]
        for i, exp in enumerate(expected):
            assert result.iloc[i] == pytest.approx(exp)

    def test_zero_denom_with_nan_numerator_is_nan(self):
        """NaN mask takes priority over zero-denominator override."""
        data = pd.DataFrame({"A": [np.nan], "B": [0.0]})
        row = pd.Series({"numerator": "A", "denominator": "B"})
        result = self.calc._divide_function(row, data)
        # The code sets zero-denom to 0, then applies NaN mask last.
        # NaN mask should win.
        assert pd.isna(result.iloc[0])

    def test_nan_denominator_propagates(self):
        """NaN in denominator column results in NaN (regular division)."""
        data = pd.DataFrame({"A": [100.0], "B": [np.nan]})
        row = pd.Series({"numerator": "A", "denominator": "B"})
        result = self.calc._divide_function(row, data)
        # Numerator is not NaN so missing_mask is False, but division
        # by NaN produces NaN naturally.
        assert pd.isna(result.iloc[0])


# =============================================================================
# TestMaxFunction
# =============================================================================

class TestMaxFunction:
    """Tests for _max_function: max(numerators) / denominator."""

    def setup_method(self):
        self.calc = _make_calculator()

    # --- Failure modes first ---

    def test_zero_denominator_returns_nan(self):
        """Zero denominator produces NaN (undefined, not zero)."""
        data = pd.DataFrame({"A": [5000.0], "B": [3000.0], "D": [0.0]})
        row = pd.Series({"numerator": "A, B", "denominator": "D"})
        result = self.calc._max_function(row, data)
        assert pd.isna(result.iloc[0])

    def test_all_nan_numerators_returns_nan(self):
        """When ALL numerator columns are NaN, result is NaN."""
        data = pd.DataFrame({"A": [np.nan], "B": [np.nan], "D": [10000.0]})
        row = pd.Series({"numerator": "A, B", "denominator": "D"})
        result = self.calc._max_function(row, data)
        assert pd.isna(result.iloc[0])

    def test_some_nan_numerators_still_computes(self):
        """When SOME (not all) numerator columns are NaN, max still works.

        _max_function uses .all() for the missing mask, so partial NaN is OK.
        This is the critical difference from _divide_function (.any()).
        """
        data = pd.DataFrame({"A": [np.nan], "B": [3000.0], "D": [10000.0]})
        row = pd.Series({"numerator": "A, B", "denominator": "D"})
        result = self.calc._max_function(row, data)
        # pd.DataFrame.max(axis=1) with skipna=True returns 3000
        assert result.iloc[0] == pytest.approx(0.30)

    # --- Known-answer tests ---

    def test_known_answer_econ_diversity(self):
        """Lack of Economic Diversity: max(5000, 3000) / 10000 = 0.50."""
        data = pd.DataFrame({
            "DP03_0033E": [5000.0],
            "DP03_0034E": [3000.0],
            "DP03_0032E": [10000.0],
        })
        row = pd.Series({
            "numerator": "DP03_0033E, DP03_0034E",
            "denominator": "DP03_0032E",
        })
        result = self.calc._max_function(row, data)
        assert result.iloc[0] == pytest.approx(0.50)

    def test_single_column_max(self):
        """Max of a single column equals that column's value / denom."""
        data = pd.DataFrame({"A": [4000.0], "D": [10000.0]})
        row = pd.Series({"numerator": "A", "denominator": "D"})
        result = self.calc._max_function(row, data)
        assert result.iloc[0] == pytest.approx(0.40)

    def test_multiple_rows(self):
        """Vectorized max across multiple rows picks correct per-row max."""
        data = pd.DataFrame({
            "A": [5000.0, 1000.0, 7000.0],
            "B": [3000.0, 6000.0, 2000.0],
            "D": [10000.0, 10000.0, 10000.0],
        })
        row = pd.Series({"numerator": "A, B", "denominator": "D"})
        result = self.calc._max_function(row, data)
        assert result.iloc[0] == pytest.approx(0.50)  # max(5000,3000)/10000
        assert result.iloc[1] == pytest.approx(0.60)  # max(1000,6000)/10000
        assert result.iloc[2] == pytest.approx(0.70)  # max(7000,2000)/10000

    def test_scalar_denominator(self):
        """Max function with a numeric (scalar) denominator."""
        data = pd.DataFrame({"A": [500.0], "B": [300.0]})
        row = pd.Series({"numerator": "A, B", "denominator": 1000})
        result = self.calc._max_function(row, data)
        assert result.iloc[0] == pytest.approx(0.50)


# =============================================================================
# TestMeanFunction
# =============================================================================

class TestMeanFunction:
    """Tests for _mean_function: mean(NETMIG{years}) / denominator."""

    def setup_method(self):
        self.calc = _make_calculator(years={"pop": 2020})

    # --- Failure modes first ---

    def test_missing_netmig_columns_returns_empty(self):
        """When no NETMIG columns exist, returns empty float Series."""
        data = pd.DataFrame({"S0101_C01_001E": [50000.0]}, index=["GEO1"])
        row = pd.Series({"numerator": "NETMIG", "denominator": "S0101_C01_001E"})
        result = self.calc._mean_function(row, data)
        assert len(result) == 1
        # With no matching columns, the function returns a fresh empty-typed Series
        # (pd.Series(index=data.index, dtype=float))
        assert pd.isna(result.iloc[0])

    def test_zero_denominator_returns_nan(self):
        """Zero denominator produces NaN (undefined, not zero)."""
        data = pd.DataFrame({
            "NETMIG2020": [100.0], "NETMIG2019": [120.0], "NETMIG2018": [80.0],
            "NETMIG2017": [90.0], "NETMIG2016": [110.0],
            "S0101_C01_001E": [0.0],
        })
        row = pd.Series({"numerator": "NETMIG", "denominator": "S0101_C01_001E"})
        result = self.calc._mean_function(row, data)
        assert pd.isna(result.iloc[0])

    # --- Known-answer tests ---

    def test_known_answer_pop_change(self):
        """Population Change: mean(100,120,80,90,110) / 50000 = 0.002."""
        data = pd.DataFrame({
            "NETMIG2020": [100.0], "NETMIG2019": [120.0], "NETMIG2018": [80.0],
            "NETMIG2017": [90.0], "NETMIG2016": [110.0],
            "S0101_C01_001E": [50000.0],
        })
        row = pd.Series({"numerator": "NETMIG", "denominator": "S0101_C01_001E"})
        result = self.calc._mean_function(row, data)
        expected = (100 + 120 + 80 + 90 + 110) / 5 / 50000  # 0.002
        assert result.iloc[0] == pytest.approx(expected)

    def test_year_column_construction(self):
        """Columns NETMIG{year} down to NETMIG{year-4} are constructed."""
        # pop year = 2020 -> expects NETMIG2020, 2019, 2018, 2017, 2016
        data = pd.DataFrame({
            "NETMIG2020": [100.0], "NETMIG2019": [200.0], "NETMIG2018": [300.0],
            "NETMIG2017": [400.0], "NETMIG2016": [500.0],
            "S0101_C01_001E": [10000.0],
        })
        row = pd.Series({"numerator": "NETMIG", "denominator": "S0101_C01_001E"})
        result = self.calc._mean_function(row, data)
        expected = (100 + 200 + 300 + 400 + 500) / 5 / 10000
        assert result.iloc[0] == pytest.approx(expected)

    def test_subset_years_available(self):
        """Only existing NETMIG columns are used when some are missing."""
        # Only 3 of 5 expected columns exist
        data = pd.DataFrame({
            "NETMIG2020": [100.0], "NETMIG2019": [120.0], "NETMIG2018": [80.0],
            "S0101_C01_001E": [50000.0],
        })
        row = pd.Series({"numerator": "NETMIG", "denominator": "S0101_C01_001E"})
        result = self.calc._mean_function(row, data)
        expected = (100 + 120 + 80) / 3 / 50000
        assert result.iloc[0] == pytest.approx(expected)

    def test_scalar_denominator(self):
        """Mean function with numeric (scalar) denominator."""
        data = pd.DataFrame({
            "NETMIG2020": [100.0], "NETMIG2019": [200.0],
            "NETMIG2018": [300.0], "NETMIG2017": [400.0],
            "NETMIG2016": [500.0],
        })
        row = pd.Series({"numerator": "NETMIG", "denominator": 1})
        result = self.calc._mean_function(row, data)
        expected = (100 + 200 + 300 + 400 + 500) / 5 / 1
        assert result.iloc[0] == pytest.approx(expected)

    def test_different_pop_year(self):
        """Pop year 2023 constructs NETMIG2023..2019 columns."""
        calc = _make_calculator(years={"pop": 2023})
        data = pd.DataFrame({
            "NETMIG2023": [50.0], "NETMIG2022": [60.0], "NETMIG2021": [70.0],
            "NETMIG2020": [80.0], "NETMIG2019": [90.0],
            "S0101_C01_001E": [10000.0],
        })
        row = pd.Series({"numerator": "NETMIG", "denominator": "S0101_C01_001E"})
        result = calc._mean_function(row, data)
        expected = (50 + 60 + 70 + 80 + 90) / 5 / 10000
        assert result.iloc[0] == pytest.approx(expected)


# =============================================================================
# TestDivideScalarFunction
# =============================================================================

class TestDivideScalarFunction:
    """Tests for _divide_scalar_function: (sum(nums) / denom) * rate * 1000."""

    def setup_method(self):
        self.calc = _make_calculator()

    # --- Failure modes first ---

    def test_nan_numerator_returns_nan(self):
        """NaN in numerator propagates to NaN result."""
        data = pd.DataFrame({"813410": [np.nan], "S0101_C01_001E": [50000.0]})
        row = pd.Series({
            "numerator": "813410",
            "denominator": "S0101_C01_001E",
            "rate": 10.0,
        })
        result = self.calc._divide_scalar_function(row, data)
        assert pd.isna(result.iloc[0])

    def test_zero_denominator_returns_nan(self):
        """Zero denominator produces NaN (undefined, not zero)."""
        data = pd.DataFrame({"813410": [5.0], "S0101_C01_001E": [0.0]})
        row = pd.Series({
            "numerator": "813410",
            "denominator": "S0101_C01_001E",
            "rate": 10.0,
        })
        result = self.calc._divide_scalar_function(row, data)
        assert pd.isna(result.iloc[0])

    # --- Known-answer tests ---

    def test_known_answer_civil_org(self):
        """Civil Org: (5 / 50000) * 10 * 1000 = 1.0."""
        data = pd.DataFrame({"813410": [5.0], "S0101_C01_001E": [50000.0]})
        row = pd.Series({
            "numerator": "813410",
            "denominator": "S0101_C01_001E",
            "rate": 10.0,
        })
        result = self.calc._divide_scalar_function(row, data)
        assert result.iloc[0] == pytest.approx(1.0)

    def test_known_answer_hospitals(self):
        """Hospitals: (3 / 50000) * 10 * 1000 = 0.6."""
        data = pd.DataFrame({"622110": [3.0], "S0101_C01_001E": [50000.0]})
        row = pd.Series({
            "numerator": "622110",
            "denominator": "S0101_C01_001E",
            "rate": 10.0,
        })
        result = self.calc._divide_scalar_function(row, data)
        assert result.iloc[0] == pytest.approx(0.6)

    def test_known_answer_medical(self):
        """Medical: (500 / 50000) * 1 * 1000 = 10.0."""
        data = pd.DataFrame({"S2401_C01_016E": [500.0], "S0101_C01_001E": [50000.0]})
        row = pd.Series({
            "numerator": "S2401_C01_016E",
            "denominator": "S0101_C01_001E",
            "rate": 1.0,
        })
        result = self.calc._divide_scalar_function(row, data)
        assert result.iloc[0] == pytest.approx(10.0)

    def test_scalar_denominator(self):
        """Scalar denominator (numeric, not column name)."""
        data = pd.DataFrame({"A": [250.0]})
        row = pd.Series({"numerator": "A", "denominator": 1000, "rate": 2.0})
        result = self.calc._divide_scalar_function(row, data)
        # (250 / 1000) * 2 * 1000 = 500.0
        assert result.iloc[0] == pytest.approx(500.0)

    def test_multiple_rows(self):
        """Vectorized across multiple rows."""
        data = pd.DataFrame({
            "813410": [5.0, 10.0, 0.0],
            "S0101_C01_001E": [50000.0, 50000.0, 50000.0],
        })
        row = pd.Series({
            "numerator": "813410",
            "denominator": "S0101_C01_001E",
            "rate": 10.0,
        })
        result = self.calc._divide_scalar_function(row, data)
        assert result.iloc[0] == pytest.approx(1.0)
        assert result.iloc[1] == pytest.approx(2.0)
        assert result.iloc[2] == pytest.approx(0.0)

    def test_zero_denom_with_nan_numerator_is_nan(self):
        """NaN mask takes priority over zero-denom override."""
        data = pd.DataFrame({"A": [np.nan], "B": [0.0]})
        row = pd.Series({"numerator": "A", "denominator": "B", "rate": 1.0})
        result = self.calc._divide_scalar_function(row, data)
        assert pd.isna(result.iloc[0])


# =============================================================================
# TestReverseDivideFunction
# =============================================================================

class TestReverseDivideFunction:
    """Tests for _reverse_divide_function: max(0, denom - sum(nums)) / denom."""

    def setup_method(self):
        self.calc = _make_calculator()

    # --- Failure modes first ---

    def test_zero_denominator_returns_nan(self):
        """Zero denominator produces NaN (undefined, not zero)."""
        data = pd.DataFrame({"S2801_C01_005E": [800.0], "S2801_C01_001E": [0.0]})
        row = pd.Series({
            "numerator": "S2801_C01_005E",
            "denominator": "S2801_C01_001E",
        })
        result = self.calc._reverse_divide_function(row, data)
        assert pd.isna(result.iloc[0])

    def test_nan_numerator_returns_nan(self):
        """NaN in numerator propagates to NaN result."""
        data = pd.DataFrame({"S2801_C01_005E": [np.nan], "S2801_C01_001E": [1000.0]})
        row = pd.Series({
            "numerator": "S2801_C01_005E",
            "denominator": "S2801_C01_001E",
        })
        result = self.calc._reverse_divide_function(row, data)
        assert pd.isna(result.iloc[0])

    def test_denom_less_than_numer_capped_at_zero(self):
        """When numerator > denominator, result is capped at 0 (not negative)."""
        data = pd.DataFrame({"A": [1200.0], "D": [1000.0]})
        row = pd.Series({"numerator": "A", "denominator": "D"})
        result = self.calc._reverse_divide_function(row, data)
        assert result.iloc[0] == pytest.approx(0.0)

    # --- Known-answer tests ---

    def test_known_answer_communications(self):
        """Low Access to Comms: (1000 - 800) / 1000 = 0.20."""
        data = pd.DataFrame({
            "S2801_C01_005E": [800.0],
            "S2801_C01_001E": [1000.0],
        })
        row = pd.Series({
            "numerator": "S2801_C01_005E",
            "denominator": "S2801_C01_001E",
        })
        result = self.calc._reverse_divide_function(row, data)
        assert result.iloc[0] == pytest.approx(0.20)

    def test_known_answer_religion(self):
        """Religion: (50000 - 30000) / 50000 = 0.40."""
        data = pd.DataFrame({"TOTADH": [30000.0], "POP": [50000.0]})
        row = pd.Series({"numerator": "TOTADH", "denominator": "POP"})
        result = self.calc._reverse_divide_function(row, data)
        assert result.iloc[0] == pytest.approx(0.40)

    def test_known_answer_unemployed_women(self):
        """Unemployed Women: (12000 - 8000) / 12000 = 0.3333."""
        data = pd.DataFrame({"DP03_0013E": [8000.0], "DP03_0012E": [12000.0]})
        row = pd.Series({"numerator": "DP03_0013E", "denominator": "DP03_0012E"})
        result = self.calc._reverse_divide_function(row, data)
        assert result.iloc[0] == pytest.approx(4000 / 12000)

    def test_scalar_denominator(self):
        """Reverse divide with numeric (scalar) denominator."""
        data = pd.DataFrame({"A": [300.0]})
        row = pd.Series({"numerator": "A", "denominator": 1000})
        result = self.calc._reverse_divide_function(row, data)
        # (1000 - 300) / 1000 = 0.70
        assert result.iloc[0] == pytest.approx(0.70)

    def test_scalar_denom_capped_at_zero(self):
        """Scalar denominator: numerator > denom still caps at 0."""
        data = pd.DataFrame({"A": [1500.0]})
        row = pd.Series({"numerator": "A", "denominator": 1000})
        result = self.calc._reverse_divide_function(row, data)
        assert result.iloc[0] == pytest.approx(0.0)

    def test_multiple_rows(self):
        """Vectorized across multiple rows."""
        data = pd.DataFrame({
            "A": [800.0, 500.0, 1000.0],
            "D": [1000.0, 1000.0, 1000.0],
        })
        row = pd.Series({"numerator": "A", "denominator": "D"})
        result = self.calc._reverse_divide_function(row, data)
        assert result.iloc[0] == pytest.approx(0.20)
        assert result.iloc[1] == pytest.approx(0.50)
        assert result.iloc[2] == pytest.approx(0.0)   # equal -> 0

    def test_equal_denom_and_numer(self):
        """When numerator equals denominator, result is 0."""
        data = pd.DataFrame({"A": [1000.0], "D": [1000.0]})
        row = pd.Series({"numerator": "A", "denominator": "D"})
        result = self.calc._reverse_divide_function(row, data)
        assert result.iloc[0] == pytest.approx(0.0)


# =============================================================================
# TestCalculateIndicator (dispatch)
# =============================================================================

class TestCalculateIndicator:
    """Tests for _calculate_indicator dispatch routing."""

    def setup_method(self):
        self.calc = _make_calculator()

    def test_dispatches_divide(self):
        """Function='divide' dispatches to _divide_function."""
        data = pd.DataFrame({"A": [100.0], "B": [200.0]})
        row = pd.Series({
            "Indicator": "Test",
            "Function": "divide",
            "numerator": "A",
            "denominator": "B",
        })
        result = self.calc._calculate_indicator(0, row, data)
        assert result.iloc[0] == pytest.approx(0.5)

    def test_dispatches_max(self):
        """Function='max' dispatches to _max_function."""
        data = pd.DataFrame({"A": [300.0], "B": [200.0], "D": [1000.0]})
        row = pd.Series({
            "Indicator": "Test",
            "Function": "max",
            "numerator": "A, B",
            "denominator": "D",
        })
        result = self.calc._calculate_indicator(0, row, data)
        assert result.iloc[0] == pytest.approx(0.3)

    def test_dispatches_mean(self):
        """Function='mean' dispatches to _mean_function."""
        data = pd.DataFrame({
            "NETMIG2020": [100.0], "NETMIG2019": [200.0],
            "NETMIG2018": [300.0], "NETMIG2017": [400.0],
            "NETMIG2016": [500.0],
            "S0101_C01_001E": [10000.0],
        })
        row = pd.Series({
            "Indicator": "Population Change",
            "Function": "mean",
            "numerator": "NETMIG",
            "denominator": "S0101_C01_001E",
        })
        result = self.calc._calculate_indicator(0, row, data)
        assert result.iloc[0] == pytest.approx(300 / 10000)

    def test_dispatches_divide_scalar(self):
        """Function='divide_scalar' dispatches to _divide_scalar_function."""
        data = pd.DataFrame({"A": [5.0], "B": [50000.0]})
        row = pd.Series({
            "Indicator": "Test",
            "Function": "divide_scalar",
            "numerator": "A",
            "denominator": "B",
            "rate": 10.0,
        })
        result = self.calc._calculate_indicator(0, row, data)
        assert result.iloc[0] == pytest.approx(1.0)

    def test_dispatches_reverse_divide(self):
        """Function='reverse_divide' dispatches to _reverse_divide_function."""
        data = pd.DataFrame({"A": [800.0], "D": [1000.0]})
        row = pd.Series({
            "Indicator": "Test",
            "Function": "reverse_divide",
            "numerator": "A",
            "denominator": "D",
        })
        result = self.calc._calculate_indicator(0, row, data)
        assert result.iloc[0] == pytest.approx(0.2)

    def test_unknown_function_returns_empty_series(self):
        """Unknown function returns a float Series of NaN with correct index."""
        data = pd.DataFrame({"A": [100.0]}, index=["GEO1"])
        row = pd.Series({
            "Indicator": "Test",
            "Function": "nonexistent_function",
        })
        result = self.calc._calculate_indicator(0, row, data)
        assert len(result) == 1
        assert result.dtype == float


# =============================================================================
# TestCalculateAllIndicators
# =============================================================================

class TestCalculateAllIndicators:
    """Tests for calculate_all_indicators orchestration."""

    def _make_calc_with_reference(self, reference, years=None):
        """Build a calculator with a specific reference DataFrame."""
        calc = _make_calculator(years=years)
        calc.reference = reference
        return calc

    def test_output_shape_matches_reference(self):
        """Output has one column per reference indicator."""
        reference = pd.DataFrame({
            "Indicator": ["Ind_A", "Ind_B"],
            "Function": ["divide", "divide"],
            "numerator": ["A", "B"],
            "denominator": ["D", "D"],
        })
        data = pd.DataFrame({
            "A": [100.0], "B": [200.0], "D": [1000.0],
        }, index=["GEO1"])
        calc = self._make_calc_with_reference(reference)
        result = calc.calculate_all_indicators(source_data=data)
        assert list(result.columns) == ["Ind_A", "Ind_B"]

    def test_index_preserved(self):
        """Output index matches source_data index."""
        reference = pd.DataFrame({
            "Indicator": ["Ind_A"],
            "Function": ["divide"],
            "numerator": ["A"],
            "denominator": ["D"],
        })
        data = pd.DataFrame({
            "A": [100.0, 200.0], "D": [1000.0, 1000.0],
        }, index=["GEO_ALPHA", "GEO_BETA"])
        calc = self._make_calc_with_reference(reference)
        result = calc.calculate_all_indicators(source_data=data)
        assert list(result.index) == ["GEO_ALPHA", "GEO_BETA"]

    def test_exception_returns_nan_column(self):
        """If an indicator calculation raises, that column is all NaN."""
        reference = pd.DataFrame({
            "Indicator": ["Good", "Bad"],
            "Function": ["divide", "divide"],
            "numerator": ["A", "MISSING_COL"],  # MISSING_COL will raise KeyError
            "denominator": ["D", "D"],
        })
        data = pd.DataFrame({"A": [100.0], "D": [1000.0]}, index=["GEO1"])
        calc = self._make_calc_with_reference(reference)
        result = calc.calculate_all_indicators(source_data=data)

        # Good indicator should work
        assert result["Good"].iloc[0] == pytest.approx(0.1)
        # Bad indicator should be NaN due to caught exception
        assert pd.isna(result["Bad"].iloc[0])

    def test_dispatches_to_correct_function_types(self):
        """Multiple function types are dispatched correctly in one call."""
        reference = pd.DataFrame({
            "Indicator": ["Div", "RevDiv", "DivScalar"],
            "Function": ["divide", "reverse_divide", "divide_scalar"],
            "numerator": ["A", "A", "A"],
            "denominator": ["D", "D", "D"],
            "rate": [np.nan, np.nan, 10.0],
        })
        data = pd.DataFrame({
            "A": [200.0], "D": [1000.0],
        }, index=["GEO1"])
        calc = self._make_calc_with_reference(reference)
        result = calc.calculate_all_indicators(source_data=data)

        # divide: 200/1000 = 0.2
        assert result["Div"].iloc[0] == pytest.approx(0.2)
        # reverse_divide: (1000-200)/1000 = 0.8
        assert result["RevDiv"].iloc[0] == pytest.approx(0.8)
        # divide_scalar: (200/1000) * 10 * 1000 = 2000
        assert result["DivScalar"].iloc[0] == pytest.approx(2000.0)

    def test_pulls_data_when_source_data_is_none(self):
        """When source_data is None, data_puller.pull_all_data() is called."""
        calc = _make_calculator()
        calc.reference = pd.DataFrame({
            "Indicator": ["Ind_A"],
            "Function": ["divide"],
            "numerator": ["A"],
            "denominator": ["D"],
        })
        mock_data = pd.DataFrame({"A": [100.0], "D": [1000.0]}, index=["GEO1"])
        calc.data_puller.pull_all_data.return_value = mock_data

        result = calc.calculate_all_indicators(source_data=None)
        calc.data_puller.pull_all_data.assert_called_once()
        assert result["Ind_A"].iloc[0] == pytest.approx(0.1)

    def test_empty_reference_returns_empty_dataframe(self):
        """Empty reference produces DataFrame with source_data index but no columns."""
        reference = pd.DataFrame(columns=["Indicator", "Function", "numerator", "denominator"])
        data = pd.DataFrame({"A": [100.0]}, index=["GEO1"])
        calc = self._make_calc_with_reference(reference)
        result = calc.calculate_all_indicators(source_data=data)
        assert result.shape == (1, 0)
        assert list(result.index) == ["GEO1"]


# =============================================================================
# TestNaNMaskDifference (critical behavioral difference)
# =============================================================================

class TestNaNMaskDifference:
    """
    Verify the intentional difference between divide (.any()) and max (.all())
    NaN masking. This is a critical behavioral distinction.
    """

    def setup_method(self):
        self.calc = _make_calculator()

    def test_divide_nan_any_one_nan_makes_result_nan(self):
        """_divide_function: ONE NaN in multi-col numerator -> NaN (uses .any())."""
        data = pd.DataFrame({
            "A": [np.nan], "B": [20.0], "D": [100.0],
        })
        row = pd.Series({"numerator": "A, B", "denominator": "D"})
        result = self.calc._divide_function(row, data)
        assert pd.isna(result.iloc[0])

    def test_max_nan_one_nan_still_computes(self):
        """_max_function: ONE NaN in multi-col numerator -> still computes (uses .all())."""
        data = pd.DataFrame({
            "A": [np.nan], "B": [20.0], "D": [100.0],
        })
        row = pd.Series({"numerator": "A, B", "denominator": "D"})
        result = self.calc._max_function(row, data)
        # max(NaN, 20) = 20 via skipna, and missing mask is .all() = False
        assert result.iloc[0] == pytest.approx(0.20)

    def test_max_nan_all_nan_makes_result_nan(self):
        """_max_function: ALL NaN in multi-col numerator -> NaN."""
        data = pd.DataFrame({
            "A": [np.nan], "B": [np.nan], "D": [100.0],
        })
        row = pd.Series({"numerator": "A, B", "denominator": "D"})
        result = self.calc._max_function(row, data)
        assert pd.isna(result.iloc[0])


# =============================================================================
# TestSaveToDatabaseFailFast — defense-in-depth fail-fast on empty maps.
# =============================================================================

class TestSaveToDatabaseFailFast:
    """
    Same doctrine as DataPuller.save_to_database: TOTAL miss → raise (setup
    error); PARTIAL miss → warn-and-continue (data issue).
    """

    def _ref(self, indicators):
        return pd.DataFrame({
            "Indicator": indicators,
            "Source": ["ACS"] * len(indicators),
            "numerator": ["B17001_002E"] * len(indicators),
            "denominator": ["B17001_001E"] * len(indicators),
            "Order_2023": list(range(1, len(indicators) + 1)),
        })

    def _patch_repos(self, ref_get_by_name, geo_id_map):
        ref_repo = MagicMock()
        ref_repo.get_by_name.side_effect = ref_get_by_name
        geo_repo = MagicMock()
        geo_repo.get_geo_id_map.return_value = geo_id_map
        ind_repo = MagicMock()
        ind_repo.bulk_create.return_value = 0
        return (
            patch("src.core.indicators.ReferenceIndicatorRepository", return_value=ref_repo),
            patch("src.core.indicators.GeographyRepository", return_value=geo_repo),
            patch("src.core.indicators.IndicatorRepository", return_value=ind_repo),
        )

    def _make_calc_with_ref(self, reference):
        calc = _make_calculator()
        calc.reference = reference
        return calc

    def test_empty_indicator_map_raises(self):
        """All ref-indicator lookups return None → RuntimeError."""
        calc = self._make_calc_with_ref(self._ref(["Poverty", "GINI"]))
        indicators = pd.DataFrame(
            {"Poverty": [0.1, 0.2]},
            index=["GEO1", "GEO2"],
        )
        p1, p2, p3 = self._patch_repos(
            ref_get_by_name=lambda name: None,
            geo_id_map={"GEO1": 1, "GEO2": 2},
        )
        with p1, p2, p3:
            with pytest.raises(RuntimeError) as exc:
                calc.save_to_database(indicators, year=2021, db=MagicMock())
        msg = str(exc.value)
        assert "indicator_map is empty" in msg
        assert "import_reference_data.py" in msg
        assert "indicators" in msg

    def test_empty_geo_id_map_raises(self):
        """Geographies for this level absent → RuntimeError."""
        calc = self._make_calc_with_ref(self._ref(["Poverty"]))
        indicators = pd.DataFrame(
            {"Poverty": [0.1, 0.2]},
            index=["GEO1", "GEO2"],
        )
        ind = MagicMock()
        ind.id = 7
        p1, p2, p3 = self._patch_repos(
            ref_get_by_name=lambda name: ind,
            geo_id_map={},
        )
        with p1, p2, p3:
            with pytest.raises(RuntimeError) as exc:
                calc.save_to_database(indicators, year=2021, db=MagicMock())
        msg = str(exc.value)
        assert "geo_id_map is empty" in msg
        assert "sync_geographies.py" in msg
        assert "level='county'" in msg

    def test_partial_indicator_miss_does_not_raise(self, caplog):
        """A SINGLE missing indicator must still warn-and-continue (not raise)."""
        import logging
        calc = self._make_calc_with_ref(self._ref(["Poverty", "GINI"]))
        indicators = pd.DataFrame(
            {"Poverty": [0.1], "GINI": [0.4]},
            index=["GEO1"],
        )
        ind = MagicMock()
        ind.id = 7

        def lookup(name):
            return ind if name == "Poverty" else None

        p1, p2, p3 = self._patch_repos(
            ref_get_by_name=lookup,
            geo_id_map={"GEO1": 1},
        )
        with p1, p2, p3:
            with caplog.at_level(logging.WARNING, logger="src.core.indicators"):
                calc.save_to_database(indicators, year=2021, db=MagicMock())

        assert any("GINI" in m for m in caplog.messages)
