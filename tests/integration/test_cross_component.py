"""
Cross-component integration tests for CRIA.

These tests verify that data flows correctly BETWEEN components:
  transformations -> aggregator
  IndicatorCalculator -> AggregateIndicator
  aggregator -> Excel export (with binning metadata)
  clean_series -> z_scores -> normalize -> aggregate (full chain)

Every test uses synthetic data (no real APIs, no production DB).
Internal component logic is NOT mocked — only external dependencies are.
"""

import pytest
import numpy as np
import pandas as pd
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def raw_indicator_data():
    """
    Synthetic indicator data with messy values that exercise clean_series.

    Includes: Excel errors, Census missing codes, valid floats, NaN.
    10 rows to give binning enough data.
    """
    np.random.seed(42)
    n = 10
    geo_ids = [f"GEO_{i:03d}" for i in range(n)]
    return pd.DataFrame(
        {
            "Poverty": [
                0.15, "#DIV/0!", 0.20, "-666666666", 0.18,
                0.22, "null", 0.12, 0.17, 0.19,
            ],
            "GINI": [
                0.45, 0.42, 0.48, 0.50, 0.47,
                0.44, 0.46, 0.41, 0.49, 0.43,
            ],
            "Unemployment": [
                0.08, 0.06, 0.10, 0.09, 0.07,
                0.11, 0.05, 0.08, 0.09, 0.06,
            ],
        },
        index=geo_ids,
    )


@pytest.fixture
def reference_data():
    """Reference data that describes 3 ACS indicators."""
    return pd.DataFrame(
        {
            "Indicator": ["Poverty", "GINI", "Unemployment"],
            "Source": ["ACS", "ACS", "ACS"],
            "Function": ["divide", "divide", "divide"],
            "numerator": ["B17001_002E", "B19083_001E", "B23025_005E"],
            "denominator": ["B17001_001E", "1", "B23025_002E"],
            "Units": ["fraction", "index", "fraction"],
            "Augment": ["reverse", "reverse", "reverse"],
            "Order_2023": [1, 2, 3],
        }
    )


@pytest.fixture
def calculator_reference_data():
    """
    Reference for IndicatorCalculator tests.

    NOTE: The denominator for GINI and Median Income is numeric 1 (scalar),
    not string "1".  The calculator checks isinstance(denom, str) to decide
    whether to look up a column or divide by a scalar.
    """
    return pd.DataFrame(
        {
            "Indicator": ["Poverty", "GINI", "Unemployment"],
            "Source": ["ACS", "ACS", "ACS"],
            "Function": ["divide", "divide", "divide"],
            "numerator": ["B17001_002E", "B19083_001E", "B23025_005E"],
            "denominator": ["B17001_001E", 1, "B23025_002E"],
            "Units": ["fraction", "index", "fraction"],
            "Augment": ["reverse", "reverse", "reverse"],
            "Order_2023": [1, 2, 3],
        }
    )


