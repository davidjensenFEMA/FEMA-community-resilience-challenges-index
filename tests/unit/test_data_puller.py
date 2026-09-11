"""
Unit tests for DataPuller class.

Tests orchestration logic with all API clients mocked.
"""

import pytest
import numpy as np
import pandas as pd
from unittest.mock import patch, MagicMock


class TestDataPullerInit:
    """Tests for DataPuller initialization."""

    @patch("src.core.data_puller.DataPuller._load_geographies", return_value={})
    @patch("src.core.data_puller.DataPuller._load_years", return_value={"acs": 2021})
    @patch("src.core.data_puller.DataPuller._load_reference", return_value=pd.DataFrame())
    @patch("src.core.data_puller.POPClient")
    @patch("src.core.data_puller.ARDAClient")
    @patch("src.core.data_puller.EAVSClient")
    @patch("src.core.data_puller.CBPClient")
    @patch("src.core.data_puller.CensusAPIClient")
    def test_initialization_sets_geography(
        self, mock_census, mock_cbp, mock_eavs, mock_arda, mock_pop,
        mock_ref, mock_years, mock_geo,
    ):
        """Test that geography is stored on the instance."""
        from src.core.data_puller import DataPuller

        puller = DataPuller(geography="tract")
        assert puller.geography == "tract"

    @patch("src.core.data_puller.DataPuller._load_geographies", return_value={})
    @patch("src.core.data_puller.DataPuller._load_years", return_value={"acs": 2021})
    @patch("src.core.data_puller.DataPuller._load_reference", return_value=pd.DataFrame())
    @patch("src.core.data_puller.POPClient")
    @patch("src.core.data_puller.ARDAClient")
    @patch("src.core.data_puller.EAVSClient")
    @patch("src.core.data_puller.CBPClient")
    @patch("src.core.data_puller.CensusAPIClient")
    def test_initialization_creates_clients(
        self, mock_census, mock_cbp, mock_eavs, mock_arda, mock_pop,
        mock_ref, mock_years, mock_geo,
    ):
        """Test that all 5 API clients are instantiated."""
        from src.core.data_puller import DataPuller

        puller = DataPuller(geography="county")

        mock_census.assert_called_once()
        mock_cbp.assert_called_once()
        mock_eavs.assert_called_once()
        mock_arda.assert_called_once()
        mock_pop.assert_called_once()


# ---------------------------------------------------------------------------
# Helper to build a DataPuller with everything mocked
# ---------------------------------------------------------------------------

def _make_puller(reference_df, years=None, geographies=None, geography="county"):
    """Create a DataPuller with mocked internals for testing dispatch logic."""
    from src.core.data_puller import DataPuller

    with (
        patch.object(DataPuller, "_load_reference", return_value=reference_df),
        patch.object(DataPuller, "_load_years", return_value=years or {"acs": 2021, "pop": 2020, "asarb": 2020}),
        patch.object(DataPuller, "_load_geographies", return_value=geographies or {}),
        patch("src.core.data_puller.CensusAPIClient"),
        patch("src.core.data_puller.CBPClient"),
        patch("src.core.data_puller.EAVSClient"),
        patch("src.core.data_puller.ARDAClient"),
        patch("src.core.data_puller.POPClient"),
    ):
        puller = DataPuller(geography=geography)
    return puller


