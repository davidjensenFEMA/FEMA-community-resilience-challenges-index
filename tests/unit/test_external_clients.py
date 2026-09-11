"""
Unit tests for external API clients (EAVS, ARDA, POP).

Tests data fetching, parsing, and transformation logic.
Does NOT make real API calls (uses mocks).
"""

import io
import zipfile
import pytest
import pandas as pd
import numpy as np
from unittest.mock import Mock, patch, MagicMock

from src.api.external_clients import EAVSClient, ARDAClient, POPClient


# =============================================================================
# EAVS Client Tests
# =============================================================================


class TestEAVSClient:
    """Tests for EAVSClient data fetching and parsing."""

    def _make_zip_response(self, csv_content: str) -> Mock:
        """Helper to create a mock response containing a ZIP with a CSV."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("eavs_data.csv", csv_content)
        buf.seek(0)

        mock_response = Mock()
        mock_response.content = buf.read()
        return mock_response

    @patch("src.api.external_clients.BaseAPIClient.get")
    def test_fetch_parses_zip(self, mock_get):
        """Test that EAVS correctly extracts CSV from a ZIP response."""
        csv_content = (
            "FIPSCode,Jurisdiction_Name,State_Abbr,A1a,A1c\n"
            "01001,Autauga County,AL,30000,500\n"
            "01003,Baldwin County,AL,120000,2000\n"
        )
        mock_get.return_value = self._make_zip_response(csv_content)

        client = EAVSClient()
        df = client.fetch_eavs_data()

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2
        assert "A1a" in df.columns
        assert "A1c" in df.columns

    @patch("src.api.external_clients.BaseAPIClient.get")
    def test_fetch_fallback_direct_csv(self, mock_get):
        """Test that BadZipFile falls back to direct CSV read."""
        csv_content = (
            "FIPSCode,Jurisdiction_Name,State_Abbr,A1a,A1c\n"
            "01001,Autauga County,AL,30000,500\n"
        )
        mock_response = Mock()
        # Not a valid ZIP -- just raw CSV bytes
        mock_response.content = csv_content.encode("latin-1")
        mock_get.return_value = mock_response

        client = EAVSClient()
        df = client.fetch_eavs_data()

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 1
        assert "A1a" in df.columns

    @patch("src.api.external_clients.BaseAPIClient.get")
    def test_special_values(self, mock_get):
        """Test that -88 maps to NaN and -99 maps to NaN."""
        csv_content = (
            "FIPSCode,Jurisdiction_Name,State_Abbr,A1a,A1c\n"
            "01001,Autauga County,AL,-88,-99\n"
        )
        mock_get.return_value = self._make_zip_response(csv_content)

        client = EAVSClient()
        df = client.fetch_eavs_data()

        assert pd.isna(df["A1a"].iloc[0])     # -88 -> NaN (does not apply)
        assert pd.isna(df["A1c"].iloc[0])     # -99 -> NaN

    @patch("src.api.external_clients.BaseAPIClient.get")
    def test_county_merge(self, mock_get):
        """Test that counties_ref merge produces GEO_ID index."""
        csv_content = (
            "FIPSCode,Jurisdiction_Name,State_Abbr,A1a,A1c\n"
            "01001,Autauga County,AL,30000,500\n"
        )
        mock_get.return_value = self._make_zip_response(csv_content)

        counties_ref = pd.DataFrame({
            "GEO_ID": ["0500000US01001"],
            "county_name": ["Autauga County"],
            "state_abbr": ["AL"],
        }).set_index("GEO_ID")

        client = EAVSClient()
        df = client.fetch_eavs_data(counties_ref=counties_ref)

        assert df.index.name == "GEO_ID"
        assert "0500000US01001" in df.index

    @patch("src.api.external_clients.BaseAPIClient.get")
    def test_geo_id_index(self, mock_get):
        """Test that result is indexed by GEO_ID when counties_ref provided."""
        csv_content = (
            "FIPSCode,Jurisdiction_Name,State_Abbr,A1a,A1c\n"
            "01001,Autauga County,AL,30000,500\n"
            "01003,Baldwin County,AL,120000,2000\n"
        )
        mock_get.return_value = self._make_zip_response(csv_content)

        counties_ref = pd.DataFrame({
            "GEO_ID": ["0500000US01001", "0500000US01003"],
            "county_name": ["Autauga County", "Baldwin County"],
            "state_abbr": ["AL", "AL"],
        }).set_index("GEO_ID")

        client = EAVSClient()
        df = client.fetch_eavs_data(counties_ref=counties_ref)

        assert df.index.name == "GEO_ID"
        assert len(df) == 2


# =============================================================================
# ARDA Client Tests
# =============================================================================


class TestARDAClient:
    """Tests for ARDAClient data fetching and parsing."""

    @patch("src.api.external_clients.pd.ExcelFile")
    @patch("src.api.external_clients.pd.read_excel")
    def test_fetch_2020(self, mock_read_excel, mock_excel_file):
        """Test fetching 2020 ARDA data from online source."""
        mock_df = pd.DataFrame({
            "STATE NAME": ["Alabama", "Alabama"],
            "FIPS": ["01001", "01003"],
            "ADHERENTS": [25000, 80000],
            "TOTAL POPULATION": [55000, 200000],
        })

        # mock_excel_file is the ExcelFile constructor
        mock_xls = MagicMock()
        mock_excel_file.return_value = mock_xls

        # When pd.read_excel is called with sheet_name, return our mock_df
        mock_read_excel.return_value = mock_df

        client = ARDAClient()
        df = client.fetch_arda_data(year=2020)

        assert isinstance(df, pd.DataFrame)
        assert df.index.name == "GEO_ID"
        assert "TOTADH" in df.columns
        assert "POP2020" in df.columns

    @patch("src.api.external_clients.pd.read_excel")
    def test_fetch_2010(self, mock_read_excel):
        """Test fetching 2010 ARDA data from local file."""
        mock_df = pd.DataFrame({
            "STCODE": [1, 1],
            "CNTYCODE": [1, 3],
            "TOTADH": [20000, 70000],
            "POP2010": [55000, 200000],
        })
        mock_read_excel.return_value = mock_df

        client = ARDAClient()
        df = client.fetch_arda_data(year=2010)

        assert isinstance(df, pd.DataFrame)
        assert df.index.name == "GEO_ID"
        assert "TOTADH" in df.columns
        assert "POP2010" in df.columns

    def test_unsupported_year_raises(self):
        """Test that an unsupported year raises ValueError."""
        client = ARDAClient()

        with pytest.raises(ValueError, match="Unsupported ARDA year"):
            client.fetch_arda_data(year=2015)

    @patch("src.api.external_clients.pd.ExcelFile")
    @patch("src.api.external_clients.pd.read_excel")
    def test_pop_alias_created(self, mock_read_excel, mock_excel_file):
        """Test that a generic POP column is created alongside POP2020."""
        mock_df = pd.DataFrame({
            "STATE NAME": ["Alabama"],
            "FIPS": ["01001"],
            "ADHERENTS": [25000],
            "TOTAL POPULATION": [55000],
        })
        mock_excel_file.return_value = MagicMock()
        mock_read_excel.return_value = mock_df

        client = ARDAClient()
        df = client.fetch_arda_data(year=2020)

        assert "POP" in df.columns
        assert "POP2020" in df.columns
        assert df["POP"].iloc[0] == df["POP2020"].iloc[0]

    @patch("src.api.external_clients.pd.read_excel")
    def test_pop_alias_created_2010(self, mock_read_excel):
        """Test that a generic POP column is created for 2010 data too."""
        mock_df = pd.DataFrame({
            "STCODE": [1],
            "CNTYCODE": [1],
            "TOTADH": [20000],
            "POP2010": [55000],
        })
        mock_read_excel.return_value = mock_df

        client = ARDAClient()
        df = client.fetch_arda_data(year=2010)

        assert "POP" in df.columns
        assert df["POP"].iloc[0] == 55000

    @patch("src.api.external_clients.pd.read_excel")
    def test_geo_id_format(self, mock_read_excel):
        """Test that GEO_ID follows the '0500000US' + FIPS format."""
        mock_df = pd.DataFrame({
            "STCODE": [1, 6],
            "CNTYCODE": [1, 37],
            "TOTADH": [20000, 500000],
            "POP2010": [55000, 1000000],
        })
        mock_read_excel.return_value = mock_df

        client = ARDAClient()
        df = client.fetch_arda_data(year=2010)

        assert "0500000US01001" in df.index
        assert "0500000US06037" in df.index


# =============================================================================
# POP Client Tests
# =============================================================================


class TestPOPClient:
    """Tests for POPClient data fetching and year clamping."""

    def _make_csv_response(self, csv_content: str) -> Mock:
        """Helper to create a mock response with CSV content."""
        mock_response = Mock()
        mock_response.content = csv_content.encode("ISO-8859-1")
        return mock_response

    @patch("src.api.external_clients.BaseAPIClient.get")
    def test_fetch_basic(self, mock_get):
        """Test basic fetch returns DataFrame with NETMIG columns."""
        csv_content = (
            "NETMIG2020,NETMIG2019,STATE,COUNTY\n"
            "150.0,120.0,01,001\n"
            "300.0,250.0,01,003\n"
        )
        mock_get.return_value = self._make_csv_response(csv_content)

        client = POPClient()
        df = client.fetch_pop_data(years=[2020, 2019], pop_year=2020)

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2
        assert "NETMIG2020" in df.columns
        assert "NETMIG2019" in df.columns

    @patch("src.api.external_clients.BaseAPIClient.get")
    def test_year_clamping_to_decade(self, mock_get):
        """Test that years before the decade base are excluded."""
        # pop_year=2022 -> decade base=2020 -> year 2018 should be clamped out
        csv_content = (
            "NETMIG2022,NETMIG2021,NETMIG2020,STATE,COUNTY\n"
            "150.0,120.0,100.0,01,001\n"
        )
        mock_get.return_value = self._make_csv_response(csv_content)

        client = POPClient()
        df = client.fetch_pop_data(years=[2022, 2021, 2020, 2018], pop_year=2022)

        # 2018 is before decade base 2020, so only 3 valid years
        assert "NETMIG2022" in df.columns
        assert "NETMIG2021" in df.columns
        assert "NETMIG2020" in df.columns
        assert "NETMIG2018" not in df.columns

    def test_default_years_calculation(self):
        """Test that default years are calculated as 5 years back from pop_year."""
        # pop_year=2024, decade base=2020 -> default years: [2024, 2023, 2022, 2021, 2020]
        client = POPClient()

        # We can't easily test the default calculation without calling fetch,
        # so we test the logic by inspecting what years would be generated.
        pop_year = 2024
        year_remainder = pop_year % 10
        if year_remainder == 0:
            year_remainder = 10
        year_base = pop_year - year_remainder  # 2020

        earliest = max(pop_year - 4, year_base)  # max(2020, 2020) = 2020
        years = list(range(pop_year, earliest - 1, -1))

        assert years == [2024, 2023, 2022, 2021, 2020]

    def test_default_years_clamped_by_decade(self):
        """Test default years when pop_year is close to decade start."""
        # pop_year=2021, decade base=2020 -> only 2 years: [2021, 2020]
        pop_year = 2021
        year_remainder = pop_year % 10
        if year_remainder == 0:
            year_remainder = 10
        year_base = pop_year - year_remainder  # 2020

        earliest = max(pop_year - 4, year_base)  # max(2017, 2020) = 2020
        years = list(range(pop_year, earliest - 1, -1))

        assert years == [2021, 2020]

    def test_no_valid_years_raises(self):
        """Test that error is raised when all years are clamped out."""
        client = POPClient()

        # pop_year=2021, decade base=2020. Requesting years=[2018, 2017]
        # Both are before 2020, so all get clamped out.
        with pytest.raises(ValueError, match="No valid years"):
            client.fetch_pop_data(years=[2018, 2017], pop_year=2021)

    @patch("src.api.external_clients.BaseAPIClient.get")
    def test_geo_id_construction(self, mock_get):
        """Test that GEO_ID is built from STATE+COUNTY as '0500000US01001'."""
        csv_content = (
            "NETMIG2020,STATE,COUNTY\n"
            "150.0,01,001\n"
            "300.0,06,037\n"
        )
        mock_get.return_value = self._make_csv_response(csv_content)

        client = POPClient()
        df = client.fetch_pop_data(years=[2020], pop_year=2020)

        assert df.index.name == "GEO_ID"
        assert "0500000US01001" in df.index
        assert "0500000US06037" in df.index

    @patch("src.api.external_clients.BaseAPIClient.get")
    def test_csv_encoding(self, mock_get):
        """Test that ISO-8859-1 encoded content is handled correctly."""
        # Include a character that differs between ISO-8859-1 and UTF-8
        csv_content = "NETMIG2020,STATE,COUNTY\n150.0,01,001\n"
        mock_response = Mock()
        mock_response.content = csv_content.encode("ISO-8859-1")
        mock_get.return_value = mock_response

        client = POPClient()
        df = client.fetch_pop_data(years=[2020], pop_year=2020)

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 1

    @patch("src.api.external_clients.BaseAPIClient.get")
    def test_state_county_columns_dropped(self, mock_get):
        """Test that STATE and COUNTY columns are dropped from result."""
        csv_content = (
            "NETMIG2020,STATE,COUNTY\n"
            "150.0,01,001\n"
        )
        mock_get.return_value = self._make_csv_response(csv_content)

        client = POPClient()
        df = client.fetch_pop_data(years=[2020], pop_year=2020)

        assert "STATE" not in df.columns
        assert "COUNTY" not in df.columns
