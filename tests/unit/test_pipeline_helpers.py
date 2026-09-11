"""
Unit tests for pipeline helper functions in scripts/run_full_pipeline.py.

Targets:
  - _impute_tract_from_county(): Imputes non-ACS indicator values from county to tract
  - _nullify_zero_vote_states(): Sets Inactive Voter_bins to NaN for zero-vote states
  - DEFAULT_BINS: Geography-specific bin count mapping

All tests use synthetic DataFrames — no external APIs or real data.
"""

import numpy as np
import pandas as pd
import pytest

from scripts.run_full_pipeline import (
    DEFAULT_BINS,
    PipelinePreflightError,
    YearMismatchError,
    _impute_tract_from_county,
    _nullify_zero_vote_states,
    preflight_database,
    preflight_year_consistency,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_reference(acs_names, non_acs_names):
    """Build a minimal reference DataFrame with Source column."""
    rows = [{"Indicator": name, "Source": "ACS"} for name in acs_names]
    rows += [{"Indicator": name, "Source": "CBP"} for name in non_acs_names]
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# _impute_tract_from_county tests
# ---------------------------------------------------------------------------

class TestImputeTractFromCounty:
    """Tests for _impute_tract_from_county()."""

    @pytest.fixture
    def impute_setup(self):
        """
        Build synthetic tract and county data for imputation tests.

        Layout:
          - 2 counties: state=01/county=001 and state=01/county=003
          - 4 tracts: first 2 belong to county 001, last 2 to county 003
          - ACS indicator: "Poverty" (should NOT be overwritten)
          - Non-ACS indicator: "Civil Org" (should be imputed from county)
        """
        acs_cols = ["Poverty"]
        non_acs_cols = ["Civil Org"]
        reference = _make_reference(acs_cols, non_acs_cols)

        # County data: 2 counties with known Civil Org values
        county_index = ["COUNTY_01001", "COUNTY_01003"]
        county_indicators = pd.DataFrame({
            "Poverty": [0.12, 0.18],
            "Civil Org": [3.5, 7.2],
        }, index=county_index)
        county_geo = pd.DataFrame({
            "state": ["01", "01"],
            "county": ["001", "003"],
        }, index=county_index)

        # Tract data: 4 tracts, each pair belongs to one county
        tract_index = ["TRACT_A", "TRACT_B", "TRACT_C", "TRACT_D"]
        tract_indicators = pd.DataFrame({
            "Poverty": [0.10, 0.11, 0.20, 0.22],
            "Civil Org": [0.0, 0.0, 0.0, 0.0],  # Pre-fix: all zeros
        }, index=tract_index)
        tract_geo = pd.DataFrame({
            "state": ["01", "01", "01", "01"],
            "county": ["001", "001", "003", "003"],
        }, index=tract_index)

        return {
            "indicators": tract_indicators,
            "reference": reference,
            "geo_reference": tract_geo,
            "county_indicators": county_indicators,
            "county_geo_reference": county_geo,
            "acs_cols": acs_cols,
            "non_acs_cols": non_acs_cols,
        }

    def test_impute_correct_county_to_tract_mapping(self, impute_setup):
        """Tracts get their parent county's non-ACS values."""
        result = _impute_tract_from_county(**{
            k: impute_setup[k]
            for k in [
                "indicators", "reference", "geo_reference",
                "county_indicators", "county_geo_reference",
            ]
        })

        # Tracts A, B -> county 001 -> Civil Org = 3.5
        assert result.loc["TRACT_A", "Civil Org"] == pytest.approx(3.5)
        assert result.loc["TRACT_B", "Civil Org"] == pytest.approx(3.5)
        # Tracts C, D -> county 003 -> Civil Org = 7.2
        assert result.loc["TRACT_C", "Civil Org"] == pytest.approx(7.2)
        assert result.loc["TRACT_D", "Civil Org"] == pytest.approx(7.2)

    def test_impute_only_non_acs_columns_overwritten(self, impute_setup):
        """ACS indicator columns are NOT modified by imputation."""
        original_poverty = impute_setup["indicators"]["Poverty"].copy()

        result = _impute_tract_from_county(**{
            k: impute_setup[k]
            for k in [
                "indicators", "reference", "geo_reference",
                "county_indicators", "county_geo_reference",
            ]
        })

        pd.testing.assert_series_equal(
            result["Poverty"], original_poverty,
            check_names=True,
        )

    def test_impute_orphan_tracts_get_nan(self, impute_setup):
        """Tracts with no matching county get NaN for imputed columns."""
        # Add a tract whose county doesn't exist in county data
        orphan_setup = {k: v for k, v in impute_setup.items()}
        tract_index = ["TRACT_A", "TRACT_B", "TRACT_ORPHAN"]
        orphan_indicators = pd.DataFrame({
            "Poverty": [0.10, 0.11, 0.30],
            "Civil Org": [0.0, 0.0, 0.0],
        }, index=tract_index)
        orphan_geo = pd.DataFrame({
            "state": ["01", "01", "99"],   # state 99 doesn't match any county
            "county": ["001", "001", "999"],
        }, index=tract_index)

        result = _impute_tract_from_county(
            indicators=orphan_indicators,
            reference=impute_setup["reference"],
            geo_reference=orphan_geo,
            county_indicators=impute_setup["county_indicators"],
            county_geo_reference=impute_setup["county_geo_reference"],
        )

        assert pd.isna(result.loc["TRACT_ORPHAN", "Civil Org"])

    def test_impute_preserves_row_count(self, impute_setup):
        """Output has the same number of rows as input."""
        result = _impute_tract_from_county(**{
            k: impute_setup[k]
            for k in [
                "indicators", "reference", "geo_reference",
                "county_indicators", "county_geo_reference",
            ]
        })

        assert len(result) == len(impute_setup["indicators"])

    def test_impute_preserves_index(self, impute_setup):
        """Output index matches input index exactly."""
        result = _impute_tract_from_county(**{
            k: impute_setup[k]
            for k in [
                "indicators", "reference", "geo_reference",
                "county_indicators", "county_geo_reference",
            ]
        })

        assert list(result.index) == list(impute_setup["indicators"].index)

    def test_impute_no_non_acs_returns_unchanged(self):
        """When all indicators are ACS, return input unchanged."""
        reference = pd.DataFrame({
            "Indicator": ["Poverty", "GINI"],
            "Source": ["ACS", "ACS"],
        })
        indicators = pd.DataFrame({
            "Poverty": [0.1, 0.2],
            "GINI": [0.4, 0.5],
        }, index=["T1", "T2"])
        geo = pd.DataFrame({"state": ["01", "01"], "county": ["001", "001"]}, index=["T1", "T2"])
        county_ind = pd.DataFrame({"Poverty": [0.15], "GINI": [0.45]}, index=["C1"])
        county_geo = pd.DataFrame({"state": ["01"], "county": ["001"]}, index=["C1"])

        result = _impute_tract_from_county(indicators, reference, geo, county_ind, county_geo)

        pd.testing.assert_frame_equal(result, indicators)


# ---------------------------------------------------------------------------
# _nullify_zero_vote_states tests
# ---------------------------------------------------------------------------

class TestNullifyZeroVoteStates:
    """Tests for _nullify_zero_vote_states()."""

    @pytest.fixture
    def nullify_setup(self):
        """
        Build synthetic data for zero-vote state tests.

        Layout:
          - 6 rows: 3 in state AL (valid votes), 3 in state WY (zero votes)
          - source_data has A1a, A1c columns
          - bin_labels has Inactive Voter_bins column
          - AL: A1a=1000, A1c=200 -> product != 0 -> valid
          - WY: A1a=0, A1c=0 -> product == 0 -> zero-vote state
        """
        idx = [f"GEO_{i}" for i in range(6)]

        source_data = pd.DataFrame({
            "A1a": [1000, 1100, 1200, 0, 0, 0],
            "A1c": [200, 220, 180, 0, 0, 0],
        }, index=idx)

        geo_reference = pd.DataFrame({
            "state_abbr": ["AL", "AL", "AL", "WY", "WY", "WY"],
        }, index=idx)

        bin_labels = pd.DataFrame({
            "Inactive Voter_bins": [3.0, 2.0, 4.0, 1.0, 2.0, 3.0],
            "Poverty_bins": [1.0, 2.0, 3.0, 4.0, 5.0, 1.0],
        }, index=idx)

        results = {
            "bin_labels": bin_labels,
            "indicators": pd.DataFrame(index=idx),
        }

        geographies = {"state": pd.DataFrame()}  # unused internally

        return {
            "results": results,
            "source_data": source_data,
            "geo_reference": geo_reference,
            "geographies": geographies,
        }

    def test_nullify_zero_vote_states_nans_correct_rows(self, nullify_setup):
        """States with A1a*A1c=0 get Inactive Voter_bins=NaN."""
        out = _nullify_zero_vote_states(**nullify_setup)
        bl = out["bin_labels"]

        # WY rows (indices 3,4,5) should be NaN
        assert pd.isna(bl.loc["GEO_3", "Inactive Voter_bins"])
        assert pd.isna(bl.loc["GEO_4", "Inactive Voter_bins"])
        assert pd.isna(bl.loc["GEO_5", "Inactive Voter_bins"])

    def test_nullify_preserves_valid_vote_states(self, nullify_setup):
        """States with valid votes are untouched."""
        out = _nullify_zero_vote_states(**nullify_setup)
        bl = out["bin_labels"]

        # AL rows (indices 0,1,2) should be unchanged
        assert bl.loc["GEO_0", "Inactive Voter_bins"] == pytest.approx(3.0)
        assert bl.loc["GEO_1", "Inactive Voter_bins"] == pytest.approx(2.0)
        assert bl.loc["GEO_2", "Inactive Voter_bins"] == pytest.approx(4.0)

    def test_nullify_preserves_other_columns(self, nullify_setup):
        """Columns other than Inactive Voter_bins are untouched."""
        original_poverty = nullify_setup["results"]["bin_labels"]["Poverty_bins"].copy()

        out = _nullify_zero_vote_states(**nullify_setup)
        bl = out["bin_labels"]

        pd.testing.assert_series_equal(bl["Poverty_bins"], original_poverty)

    def test_nullify_handles_missing_source_data(self, nullify_setup):
        """source_data=None returns results unchanged."""
        original_bl = nullify_setup["results"]["bin_labels"].copy()

        out = _nullify_zero_vote_states(
            results=nullify_setup["results"],
            source_data=None,
            geo_reference=nullify_setup["geo_reference"],
            geographies=nullify_setup["geographies"],
        )

        pd.testing.assert_frame_equal(out["bin_labels"], original_bl)

    def test_nullify_handles_missing_a1a_column(self, nullify_setup):
        """Graceful if A1a column missing from source_data."""
        # Remove A1a column
        source_data_no_a1a = nullify_setup["source_data"].drop(columns=["A1a"])
        original_bl = nullify_setup["results"]["bin_labels"].copy()

        out = _nullify_zero_vote_states(
            results=nullify_setup["results"],
            source_data=source_data_no_a1a,
            geo_reference=nullify_setup["geo_reference"],
            geographies=nullify_setup["geographies"],
        )

        pd.testing.assert_frame_equal(out["bin_labels"], original_bl)

    def test_nullify_handles_missing_a1c_column(self, nullify_setup):
        """Graceful if A1c column missing from source_data."""
        source_data_no_a1c = nullify_setup["source_data"].drop(columns=["A1c"])
        original_bl = nullify_setup["results"]["bin_labels"].copy()

        out = _nullify_zero_vote_states(
            results=nullify_setup["results"],
            source_data=source_data_no_a1c,
            geo_reference=nullify_setup["geo_reference"],
            geographies=nullify_setup["geographies"],
        )

        pd.testing.assert_frame_equal(out["bin_labels"], original_bl)

    def test_nullify_handles_missing_inactive_voter_bins_column(self, nullify_setup):
        """Graceful if Inactive Voter_bins column not in bin_labels."""
        nullify_setup["results"]["bin_labels"] = nullify_setup["results"]["bin_labels"].drop(
            columns=["Inactive Voter_bins"]
        )
        original_bl = nullify_setup["results"]["bin_labels"].copy()

        out = _nullify_zero_vote_states(**nullify_setup)

        pd.testing.assert_frame_equal(out["bin_labels"], original_bl)

    def test_nullify_handles_missing_state_abbr(self, nullify_setup):
        """Graceful if state_abbr column not in geo_reference."""
        geo_no_abbr = nullify_setup["geo_reference"].drop(columns=["state_abbr"])
        original_bl = nullify_setup["results"]["bin_labels"].copy()

        out = _nullify_zero_vote_states(
            results=nullify_setup["results"],
            source_data=nullify_setup["source_data"],
            geo_reference=geo_no_abbr,
            geographies=nullify_setup["geographies"],
        )

        pd.testing.assert_frame_equal(out["bin_labels"], original_bl)

    def test_nullify_partial_zero_vote_state(self):
        """A state where A1a>0 but A1c=0 should be treated as zero-vote."""
        idx = ["GEO_0", "GEO_1"]
        source_data = pd.DataFrame({
            "A1a": [500, 500],
            "A1c": [0, 0],
        }, index=idx)
        geo_reference = pd.DataFrame({
            "state_abbr": ["TX", "TX"],
        }, index=idx)
        bin_labels = pd.DataFrame({
            "Inactive Voter_bins": [2.0, 4.0],
        }, index=idx)
        results = {"bin_labels": bin_labels}
        geographies = {}

        out = _nullify_zero_vote_states(results, source_data, geo_reference, geographies)

        # A1a*A1c = 500*0 = 0 -> zero-vote
        assert pd.isna(out["bin_labels"].loc["GEO_0", "Inactive Voter_bins"])
        assert pd.isna(out["bin_labels"].loc["GEO_1", "Inactive Voter_bins"])


# ---------------------------------------------------------------------------
# DEFAULT_BINS tests (would FAIL on pre-fix code)
# ---------------------------------------------------------------------------

class TestDefaultBins:
    """Verify DEFAULT_BINS dictionary has correct geography-bin mappings."""

    def test_default_bins_tract_is_7(self):
        """Tract must use 7 bins — the fix for D7."""
        assert DEFAULT_BINS["tract"] == 7

    def test_default_bins_county_is_5(self):
        """County uses 5 bins."""
        assert DEFAULT_BINS["county"] == 5

    def test_default_bins_state_is_5(self):
        """State uses 5 bins."""
        assert DEFAULT_BINS["state"] == 5

    def test_default_bins_tribal_is_5(self):
        """Tribal uses 5 bins."""
        assert DEFAULT_BINS["tribal"] == 5


# ---------------------------------------------------------------------------
# preflight_database tests
#
# Regression: a teammate ran the pipeline against a freshly-init'd DB without
# first running import_reference_data.py / sync_geographies.py. The pipeline
# silently logged "Indicator not found in database: <name>" per indicator and
# persisted nothing while reporting success. Preflight must refuse to start.
# ---------------------------------------------------------------------------

class TestPreflightDatabase:
    """Tests for preflight_database() — the pre-pull bootstrap check."""

    def _mock_db(self, ref_count, geo_counts):
        """
        Build a mock db whose Repository constructors yield mocks with .count()
        configured. ``geo_counts`` is a dict like {"county": 3222, "state": 0}.
        """
        from unittest.mock import patch, MagicMock

        ref_repo = MagicMock()
        ref_repo.count.return_value = ref_count
        geo_repo = MagicMock()
        geo_repo.count.side_effect = lambda level=None: geo_counts.get(level, 0)
        return ref_repo, geo_repo

    def _patch_repos(self, ref_repo, geo_repo):
        from unittest.mock import patch

        return (
            patch("scripts.run_full_pipeline.GeographyRepository", return_value=geo_repo),
            patch("scripts.run_full_pipeline.ReferenceIndicatorRepository", return_value=ref_repo),
        )

    def test_populated_db_proceeds_silently(self):
        """All counts > 0 → no exception, function returns None."""
        ref_repo, geo_repo = self._mock_db(ref_count=22, geo_counts={"county": 3222})
        p1, p2 = self._patch_repos(ref_repo, geo_repo)
        with p1, p2:
            assert preflight_database(geography="county", db=object()) is None

    def test_empty_reference_indicators_aborts(self):
        """Empty ref-table is the original incident — must abort with remediation."""
        ref_repo, geo_repo = self._mock_db(ref_count=0, geo_counts={"county": 3222})
        p1, p2 = self._patch_repos(ref_repo, geo_repo)
        with p1, p2:
            with pytest.raises(PipelinePreflightError) as exc:
                preflight_database(geography="county", db=object())
        msg = str(exc.value)
        assert "reference_indicators" in msg
        assert "import_reference_data.py" in msg
        # Must inherit SystemExit so the CLI exits with code 1, not a traceback.
        assert exc.value.code == 1

    def test_empty_geographies_for_target_level_aborts(self):
        """Pipeline targets 'state' but state geos are empty → abort."""
        ref_repo, geo_repo = self._mock_db(ref_count=22, geo_counts={"state": 0})
        p1, p2 = self._patch_repos(ref_repo, geo_repo)
        with p1, p2:
            with pytest.raises(PipelinePreflightError) as exc:
                preflight_database(geography="state", db=object())
        assert "level='state'" in str(exc.value)
        assert "sync_geographies.py --level state" in str(exc.value)

    def test_tract_pipeline_requires_county_geographies_too(self):
        """
        Tract D1 step imputes non-ACS indicators from parent county. If counties
        are absent, that imputation silently produces NaNs — preflight must
        catch this even when tract geographies themselves are populated.
        """
        ref_repo, geo_repo = self._mock_db(
            ref_count=22, geo_counts={"tract": 85396, "county": 0}
        )
        p1, p2 = self._patch_repos(ref_repo, geo_repo)
        with p1, p2:
            with pytest.raises(PipelinePreflightError) as exc:
                preflight_database(geography="tract", db=object())
        msg = str(exc.value)
        assert "county" in msg
        assert "required for tract D1 imputation" in msg

    def test_tract_pipeline_with_both_levels_populated_proceeds(self):
        ref_repo, geo_repo = self._mock_db(
            ref_count=22, geo_counts={"tract": 85396, "county": 3222}
        )
        p1, p2 = self._patch_repos(ref_repo, geo_repo)
        with p1, p2:
            assert preflight_database(geography="tract", db=object()) is None

    def test_multiple_failures_surface_all_in_one_message(self):
        """User shouldn't have to re-run to discover the second problem."""
        ref_repo, geo_repo = self._mock_db(ref_count=0, geo_counts={"county": 0})
        p1, p2 = self._patch_repos(ref_repo, geo_repo)
        with p1, p2:
            with pytest.raises(PipelinePreflightError) as exc:
                preflight_database(geography="county", db=object())
        msg = str(exc.value)
        assert "reference_indicators" in msg
        assert "level='county'" in msg
        assert "import_reference_data.py" in msg
        assert "sync_geographies.py --level county" in msg

    def test_error_message_points_to_doctor_script(self):
        """A user hitting one preflight failure should be nudged toward the broader install report."""
        ref_repo, geo_repo = self._mock_db(ref_count=0, geo_counts={"county": 3222})
        p1, p2 = self._patch_repos(ref_repo, geo_repo)
        with p1, p2:
            with pytest.raises(PipelinePreflightError) as exc:
                preflight_database(geography="county", db=object())
        assert "scripts/doctor.py" in str(exc.value)
        assert "--no-db" in str(exc.value)


# ---------------------------------------------------------------------------
# preflight_year_consistency tests
#
# Regression: a sponsor produced cria_results_county_2024.xlsx containing
# ACS 2023 data because their .env had ACS_YEAR=2023 and they ran with
# --year 2024. The --year arg only labels the output (filename, DB year
# column); the actual data pull is governed by settings.acs_year. Preflight
# must refuse the mismatch unless explicitly allowed.
# ---------------------------------------------------------------------------

class TestPreflightYearConsistency:
    """Tests for preflight_year_consistency() — the --year vs settings.acs_year guard."""

    def test_matching_year_proceeds_silently(self, monkeypatch):
        """--year equals settings.acs_year → no exception, returns None."""
        monkeypatch.setattr("scripts.run_full_pipeline.settings.acs_year", 2024)
        assert preflight_year_consistency(year=2024) is None

    def test_mismatch_aborts(self, monkeypatch):
        """The exact sponsor scenario: env says 2023, user passes --year 2024 → abort."""
        monkeypatch.setattr("scripts.run_full_pipeline.settings.acs_year", 2023)
        with pytest.raises(YearMismatchError) as exc:
            preflight_year_consistency(year=2024)
        msg = str(exc.value)
        # Both years must appear so the user knows which to fix
        assert "2024" in msg
        assert "2023" in msg
        # SystemExit subclass → CLI exits with code 1, no traceback
        assert exc.value.code == 1

    def test_mismatch_message_lists_three_remediations(self, monkeypatch):
        """User shouldn't have to guess how to resolve — message names all 3 paths."""
        monkeypatch.setattr("scripts.run_full_pipeline.settings.acs_year", 2023)
        with pytest.raises(YearMismatchError) as exc:
            preflight_year_consistency(year=2024)
        msg = str(exc.value)
        assert "--year 2023" in msg            # match the env
        assert "ACS_YEAR=2024" in msg          # change the env
        assert "--allow-year-mismatch" in msg  # opt-in override

    def test_mismatch_with_override_proceeds(self, monkeypatch):
        """--allow-year-mismatch lets the run continue (rare legitimate cases)."""
        monkeypatch.setattr("scripts.run_full_pipeline.settings.acs_year", 2023)
        # Should NOT raise
        assert preflight_year_consistency(year=2024, allow_mismatch=True) is None

    def test_override_logs_warning(self, monkeypatch, caplog):
        """The override is loud — silent allow would just reintroduce the original bug."""
        import logging
        monkeypatch.setattr("scripts.run_full_pipeline.settings.acs_year", 2023)
        with caplog.at_level(logging.WARNING, logger="cria"):
            preflight_year_consistency(year=2024, allow_mismatch=True)
        # The warning must mention both years so it's actionable in logs
        assert any("2024" in r.message and "2023" in r.message
                   for r in caplog.records if r.levelno >= logging.WARNING)