class TestPullAllData:
    """Tests for pull_all_data dispatch and merge logic."""

    def test_dispatches_acs_for_acs_source(self):
        """ACS source rows should call _pull_acs_indicator."""
        ref = pd.DataFrame({
            "Indicator": ["Poverty"],
            "Source": ["ACS"],
            "numerator": ["B17001_002E"],
            "denominator": ["B17001_001E"],
            "Order_2023": [1],
        })
        puller = _make_puller(ref)

        acs_df = pd.DataFrame({"B17001_002E": [100]}, index=["GEO1"])
        puller._pull_acs_indicator = MagicMock(return_value=acs_df)
        puller._post_process_data = MagicMock(side_effect=lambda d: d)

        result = puller.pull_all_data()
        puller._pull_acs_indicator.assert_called_once()
        assert "B17001_002E" in result.columns

    def test_dispatches_cbp_for_cbp_source(self):
        """CBP source rows should call _pull_cbp_indicator."""
        ref = pd.DataFrame({
            "Indicator": ["Hospitals"],
            "Source": ["CBP"],
            "numerator": ["622110"],
            "denominator": ["S0101_C01_001E"],
            "Order_2023": [1],
        })
        puller = _make_puller(ref)

        cbp_df = pd.DataFrame({"622110": [5]}, index=["GEO1"])
        puller._pull_cbp_indicator = MagicMock(return_value=cbp_df)
        puller._post_process_data = MagicMock(side_effect=lambda d: d)

        result = puller.pull_all_data()
        puller._pull_cbp_indicator.assert_called_once()
        assert "622110" in result.columns

    def test_dispatches_eavs_for_eavs_source(self):
        """EAVS source rows should call _pull_eavs_indicator."""
        ref = pd.DataFrame({
            "Indicator": ["Inactive Voter"],
            "Source": ["EAVS"],
            "numerator": ["A1c"],
            "denominator": ["A1a"],
            "Order_2023": [1],
        })
        puller = _make_puller(ref)

        eavs_df = pd.DataFrame({"A1c": [500]}, index=["GEO1"])
        puller._pull_eavs_indicator = MagicMock(return_value=eavs_df)
        puller._post_process_data = MagicMock(side_effect=lambda d: d)

        result = puller.pull_all_data()
        puller._pull_eavs_indicator.assert_called_once()

    def test_dispatches_arda_for_arda_source(self):
        """ARDA source rows should call _pull_arda_indicator."""
        ref = pd.DataFrame({
            "Indicator": ["Religion"],
            "Source": ["ARDA"],
            "numerator": ["TOTADH"],
            "denominator": ["POP"],
            "Order_2023": [1],
        })
        puller = _make_puller(ref)

        arda_df = pd.DataFrame({"TOTADH": [1000]}, index=["GEO1"])
        puller._pull_arda_indicator = MagicMock(return_value=arda_df)
        puller._post_process_data = MagicMock(side_effect=lambda d: d)

        result = puller.pull_all_data()
        puller._pull_arda_indicator.assert_called_once()

    def test_dispatches_pop_for_pop_source(self):
        """POP source rows should call _pull_pop_indicator."""
        ref = pd.DataFrame({
            "Indicator": ["Population Change"],
            "Source": ["POP"],
            "numerator": ["NETMIG"],
            "denominator": ["S0101_C01_001E"],
            "Order_2023": [1],
        })
        puller = _make_puller(ref)

        pop_df = pd.DataFrame({"NETMIG2020": [50]}, index=["GEO1"])
        puller._pull_pop_indicator = MagicMock(return_value=pop_df)
        puller._post_process_data = MagicMock(side_effect=lambda d: d)

        result = puller.pull_all_data()
        puller._pull_pop_indicator.assert_called_once()

    def test_unknown_source_skipped(self, caplog):
        """Unknown source values should log a warning and continue."""
        ref = pd.DataFrame({
            "Indicator": ["Mystery"],
            "Source": ["UNKNOWN_SRC"],
            "numerator": ["X"],
            "denominator": ["Y"],
            "Order_2023": [1],
        })
        puller = _make_puller(ref)
        puller._post_process_data = MagicMock(side_effect=lambda d: d)

        import logging
        with caplog.at_level(logging.WARNING, logger="src.core.data_puller"):
            result = puller.pull_all_data()

        assert any("unknown source" in m.lower() for m in caplog.messages)

    def test_exception_in_pull_continues(self):
        """If one indicator pull raises, the others should still be pulled."""
        ref = pd.DataFrame({
            "Indicator": ["Poverty", "GINI"],
            "Source": ["ACS", "ACS"],
            "numerator": ["B17001_002E", "B19083_001E"],
            "denominator": ["B17001_001E", "1"],
            "Order_2023": [1, 2],
        })
        puller = _make_puller(ref)

        call_count = 0

        def side_effect(idx, row):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Simulated API failure")
            return pd.DataFrame({"B19083_001E": [0.45]}, index=["GEO1"])

        puller._pull_acs_indicator = MagicMock(side_effect=side_effect)
        puller._post_process_data = MagicMock(side_effect=lambda d: d)

        result = puller.pull_all_data()

        # Both indicators attempted (call_count == 2)
        assert call_count == 2
        # Second indicator data is present
        assert "B19083_001E" in result.columns

    def test_duplicate_columns_dropped(self):
        """When merging multiple pulls, duplicate columns should be dropped."""
        ref = pd.DataFrame({
            "Indicator": ["Poverty", "GINI"],
            "Source": ["ACS", "ACS"],
            "numerator": ["B17001_002E", "B19083_001E"],
            "denominator": ["B17001_001E", "1"],
            "Order_2023": [1, 2],
        })
        puller = _make_puller(ref)

        # Both pulls return the shared column SHARED_COL
        df1 = pd.DataFrame({"B17001_002E": [100], "SHARED_COL": [1]}, index=["GEO1"])
        df2 = pd.DataFrame({"B19083_001E": [0.45], "SHARED_COL": [999]}, index=["GEO1"])

        call_num = 0

        def side_effect(idx, row):
            nonlocal call_num
            call_num += 1
            return df1 if call_num == 1 else df2

        puller._pull_acs_indicator = MagicMock(side_effect=side_effect)
        puller._post_process_data = MagicMock(side_effect=lambda d: d)

        result = puller.pull_all_data()

        # SHARED_COL should appear exactly once (from the first pull)
        assert list(result.columns).count("SHARED_COL") == 1
        # Value should be from the first pull (duplicates dropped from second)
        assert result.loc["GEO1", "SHARED_COL"] == 1


