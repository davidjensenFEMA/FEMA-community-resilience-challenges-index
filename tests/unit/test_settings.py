"""
Unit tests for Settings (pydantic-settings model).
"""

import pytest
from pydantic import ValidationError


class TestSettings:
    """Tests for the Settings class."""

    def _make_settings(self, **overrides):
        """Build a Settings instance with env vars cleared and explicit values."""
        from src.config.settings import Settings

        # Provide all required defaults so no .env file is needed
        defaults = {
            "census_api_key": "",
            "acs_year": 2021,
            "cbp_year": 2020,
            "naics_year": 2017,
            "pop_year": 2020,
            "asarb_year": 2020,
            "acs_labels_year": 2020,
            "database_url": "sqlite:///./cria.db",
            "test_database_url": "sqlite:///./cria_test.db",
            "data_dir": "data",
            "output_dir": "data/output",
            "logs_dir": "logs",
            "default_geography": "county",
            "debug": True,
            "log_level": "INFO",
            "pipeline_timeout_minutes": 60,
            "test_mode": False,
            "test_sample_size": 100,
        }
        defaults.update(overrides)
        return Settings(**defaults)

    def test_default_values(self):
        """All defaults should match expected values."""
        s = self._make_settings()

        assert s.acs_year == 2021
        assert s.cbp_year == 2020
        assert s.naics_year == 2017
        assert s.pop_year == 2020
        assert s.asarb_year == 2020
        assert s.acs_labels_year == 2020
        assert s.database_url == "sqlite:///./cria.db"
        assert s.default_geography == "county"
        assert s.log_level == "INFO"
        assert s.pipeline_timeout_minutes == 60
        assert s.test_mode is False
        assert s.test_sample_size == 100

    def test_year_validation_too_low(self):
        """ACS year below 2010 should be rejected."""
        with pytest.raises(ValidationError):
            self._make_settings(acs_year=2005)

    def test_year_validation_too_high(self):
        """ACS year above 2030 should be rejected."""
        with pytest.raises(ValidationError):
            self._make_settings(acs_year=2035)

    def test_years_dict_property(self):
        """years_dict should return all 6 year entries."""
        s = self._make_settings()
        yd = s.years_dict

        assert yd == {
            "acs": 2021,
            "cbp": 2020,
            "naics": 2017,
            "pop": 2020,
            "asarb": 2020,
            "acs_labels": 2020,
        }

    def test_is_docker_property_sqlite(self):
        """is_docker should be False for a SQLite URL."""
        s = self._make_settings(database_url="sqlite:///./cria.db")
        assert s.is_docker is False

    def test_is_docker_property_postgres(self):
        """is_docker should be True when 'postgres' appears in the URL."""
        s = self._make_settings(
            database_url="postgresql://user:pass@postgres:5432/db"
        )
        assert s.is_docker is True

    def test_geography_validation_valid(self):
        """Valid geography values should be accepted."""
        for geo in ("state", "county", "tract", "tribal"):
            s = self._make_settings(default_geography=geo)
            assert s.default_geography == geo

    def test_geography_validation_invalid(self):
        """Invalid geography values should be rejected."""
        with pytest.raises(ValidationError):
            self._make_settings(default_geography="zipcode")

    def test_log_level_validation_valid(self):
        """All standard log levels should be accepted."""
        for level in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            s = self._make_settings(log_level=level)
            assert s.log_level == level

    def test_log_level_validation_invalid(self):
        """Invalid log level should be rejected."""
        with pytest.raises(ValidationError):
            self._make_settings(log_level="VERBOSE")

    def test_pipeline_timeout_too_low(self):
        """Pipeline timeout below 5 should be rejected."""
        with pytest.raises(ValidationError):
            self._make_settings(pipeline_timeout_minutes=2)

    def test_pipeline_timeout_too_high(self):
        """Pipeline timeout above 1440 should be rejected."""
        with pytest.raises(ValidationError):
            self._make_settings(pipeline_timeout_minutes=2000)
