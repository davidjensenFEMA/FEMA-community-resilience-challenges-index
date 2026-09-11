"""
Unit tests for CBPClient.

Tests URL building, data fetching, and multi-NAICS merge logic.
Does NOT make real API calls (uses mocks).
"""

import pytest
import pandas as pd
import numpy as np
from unittest.mock import Mock, patch

from src.api.cbp_client import CBPClient


class TestCBPClient:
    """Tests for CBPClient initialization and URL building."""

    def test_initialization_defaults(self):
        """Test that client initializes with settings defaults."""
        client = CBPClient()

        assert client.base_url == "https://api.census.gov/data"
        assert client.api_key is not None
        assert client.cbp_year is not None
        assert client.naics_year is not None

    def test_initialization_custom_values(self):
        """Test client initialization with explicit values."""
        client = CBPClient(api_key="test_key", cbp_year=2022, naics_year=2022)

        assert client.api_key == "test_key"
        assert client.cbp_year == 2022
        assert client.naics_year == 2022

    def test_build_cbp_url_basic(self):
        """Test that build_cbp_url produces correct URL structure."""
        client = CBPClient(api_key="test_key", cbp_year=2020, naics_year=2017)

        url = client.build_cbp_url(8131)

        assert "api.census.gov/data/2020/cbp" in url
        assert "get=NAME,GEO_ID" in url
        assert "ESTAB" in url
        assert "county:*" in url
        assert "state:*" in url
        assert "key=test_key" in url

    def test_build_cbp_url_naics_in_query(self):
        """Test that NAICS year is interpolated into parameter names."""
        client = CBPClient(api_key="test_key", cbp_year=2020, naics_year=2017)

        url = client.build_cbp_url(622)

        assert "NAICS2017_LABEL" in url
        assert "NAICS2017=622" in url

    def test_repr(self):
        """Test string representation."""
        client = CBPClient(cbp_year=2020, naics_year=2017)

        result = repr(client)
        assert "CBPClient" in result
        assert "2020" in result
        assert "2017" in result


class TestFetchCBPData:
    """Tests for CBPClient.fetch_cbp_data method."""

    def _make_mock_response(self, data):
        """Helper to create a mock response with JSON text."""
        import json
        mock_response = Mock()
        mock_response.text = json.dumps(data)
        return mock_response

    @patch("src.api.cbp_client.BaseAPIClient.get")
    def test_basic_fetch(self, mock_get):
        """Test fetching CBP data returns a DataFrame."""
        client = CBPClient(api_key="test_key", cbp_year=2020, naics_year=2017)

        mock_get.return_value = self._make_mock_response([
            ["NAME", "GEO_ID", "NAICS2017_LABEL", "ESTAB", "NAICS2017", "state", "county"],
            ["Autauga County", "0500000US01001", "Religious orgs", "15", "8131", "01", "001"],
            ["Baldwin County", "0500000US01003", "Religious orgs", "30", "8131", "01", "003"],
        ])

        df = client.fetch_cbp_data(8131)

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2

    @patch("src.api.cbp_client.BaseAPIClient.get")
    def test_column_renamed(self, mock_get):
        """Test that ESTAB column is renamed to the NAICS code string."""
        client = CBPClient(api_key="test_key", cbp_year=2020, naics_year=2017)

        mock_get.return_value = self._make_mock_response([
            ["NAME", "GEO_ID", "NAICS2017_LABEL", "ESTAB", "NAICS2017", "state", "county"],
            ["Autauga County", "0500000US01001", "Religious orgs", "15", "8131", "01", "001"],
        ])

        df = client.fetch_cbp_data(8131)

        assert "8131" in df.columns
        assert "ESTAB" not in df.columns

    @patch("src.api.cbp_client.BaseAPIClient.get")
    def test_geo_id_as_index(self, mock_get):
        """Test that GEO_ID is set as the DataFrame index."""
        client = CBPClient(api_key="test_key", cbp_year=2020, naics_year=2017)

        mock_get.return_value = self._make_mock_response([
            ["NAME", "GEO_ID", "NAICS2017_LABEL", "ESTAB", "NAICS2017", "state", "county"],
            ["Autauga County", "0500000US01001", "Religious orgs", "15", "8131", "01", "001"],
            ["Baldwin County", "0500000US01003", "Religious orgs", "30", "8131", "01", "003"],
        ])

        df = client.fetch_cbp_data(8131)

        assert df.index.name == "GEO_ID"
        assert "0500000US01001" in df.index
        assert "0500000US01003" in df.index

    @patch("src.api.cbp_client.BaseAPIClient.get")
    def test_fill_missing_true(self, mock_get):
        """Test that NaN values are filled with 0 when fill_missing=True."""
        client = CBPClient(api_key="test_key", cbp_year=2020, naics_year=2017)

        mock_get.return_value = self._make_mock_response([
            ["NAME", "GEO_ID", "NAICS2017_LABEL", "ESTAB", "NAICS2017", "state", "county"],
            ["Autauga County", "0500000US01001", "Religious orgs", "15", "8131", "01", "001"],
            ["Baldwin County", "0500000US01003", "Religious orgs", "N", "8131", "01", "003"],
        ])

        df = client.fetch_cbp_data(8131, fill_missing=True)

        # "N" should become NaN via pd.to_numeric(errors="coerce"), then filled to 0
        assert df.loc["0500000US01003", "8131"] == 0

    @patch("src.api.cbp_client.BaseAPIClient.get")
    def test_fill_missing_false(self, mock_get):
        """Test that NaN values are preserved when fill_missing=False."""
        client = CBPClient(api_key="test_key", cbp_year=2020, naics_year=2017)

        mock_get.return_value = self._make_mock_response([
            ["NAME", "GEO_ID", "NAICS2017_LABEL", "ESTAB", "NAICS2017", "state", "county"],
            ["Autauga County", "0500000US01001", "Religious orgs", "15", "8131", "01", "001"],
            ["Baldwin County", "0500000US01003", "Religious orgs", "N", "8131", "01", "003"],
        ])

        df = client.fetch_cbp_data(8131, fill_missing=False)

        # "N" becomes NaN and should stay NaN
        assert pd.isna(df.loc["0500000US01003", "8131"])

    @patch("src.api.cbp_client.BaseAPIClient.get")
    def test_numeric_conversion(self, mock_get):
        """Test that string ESTAB values are converted to numeric."""
        client = CBPClient(api_key="test_key", cbp_year=2020, naics_year=2017)

        mock_get.return_value = self._make_mock_response([
            ["NAME", "GEO_ID", "NAICS2017_LABEL", "ESTAB", "NAICS2017", "state", "county"],
            ["Autauga County", "0500000US01001", "Religious orgs", "15", "8131", "01", "001"],
        ])

        df = client.fetch_cbp_data(8131)

        # Value should be numeric, not string
        assert df.loc["0500000US01001", "8131"] == 15
        assert pd.api.types.is_numeric_dtype(df["8131"])