class TestPostProcessData:
    """Tests for _post_process_data."""

    def test_invalid_index_dropped(self):
        """Rows with NaN index values should be removed."""
        ref = pd.DataFrame({
            "Indicator": ["Poverty"],
            "Source": ["ACS"],
            "numerator": ["B17001_002E"],
            "denominator": ["B17001_001E"],
            "Order_2023": [1],
        })
        puller = _make_puller(ref)

        data = pd.DataFrame(
            {"B17001_002E": [100, 200, 300]},
            index=["GEO1", np.nan, "GEO3"],
        )

        result = puller._post_process_data(data)
        assert len(result) == 2
        assert "GEO1" in result.index
        assert "GEO3" in result.index

    def test_cbp_missing_filled_zero(self):
        """CBP columns with NaN should be filled with 0."""
        ref = pd.DataFrame({
            "Indicator": ["Hospitals"],
            "Source": ["CBP"],
            "numerator": [622110],
            "denominator": ["S0101_C01_001E"],
            "Order_2023": [1],
        })
        puller = _make_puller(ref)

        data = pd.DataFrame(
            {"622110": [5.0, np.nan, 3.0]},
            index=["GEO1", "GEO2", "GEO3"],
        )

        result = puller._post_process_data(data)
        assert result.loc["GEO2", "622110"] == 0

    def test_pr_limited_english_nan(self):
        """Puerto Rico (state==72) Limited English values should be set to NaN."""
        ref = pd.DataFrame({
            "Indicator": ["Limited English"],
            "Source": ["ACS"],
            "numerator": ["S1602_C03_001E"],
            "denominator": ["S1602_C01_001E"],
            "Order_2023": [1],
        })
        geo_ref = pd.DataFrame(
            {"state": [1, 72, 72]},
            index=["GEO_AL", "GEO_PR1", "GEO_PR2"],
        )
        puller = _make_puller(
            ref, geographies={"county": geo_ref}, geography="county"
        )

        data = pd.DataFrame(
            {"S1602_C03_001E": [0.05, 0.80, 0.75]},
            index=["GEO_AL", "GEO_PR1", "GEO_PR2"],
        )

        result = puller._post_process_data(data)

        # Alabama value untouched
        assert result.loc["GEO_AL", "S1602_C03_001E"] == 0.05
        # Puerto Rico values set to NaN
        assert pd.isna(result.loc["GEO_PR1", "S1602_C03_001E"])
        assert pd.isna(result.loc["GEO_PR2", "S1602_C03_001E"])

    def test_pr_exclusion_geography_gate(self):
        """PR Limited English NaN logic should NOT apply for tribal geography."""
        ref = pd.DataFrame({
            "Indicator": ["Limited English"],
            "Source": ["ACS"],
            "numerator": ["S1602_C03_001E"],
            "denominator": ["S1602_C01_001E"],
            "Order_2023": [1],
        })
        geo_ref = pd.DataFrame(
            {"state": [72]},
            index=["GEO_PR1"],
        )
        puller = _make_puller(
            ref, geographies={"tribal": geo_ref}, geography="tribal"
        )

        data = pd.DataFrame(
            {"S1602_C03_001E": [0.80]},
            index=["GEO_PR1"],
        )

        result = puller._post_process_data(data)

        # tribal geography should NOT trigger PR exclusion
        assert result.loc["GEO_PR1", "S1602_C03_001E"] == 0.80