@pytest.fixture
def source_data_for_calculator():
    """
    Synthetic source data whose raw columns are compatible with a 3-indicator
    reference (Poverty, GINI, Unemployment).  Hand-picked values so we can
    verify the calculator output independently.
    """
    np.random.seed(99)
    n = 10
    geo_ids = [f"GEO_{i:03d}" for i in range(n)]

    pov_denom = np.full(n, 1000.0)
    pov_numer = np.array([100, 150, 200, 120, 180, 220, 130, 160, 170, 140], dtype=float)

    unemp_denom = np.full(n, 500.0)
    unemp_numer = np.array([40, 30, 50, 45, 35, 55, 25, 40, 42, 33], dtype=float)

    gini = np.array([0.45, 0.42, 0.48, 0.50, 0.47, 0.44, 0.46, 0.41, 0.49, 0.43])

    return pd.DataFrame(
        {
            "B17001_002E": pov_numer,
            "B17001_001E": pov_denom,
            "B19083_001E": gini,
            "B23025_005E": unemp_numer,
            "B23025_002E": unemp_denom,
        },
        index=pd.Index(geo_ids, name="GEO_ID"),
    )


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestCrossComponentIntegration:
    """
    Tests that verify data flows correctly between CRIA components.
    Each test exercises a real cross-component interface.
    """

    # ------------------------------------------------------------------
    # 1. transformations -> aggregator
    # ------------------------------------------------------------------
    def test_transformations_fed_into_aggregator(
        self, raw_indicator_data, reference_data
    ):
        """
        Pipeline: raw strings -> clean_series -> calc_z_scores -> normalize
        -> AggregateIndicator.create_aggregate.

        Asserts:
        - Cleaning removed sentinel values and produced floats.
        - Z-scores have mean ~ 0 for each column.
        - Normalized values are in [0, 1].
        - Aggregate output has 'agg', 'cri', 'cria_p' columns with no
          unexpected NaN.
        """
        from src.core.transformations import clean_series, calc_z_scores, normalize_to_range
        from src.core.aggregator import AggregateIndicator

        # --- Step 1: clean each column (mimics _clean_indicators) ---
        df_clean = raw_indicator_data.apply(clean_series, impute=True)

        # No non-float types should remain
        for col in df_clean.columns:
            assert df_clean[col].dtype == np.float64, (
                f"Column {col} has dtype {df_clean[col].dtype} after cleaning"
            )

        # Sentinels ("#DIV/0!", "-666666666", "null") should now be imputed
        assert df_clean.isna().sum().sum() == 0, "Imputation should fill all NaN"

        # --- Step 2: z-scores ---
        df_z = calc_z_scores(df_clean)

        for col in df_z.columns:
            col_mean = df_z[col].mean()
            assert col_mean == pytest.approx(0.0, abs=1e-10), (
                f"Z-score mean for {col} is {col_mean}, expected ~0"
            )

        # --- Step 3: normalize to [0, 1] ---
        df_norm = pd.DataFrame(index=df_z.index)
        for col in df_z.columns:
            df_norm[col] = normalize_to_range(df_z[col], 0.0, 1.0)
            assert df_norm[col].min() == pytest.approx(0.0)
            assert df_norm[col].max() == pytest.approx(1.0)

        # --- Step 4: feed into aggregator ---
        aggregator = AggregateIndicator(geography="county", bins=5)
        results = aggregator.create_aggregate(
            indicators=df_norm,
            reference=reference_data,
            bin_indicators=True,
        )

        agg = results["agg"]
        assert "agg" in agg.columns
        assert "cri" in agg.columns
        assert "cria_p" in agg.columns

        # cri = -agg, verify the relationship holds exactly
        assert (agg["cri"] + agg["agg"]).abs().max() == pytest.approx(0.0, abs=1e-12)

        # cria_p should be in (0, 1] — percentile ranks
        assert agg["cria_p"].min() > 0.0
        assert agg["cria_p"].max() <= 1.0

        # No NaN in aggregate since we imputed everything
        assert agg["agg"].isna().sum() == 0

    # ------------------------------------------------------------------
    # 2. IndicatorCalculator output -> AggregateIndicator
    # ------------------------------------------------------------------
    def test_calculator_output_compatible_with_aggregator(
        self, source_data_for_calculator, calculator_reference_data, reference_data
    ):
        """
        Build synthetic reference + source data, run
        IndicatorCalculator.calculate_all_indicators(), then feed the
        result directly into AggregateIndicator.create_aggregate().

        Asserts:
        - Calculator returns expected indicator columns.
        - Calculator values match hand-computed expected values.
        - Aggregation completes and produces 'cri' column.
        - Number of output rows == number of input rows.
        """
        from src.core.indicators import IndicatorCalculator
        from src.core.aggregator import AggregateIndicator

        # Mock DataPuller so IndicatorCalculator.__init__ doesn't hit APIs.
        # Use calculator_reference_data which has numeric 1 denominator for
        # GINI (the calculator checks isinstance(denom, str) to decide
        # column-lookup vs scalar division).
        with patch("src.core.indicators.DataPuller") as MockDP:
            mock_dp = MagicMock()
            mock_dp.reference = calculator_reference_data
            mock_dp.years = {"acs": 2021, "cbp": 2020, "pop": 2020}
            MockDP.return_value = mock_dp

            calc = IndicatorCalculator(geography="county")

        # Run calculator with our synthetic source data
        indicators = calc.calculate_all_indicators(
            source_data=source_data_for_calculator
        )

        # Verify expected columns exist
        for col in ["Poverty", "GINI", "Unemployment"]:
            assert col in indicators.columns, f"Missing indicator column: {col}"

        # Verify hand-computed values for first row:
        #   Poverty = 100 / 1000 = 0.10
        #   GINI = 0.45 / 1 = 0.45  (scalar denominator 1)
        #   Unemployment = 40 / 500 = 0.08
        assert indicators.loc["GEO_000", "Poverty"] == pytest.approx(0.10)
        assert indicators.loc["GEO_000", "GINI"] == pytest.approx(0.45)
        assert indicators.loc["GEO_000", "Unemployment"] == pytest.approx(0.08)

        # Feed into aggregator (uses string-denominator reference_data for
        # the aggregator, which only needs Indicator/Units/Augment columns)
        aggregator = AggregateIndicator(geography="county", bins=5)
        results = aggregator.create_aggregate(
            indicators=indicators,
            reference=reference_data,
            bin_indicators=True,
        )

        assert len(results["agg"]) == len(source_data_for_calculator)
        assert "cri" in results["agg"].columns
        assert results["agg"]["cri"].isna().sum() == 0

    # ------------------------------------------------------------------
    # 3. Aggregation pipeline -> Excel with binning metadata
    # ------------------------------------------------------------------
    def test_binning_metadata_flows_to_excel(self, reference_data, tmp_path):
        """
        Run full aggregation pipeline with binning, save to Excel via
        save_to_excel, read back, and verify:
        - bin_meta and agg_meta sheets exist
        - 'selected_method' column is present in metadata
        - ref and years sheets present when provided
        """
        from src.core.aggregator import AggregateIndicator

        np.random.seed(77)
        n = 30  # enough for meaningful binning
        geo_ids = [f"GEO_{i:03d}" for i in range(n)]

        indicators = pd.DataFrame(
            {
                "Poverty": np.random.beta(2, 5, n),
                "GINI": np.random.uniform(0.3, 0.6, n),
                "Unemployment": np.random.beta(2, 8, n),
            },
            index=geo_ids,
        )

        aggregator = AggregateIndicator(
            geography="county", bins=5, binning_strategy="auto"
        )
        results = aggregator.create_aggregate(
            indicators=indicators,
            reference=reference_data,
            bin_indicators=True,
        )

        # Save with ref + years metadata
        output_file = tmp_path / "cross_component_test.xlsx"
        years = {"acs": 2021, "cbp": 2020, "pop": 2020}

        aggregator.save_to_excel(
            results=results,
            file_path=str(output_file),
            include_geo=False,
            reference=reference_data,
            years=years,
        )

        assert output_file.exists()

        sheets = pd.read_excel(output_file, sheet_name=None)

        # Key metadata sheets must exist
        assert "bin_meta" in sheets, f"Missing bin_meta sheet. Got: {list(sheets.keys())}"
        assert "agg_meta" in sheets, f"Missing agg_meta sheet. Got: {list(sheets.keys())}"

        # 'selected_method' column must be in bin_meta
        assert "selected_method" in sheets["bin_meta"].columns, (
            f"bin_meta columns: {list(sheets['bin_meta'].columns)}"
        )
        assert "selected_method" in sheets["agg_meta"].columns, (
            f"agg_meta columns: {list(sheets['agg_meta'].columns)}"
        )

        # ref and years tabs should be present
        assert "ref" in sheets, f"Missing ref sheet. Got: {list(sheets.keys())}"
        assert "years" in sheets, f"Missing years sheet. Got: {list(sheets.keys())}"

        # Verify years tab content
        years_df = sheets["years"]
        assert "source" in years_df.columns
        assert "year" in years_df.columns
        assert set(years_df["source"]) == {"acs", "cbp", "pop"}

    # ------------------------------------------------------------------
    # 4. Full chain: raw strings -> clean -> z-score -> normalize -> agg
    # ------------------------------------------------------------------
    def test_clean_series_through_z_scores_through_aggregate(self, reference_data):
        """
        Full transformation pipeline with deliberately ugly input:
        - String floats, Census error codes, CBP top-coding
        - Passes through clean_series, calc_z_scores, normalize_to_range
        - Then into AggregateIndicator

        Asserts:
        - No infinities anywhere in the chain
        - Normalized values bounded in [0, 1]
        - Aggregate values are finite
        - Bin labels in [1, k]
        """
        from src.core.transformations import clean_series, calc_z_scores, normalize_to_range
        from src.core.aggregator import AggregateIndicator

        n = 10
        geo_ids = [f"GEO_{i:03d}" for i in range(n)]

        # Deliberately messy data including CBP special values
        raw = pd.DataFrame(
            {
                "Poverty": [
                    "0.15", "#VALUE!", "0.20", "<Null>", "0.18",
                    "-", "0.22", "0.12", "0.17", "0.19",
                ],
                "GINI": [
                    "0.45", "0.42", "0.48", "0.50", "0.47",
                    "0.44", "0.46", "0.41", "0.49", "0.43",
                ],
                "Unemployment": [
                    "0.08", "0.06", "0.10", "0.09", "0.07",
                    "0.11", "0.05", "0.08", "0.09", "0.06",
                ],
            },
            index=geo_ids,
        )

        # Stage 1: Clean
        df_clean = raw.apply(clean_series, impute=True)
        assert df_clean.isna().sum().sum() == 0, "All NaN should be imputed"
        assert not np.isinf(df_clean.values).any(), "No infinities after cleaning"

        # Stage 2: Z-scores
        df_z = calc_z_scores(df_clean)
        assert not np.isinf(df_z.values).any(), "No infinities after z-scoring"
        for col in df_z.columns:
            assert df_z[col].std() == pytest.approx(1.0, abs=0.15), (
                f"Z-score std for {col} should be ~1.0, got {df_z[col].std()}"
            )

        # Stage 3: Normalize to [0, 1]
        df_norm = pd.DataFrame(index=df_z.index)
        for col in df_z.columns:
            df_norm[col] = normalize_to_range(df_z[col], 0.0, 1.0)

        assert df_norm.min().min() == pytest.approx(0.0)
        assert df_norm.max().max() == pytest.approx(1.0)
        assert not np.isinf(df_norm.values).any(), "No infinities after normalization"

        # Stage 4: Aggregate
        aggregator = AggregateIndicator(geography="county", bins=5)
        results = aggregator.create_aggregate(
            indicators=df_norm,
            reference=reference_data,
            bin_indicators=True,
        )

        agg = results["agg"]
        assert np.isfinite(agg["agg"].values).all(), "Aggregate values must be finite"
        assert np.isfinite(agg["cri"].values).all(), "CRI values must be finite"
        assert np.isfinite(agg["cria_p"].values).all(), "Percentile values must be finite"

        # Bin labels in valid range [1, 5]
        for col in df_norm.columns:
            bin_col = f"{col}_bins"
            if bin_col in results["bin_labels"].columns:
                valid_bins = results["bin_labels"][bin_col].dropna()
                assert valid_bins.min() >= 1, f"{bin_col} has bins < 1"
                assert valid_bins.max() <= 5, f"{bin_col} has bins > 5"

    # ------------------------------------------------------------------
    # 5. Population Change special handling across components
    # ------------------------------------------------------------------
    def test_population_change_special_handling_across_components(self):
        """
        Population Change gets special treatment in multiple components:
        - calc_z_scores: only scale, don't center
        - _aggregate_scores: convert to negative absolute value

        Verify this cross-component contract with known values.
        """
        from src.core.transformations import calc_z_scores
        from src.core.aggregator import AggregateIndicator

        n = 20
        np.random.seed(55)
        geo_ids = [f"GEO_{i:03d}" for i in range(n)]

        # Create indicators including Population Change
        indicators = pd.DataFrame(
            {
                "Poverty": np.random.beta(2, 5, n),
                "GINI": np.random.uniform(0.3, 0.6, n),
                "Population Change": np.random.normal(0.0, 0.05, n),
            },
            index=geo_ids,
        )

        reference = pd.DataFrame(
            {
                "Indicator": ["Poverty", "GINI", "Population Change"],
                "Source": ["ACS", "ACS", "POP"],
                "Function": ["divide", "divide", "mean"],
                "numerator": ["B17001_002E", "B19083_001E", "NETMIG"],
                "denominator": ["B17001_001E", "1", "S0101_C01_001E"],
                "Units": ["fraction", "index", "rate"],
                "Augment": ["reverse", "reverse", "none"],
                "Order_2023": [1, 2, 3],
            }
        )

        # -- Verify transformations contract --
        # calc_z_scores should NOT center Population Change
        df_z = calc_z_scores(indicators)

        # Regular columns should have mean ~0
        assert df_z["Poverty"].mean() == pytest.approx(0.0, abs=1e-10)
        assert df_z["GINI"].mean() == pytest.approx(0.0, abs=1e-10)

        # Population Change should NOT be centered (mean != 0 in general)
        # It's divided by std only.  Verify by recomputing:
        pc_std = indicators["Population Change"].std()
        expected_pc_z = indicators["Population Change"] / pc_std
        pd.testing.assert_series_equal(
            df_z["Population Change"],
            expected_pc_z,
            check_names=False,
            atol=1e-10,
        )

        # -- Verify aggregator contract --
        aggregator = AggregateIndicator(geography="county", bins=5)
        results = aggregator.create_aggregate(
            indicators=indicators,
            reference=reference,
            bin_indicators=True,
        )

        agg = results["agg"]

        # Aggregator should produce 'pop change' (absolute value) column
        assert "pop change" in agg.columns
        assert (agg["pop change"] >= 0).all(), "pop change should be non-negative (absolute value)"

        # pop_p should be valid percentile ranks
        assert "pop_p" in agg.columns
        assert agg["pop_p"].min() > 0.0
        assert agg["pop_p"].max() <= 1.0

    # ------------------------------------------------------------------
    # 6. Rescaling flow: fraction/index indicators get *100
    # ------------------------------------------------------------------
    def test_rescaling_flows_through_aggregation(self, reference_data):
        """
        Indicators with Units='fraction' or 'index' get rescaled (*100)
        inside the aggregator.  Verify the rescaled values propagate
        correctly through reorientation and z-scoring.
        """
        from src.core.aggregator import AggregateIndicator

        n = 10
        geo_ids = [f"GEO_{i:03d}" for i in range(n)]

        # All values in [0,1] — fractions
        indicators = pd.DataFrame(
            {
                "Poverty": [0.15, 0.12, 0.20, 0.18, 0.22,
                            0.10, 0.14, 0.16, 0.19, 0.21],
                "GINI": [0.45, 0.42, 0.48, 0.50, 0.47,
                         0.44, 0.46, 0.41, 0.49, 0.43],
                "Unemployment": [0.08, 0.06, 0.10, 0.09, 0.07,
                                 0.11, 0.05, 0.08, 0.09, 0.06],
            },
            index=geo_ids,
        )

        aggregator = AggregateIndicator(geography="county", bins=5)
        results = aggregator.create_aggregate(
            indicators=indicators,
            reference=reference_data,
            bin_indicators=True,
        )

        # 'pos' contains reoriented values.  Since all three have
        # Augment='reverse', pos[col] = 100 - (indicator * 100)
        # For Poverty GEO_000: 100 - (0.15 * 100) = 85.0
        # (clean_series imputes nothing since there are no invalids)
        pos = results["pos"]
        assert pos.loc["GEO_000", "Poverty"] == pytest.approx(85.0)
        assert pos.loc["GEO_000", "GINI"] == pytest.approx(55.0)
        assert pos.loc["GEO_000", "Unemployment"] == pytest.approx(92.0)

    # ------------------------------------------------------------------
    # 7. Edge case: all-identical values through the full pipeline
    # ------------------------------------------------------------------
    def test_constant_values_degrade_gracefully(self, reference_data):
        """
        If every geography has the same indicator value, std=0.
        calc_z_scores on a DataFrame divides by 0, producing NaN.
        (The Series path returns zeros, but the DataFrame path does not
        have the same guard.)

        The aggregator should complete without raising and the output
        should contain NaN — not inf.  This tests graceful degradation
        of degenerate input through the full pipeline.
        """
        from src.core.aggregator import AggregateIndicator

        n = 10
        geo_ids = [f"GEO_{i:03d}" for i in range(n)]

        # All constant values
        indicators = pd.DataFrame(
            {
                "Poverty": [0.15] * n,
                "GINI": [0.45] * n,
                "Unemployment": [0.08] * n,
            },
            index=geo_ids,
        )

        aggregator = AggregateIndicator(geography="county", bins=5)
        results = aggregator.create_aggregate(
            indicators=indicators,
            reference=reference_data,
            bin_indicators=False,  # binning constant data is degenerate
        )

        agg = results["agg"]
        scores = results["scores"]

        # Z-scores should not contain inf (NaN is acceptable for 0/0)
        assert not np.isinf(scores.values[~np.isnan(scores.values)]).any(), (
            "Z-scores should not be inf for constant data"
        )

        # Aggregate should not contain inf either
        agg_vals = agg["agg"].values
        assert not np.isinf(agg_vals[~np.isnan(agg_vals)]).any(), (
            "Aggregate should not contain inf for constant data"
        )