class TestFetchMultipleNaics:
    """Tests for CBPClient.fetch_multiple_naics method."""

    def _make_mock_response(self, data):
        """Helper to create a mock response with JSON text."""
        import json
        mock_response = Mock()
        mock_response.text = json.dumps(data)
        return mock_response

    @patch("src.api.cbp_client.BaseAPIClient.get")
    def test_multiple_codes_merged(self, mock_get):
        """Test that multiple NAICS codes are fetched and merged via outer join."""
        client = CBPClient(api_key="test_key", cbp_year=2020, naics_year=2017)

        # First call returns NAICS 8131
        response1 = self._make_mock_response([
            ["NAME", "GEO_ID", "NAICS2017_LABEL", "ESTAB", "NAICS2017", "state", "county"],
            ["Autauga County", "0500000US01001", "Religious orgs", "15", "8131", "01", "001"],
            ["Baldwin County", "0500000US01003", "Religious orgs", "30", "8131", "01", "003"],
        ])

        # Second call returns NAICS 622
        response2 = self._make_mock_response([
            ["NAME", "GEO_ID", "NAICS2017_LABEL", "ESTAB", "NAICS2017", "state", "county"],
            ["Autauga County", "0500000US01001", "Hospitals", "3", "622", "01", "001"],
            ["Baldwin County", "0500000US01003", "Hospitals", "5", "622", "01", "003"],
        ])

        mock_get.side_effect = [response1, response2]

        df = client.fetch_multiple_naics([8131, 622])

        assert "8131" in df.columns
        assert "622" in df.columns
        assert len(df) == 2
        assert df.loc["0500000US01001", "8131"] == 15
        assert df.loc["0500000US01001", "622"] == 3

    @patch("src.api.cbp_client.BaseAPIClient.get")
    def test_one_code_fails_gracefully(self, mock_get):
        """Test that a failed NAICS fetch produces an empty DataFrame for that code."""
        client = CBPClient(api_key="test_key", cbp_year=2020, naics_year=2017)

        # First call succeeds
        response1 = self._make_mock_response([
            ["NAME", "GEO_ID", "NAICS2017_LABEL", "ESTAB", "NAICS2017", "state", "county"],
            ["Autauga County", "0500000US01001", "Religious orgs", "15", "8131", "01", "001"],
        ])

        # Second call raises an exception
        mock_get.side_effect = [response1, Exception("API error")]

        df = client.fetch_multiple_naics([8131, 622])

        assert "8131" in df.columns
        assert "622" in df.columns
        assert len(df) >= 1

    @patch("src.api.cbp_client.BaseAPIClient.get")
    def test_fill_missing_across_codes(self, mock_get):
        """Test that remaining NaN values are filled after merge when fill_missing=True."""
        client = CBPClient(api_key="test_key", cbp_year=2020, naics_year=2017)

        # First code has county A and B
        response1 = self._make_mock_response([
            ["NAME", "GEO_ID", "NAICS2017_LABEL", "ESTAB", "NAICS2017", "state", "county"],
            ["Autauga County", "0500000US01001", "Religious orgs", "15", "8131", "01", "001"],
            ["Baldwin County", "0500000US01003", "Religious orgs", "30", "8131", "01", "003"],
        ])

        # Second code only has county A (county B will be NaN after outer join)
        response2 = self._make_mock_response([
            ["NAME", "GEO_ID", "NAICS2017_LABEL", "ESTAB", "NAICS2017", "state", "county"],
            ["Autauga County", "0500000US01001", "Hospitals", "3", "622", "01", "001"],
        ])

        mock_get.side_effect = [response1, response2]

        df = client.fetch_multiple_naics([8131, 622], fill_missing=True)

        # County B's hospital count should be filled with 0 (not NaN)
        assert df.loc["0500000US01003", "622"] == 0