class TestLoadGeographiesParquetEngineMissing:
    """
    Regression: a missing parquet engine (pyarrow / fastparquet) used to be
    swallowed as a generic warning, falling back to the Census-API geography
    fetcher which strips columns (state_abbr, county_name, ...) — corrupting
    downstream EAVS/CBP joins and producing thousands of NaN-indexed rows.
    """

    def test_import_error_on_parquet_read_raises_with_remediation(self, tmp_path, monkeypatch):
        from types import SimpleNamespace
        from src.core import data_puller as dp_mod

        # Build a parquet_dir with all 4 expected files present (so the loader
        # actually attempts a read instead of falling through on missing files).
        geo_dir = tmp_path / "geographies"
        geo_dir.mkdir()
        for level in ["state", "county", "tract", "tribal"]:
            (geo_dir / f"{level}.parquet").write_bytes(b"placeholder")

        # Substitute the whole `paths` object (paths.data is a property).
        monkeypatch.setattr(dp_mod, "paths", SimpleNamespace(data=tmp_path))

        # Force pd.read_parquet to raise ImportError as if pyarrow is missing.
        def _raise_import(*args, **kwargs):
            raise ImportError(
                "Unable to find a usable engine; tried using: 'pyarrow', 'fastparquet'."
            )

        monkeypatch.setattr(dp_mod.pd, "read_parquet", _raise_import)

        # Bypass __init__ — exercise _load_geographies in isolation.
        puller = dp_mod.DataPuller.__new__(dp_mod.DataPuller)

        with pytest.raises(RuntimeError) as excinfo:
            puller._load_geographies()

        msg = str(excinfo.value)
        assert "parquet engine" in msg
        assert "poetry install" in msg
        assert "pyarrow" in msg

    def test_non_import_exception_still_warns_and_falls_through(self, tmp_path, monkeypatch, caplog):
        """Other read failures (corrupt file, etc.) must NOT raise — preserve fallback path."""
        import logging
        from types import SimpleNamespace
        from src.core import data_puller as dp_mod

        geo_dir = tmp_path / "geographies"
        geo_dir.mkdir()
        # Only state.parquet exists — the others are absent, so the per-level
        # `if pq.exists()` short-circuits cleanly without needing fallback mocks.
        (geo_dir / "state.parquet").write_bytes(b"corrupt")

        monkeypatch.setattr(dp_mod, "paths", SimpleNamespace(data=tmp_path))

        def _raise_value(*args, **kwargs):
            raise ValueError("file is corrupt")

        monkeypatch.setattr(dp_mod.pd, "read_parquet", _raise_value)

        # Mock Census fallback so the test doesn't try to hit the network when
        # not all 4 levels load (1 out of 4 succeeds → falls through to API).
        puller = dp_mod.DataPuller.__new__(dp_mod.DataPuller)
        puller.census = MagicMock()
        puller.census.get_geographies.return_value = pd.DataFrame()

        with caplog.at_level(logging.WARNING, logger=dp_mod.__name__):
            puller._load_geographies()

        assert any("Failed to load" in rec.message for rec in caplog.records), (
            f"Expected 'Failed to load' warning, got: "
            f"{[(r.levelname, r.message) for r in caplog.records]}"
        )


# ---------------------------------------------------------------------------
# Drop-log message: dropped/kept counts + INFO/WARNING by threshold.
# ---------------------------------------------------------------------------

class TestPostProcessDropLog:
    """
    The drop-log line was once a bare WARNING that read as alarming data loss
    even when the filter was doing its job. Replacement: report dropped + kept,
    name the cause (outer-merge artifact), escalate to WARNING only above 60%.
    """

    def _make_ref(self):
        return pd.DataFrame({
            "Indicator": ["Poverty"],
            "Source": ["ACS"],
            "numerator": ["B17001_002E"],
            "denominator": ["B17001_001E"],
            "Order_2023": [1],
        })

    def test_no_drops_emits_no_log_line(self, caplog):
        """Zero NaN-indexed rows → no drop-log line at all."""
        import logging
        puller = _make_puller(self._make_ref())
        data = pd.DataFrame(
            {"B17001_002E": [100, 200]},
            index=["GEO1", "GEO2"],
        )
        with caplog.at_level(logging.INFO, logger="src.core.data_puller"):
            result = puller._post_process_data(data)
        # No "Cleaning merge artifacts" line when nothing was dropped.
        assert not any("Cleaning merge artifacts" in m for m in caplog.messages)
        assert len(result) == 2

    @pytest.mark.parametrize("n_kept,n_drop,expected_level", [
        # Below 60% — informational. 50% (3-of-6) is the typical county case.
        (3, 3, "INFO"),
        # Just under threshold — still INFO.
        (4, 5, "INFO"),  # 5/9 = 55.6%
        # Above 60% — escalate to WARNING (genuine regression signal).
        (3, 7, "WARNING"),  # 7/10 = 70%
        (1, 9, "WARNING"),  # 9/10 = 90%
    ])
    def test_threshold_chooses_log_level(self, caplog, n_kept, n_drop, expected_level):
        """Drop fraction at/below 60% logs INFO; above 60% logs WARNING."""
        import logging
        puller = _make_puller(self._make_ref())
        # Build a frame with n_kept valid indices + n_drop NaN indices.
        index = [f"GEO{i}" for i in range(n_kept)] + [np.nan] * n_drop
        data = pd.DataFrame(
            {"B17001_002E": list(range(n_kept + n_drop))},
            index=index,
        )
        with caplog.at_level(logging.INFO, logger="src.core.data_puller"):
            puller._post_process_data(data)

        drop_records = [r for r in caplog.records if "Cleaning merge artifacts" in r.message]
        assert len(drop_records) == 1, (
            f"Expected exactly one drop-log line, got: {[r.message for r in drop_records]}"
        )
        assert drop_records[0].levelname == expected_level

    def test_message_reports_kept_dropped_and_cause(self, caplog):
        """Message must name dropped count, kept count, percentage, and the cause."""
        import logging
        puller = _make_puller(self._make_ref())
        index = ["GEO1", "GEO2", np.nan, np.nan]
        data = pd.DataFrame(
            {"B17001_002E": [1, 2, 3, 4]},
            index=index,
        )
        with caplog.at_level(logging.INFO, logger="src.core.data_puller"):
            puller._post_process_data(data)

        drop_msg = next(m for m in caplog.messages if "Cleaning merge artifacts" in m)
        # Counts present, cause named.
        assert "dropped 2" in drop_msg
        assert "keeping 2" in drop_msg
        assert "50.0%" in drop_msg
        assert "Outer-merge artifact" in drop_msg


# ---------------------------------------------------------------------------
# DataPuller.save_to_database — defense-in-depth fail-fast.
# ---------------------------------------------------------------------------

class TestSaveToDatabaseFailFast:
    """
    Preflight in run_full_pipeline.py catches empty-table cases at startup,
    but save_to_database() is also called from notebooks and ad-hoc scripts
    that bypass preflight. Doctrine: TOTAL miss → raise (setup error);
    PARTIAL miss (single missing indicator) → warn-and-continue (data issue).
    """

    def _ref(self, indicators):
        return pd.DataFrame({
            "Indicator": indicators,
            "Source": ["ACS"] * len(indicators),
            "numerator": ["B17001_002E"] * len(indicators),
            "denominator": ["B17001_001E"] * len(indicators),
            "Order_2023": list(range(1, len(indicators) + 1)),
        })

    def _data(self, geo_ids):
        return pd.DataFrame(
            {"B17001_002E": list(range(len(geo_ids)))},
            index=geo_ids,
        )

    def _patch_repos(self, ref_get_by_name, geo_id_map):
        """Patch all three repository constructors in src.core.data_puller."""
        ref_repo = MagicMock()
        ref_repo.get_by_name.side_effect = ref_get_by_name
        geo_repo = MagicMock()
        geo_repo.get_geo_id_map.return_value = geo_id_map
        source_repo = MagicMock()
        source_repo.bulk_create.return_value = 0
        return (
            patch("src.core.data_puller.ReferenceIndicatorRepository", return_value=ref_repo),
            patch("src.core.data_puller.GeographyRepository", return_value=geo_repo),
            patch("src.core.data_puller.SourceDataRepository", return_value=source_repo),
        )

    def test_empty_indicator_map_raises(self):
        """Every reference indicator missing from DB → RuntimeError."""
        ref = self._ref(["Poverty", "GINI"])
        puller = _make_puller(ref)
        data = self._data(["GEO1", "GEO2"])
        # All lookups return None → indicator_map ends up empty.
        p1, p2, p3 = self._patch_repos(
            ref_get_by_name=lambda name: None,
            geo_id_map={"GEO1": 1, "GEO2": 2},
        )
        with p1, p2, p3:
            with pytest.raises(RuntimeError) as exc:
                puller.save_to_database(data, year=2021, db=MagicMock())
        msg = str(exc.value)
        assert "indicator_map is empty" in msg
        assert "import_reference_data.py" in msg
        assert "source_data" in msg  # names the affected table

    def test_empty_geo_id_map_raises(self):
        """Geographies table empty for this level → RuntimeError."""
        ref = self._ref(["Poverty"])
        puller = _make_puller(ref)
        data = self._data(["GEO1", "GEO2"])
        # Indicator lookup succeeds; geo_id_map is empty.
        ind = MagicMock()
        ind.id = 7
        p1, p2, p3 = self._patch_repos(
            ref_get_by_name=lambda name: ind,
            geo_id_map={},
        )
        with p1, p2, p3:
            with pytest.raises(RuntimeError) as exc:
                puller.save_to_database(data, year=2021, db=MagicMock())
        msg = str(exc.value)
        assert "geo_id_map is empty" in msg
        assert "sync_geographies.py" in msg
        assert "level='county'" in msg

    def test_partial_indicator_miss_does_not_raise(self, caplog):
        """A SINGLE missing indicator must still warn-and-continue (not raise)."""
        import logging
        ref = self._ref(["Poverty", "GINI"])
        puller = _make_puller(ref)
        data = self._data(["GEO1"])

        ind = MagicMock()
        ind.id = 7

        def lookup(name):
            # Poverty resolves, GINI doesn't → indicator_map non-empty.
            return ind if name == "Poverty" else None

        p1, p2, p3 = self._patch_repos(
            ref_get_by_name=lookup,
            geo_id_map={"GEO1": 1},
        )
        with p1, p2, p3:
            with caplog.at_level(logging.WARNING, logger="src.core.data_puller"):
                # Must NOT raise.
                puller.save_to_database(data, year=2021, db=MagicMock())

        # Per-indicator warning preserved.
        assert any("GINI" in m for m in caplog.messages)
