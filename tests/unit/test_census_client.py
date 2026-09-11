"""
Unit tests for CensusAPIClient.

Tests URL building, data fetching logic, and error handling.
Does NOT make real API calls (uses mocks).
"""

from datetime import datetime
import io

import pytest
import pandas as pd
from unittest.mock import Mock, patch, MagicMock

from src.api.census_client import (
    CENSUS_API_KEY_LENGTH,
    CensusAPIClient,
    CensusAPIError,
    PLACEHOLDER_API_KEY,
    _mask_api_key,
    _normalize_api_key,
    _parse_census_response,
    _redact_api_key,
    confirm_suspect_api_key,
    validate_census_api_key_format,
)


class TestCensusAPIClient:
    """Test suite for CensusAPIClient"""

    def test_initialization(self):
        """Test client initialization"""
        client = CensusAPIClient(api_key="test_key")

        assert client.base_url == "https://api.census.gov/data"
        assert client.api_key == "test_key"
        assert client.year is not None

    def test_build_acs_url_county(self):
        """Test building ACS URL for county geography"""
        client = CensusAPIClient(api_key="test_key", year=2021)

        url = client.build_acs_url(
            columns=["B01001_001E", "B17001_002E"],
            geography="county",
        )

        # Check URL components
        assert "api.census.gov/data/2021/acs/acs5" in url
        assert "B01001_001E" in url
        assert "B17001_002E" in url
        assert "county:*" in url
        assert "key=test_key" in url

    def test_build_acs_url_state(self):
        """Test building ACS URL for state geography"""
        client = CensusAPIClient(api_key="test_key", year=2021)

        url = client.build_acs_url(
            columns=["B01001_001E"],
            geography="state",
        )

        assert "state:*" in url
        assert "county" not in url

    def test_build_acs_url_subject_table(self):
        """Test building URL for subject table (S-tables)"""
        client = CensusAPIClient(api_key="test_key", year=2021)

        url = client.build_acs_url(
            columns=["S1701_C01_001E"],
            geography="county",
        )

        # Subject tables use different endpoint
        assert "acs5/subject" in url

    def test_build_acs_url_data_profile(self):
        """Test building URL for data profile (DP-tables)"""
        client = CensusAPIClient(api_key="test_key", year=2021)

        url = client.build_acs_url(
            columns=["DP02_0001E"],
            geography="county",
        )

        assert "acs5/profile" in url

    def test_build_acs_url_invalid_geography(self):
        """Test that invalid geography raises ValueError"""
        client = CensusAPIClient(api_key="test_key")

        with pytest.raises(ValueError, match="Unsupported geography"):
            client.build_acs_url(
                columns=["B01001_001E"],
                geography="invalid_geo",
            )

    def test_build_acs_url_no_columns(self):
        """Test that empty columns raises ValueError"""
        client = CensusAPIClient(api_key="test_key")

        with pytest.raises(ValueError, match="Must provide at least one column"):
            client.build_acs_url(columns=[], geography="county")

    @patch("src.api.census_client.BaseAPIClient.get")
    def test_fetch_acs_data_basic(self, mock_get):
        """Test fetching ACS data (mocked response)"""
        client = CensusAPIClient(api_key="test_key")

        # Mock API response
        mock_response = Mock()
        mock_response.text = """[
            ["NAME", "GEO_ID", "B01001_001E", "state", "county"],
            ["Autauga County, Alabama", "0500000US01001", "55000", "01", "001"],
            ["Baldwin County, Alabama", "0500000US01003", "200000", "01", "003"]
        ]"""
        mock_get.return_value = mock_response

        # Fetch data
        df = client.fetch_acs_data(["B01001_001E"], geography="county")

        # Verify result
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2
        assert "B01001_001E" in df.columns
        assert df.index.name == "GEO_ID"
        assert "0500000US01001" in df.index

    @patch("src.api.census_client.BaseAPIClient.get")
    def test_fetch_acs_data_cleans_missing(self, mock_get):
        """Test that Census missing codes (-666666666) are replaced with NaN"""
        client = CensusAPIClient(api_key="test_key")

        # Mock response with missing data
        mock_response = Mock()
        mock_response.text = """[
            ["NAME", "GEO_ID", "B01001_001E"],
            ["County 1", "0500000US01001", "55000"],
            ["County 2", "0500000US01003", "-666666666"]
        ]"""
        mock_get.return_value = mock_response

        df = client.fetch_acs_data(["B01001_001E"], geography="county")

        # Check that missing code was replaced
        assert pd.isna(df.loc["0500000US01003", "B01001_001E"])
        assert df.loc["0500000US01001", "B01001_001E"] == 55000

    def test_repr(self):
        """Test string representation"""
        client = CensusAPIClient(api_key="test_key", year=2021)

        assert "CensusAPIClient" in repr(client)
        assert "2021" in repr(client)


class TestCensusAPIErrorHandling:
    """
    Tests for the non-JSON-on-HTTP-200 failure mode.

    The Census API returns plain-text or HTML error bodies (with HTTP 200)
    for unknown variables, unknown datasets, and bad keys. These tests pin
    down that the resulting error surfaces the actual server message instead
    of a cryptic ``Expecting value: line 2 column 1`` JSONDecodeError.
    """

    def _mock_response(self, *, status: int, body: str, content_type: str) -> Mock:
        response = Mock()
        response.status_code = status
        response.text = body
        response.headers = {"content-type": content_type}
        return response

    def test_parse_response_returns_json_for_valid_body(self):
        response = self._mock_response(
            status=200,
            body='[["NAME","GEO_ID"],["x","0500000US01001"]]',
            content_type="application/json",
        )

        data = _parse_census_response(response, ["B01001_001E"], "https://api.census.gov/data/...")

        assert data == [["NAME", "GEO_ID"], ["x", "0500000US01001"]]

    def test_parse_response_raises_on_plain_text_error(self):
        """The Census API's typical 'unknown variable' response: HTTP 200 + text/html."""
        body = "error: error: unknown variable 'DP04_0014E'"
        response = self._mock_response(status=200, body=body, content_type="text/html")

        with pytest.raises(CensusAPIError) as excinfo:
            _parse_census_response(
                response,
                ["DP04_0014E", "DP04_0001E"],
                "https://api.census.gov/data/2024/acs/acs5/profile?get=...&key=secret123",
            )

        msg = str(excinfo.value)
        assert "DP04_0014E" in msg, "variable list must surface in the error"
        assert "unknown variable" in msg, "actual Census error body must surface"
        assert "HTTP 200" in msg
        assert "text/html" in msg
        assert "key=REDACTED" in msg, "API key must be stripped from logged URL"
        assert "secret123" not in msg

    def test_parse_response_raises_on_html_error_page(self):
        body = "<html><body>404 Not Found - dataset 2030/acs/acs5</body></html>"
        response = self._mock_response(status=200, body=body, content_type="text/html")

        with pytest.raises(CensusAPIError) as excinfo:
            _parse_census_response(response, ["B01001_001E"], "https://api.census.gov/...")

        assert "404" in str(excinfo.value)

    def test_parse_response_truncates_long_body(self):
        """Body excerpt should not flood logs."""
        body = "x" * 5000
        response = self._mock_response(status=200, body=body, content_type="text/plain")

        with pytest.raises(CensusAPIError) as excinfo:
            _parse_census_response(response, ["B01001_001E"], "https://api.census.gov/...")

        assert len(str(excinfo.value)) < 1500

    def test_redact_api_key_strips_key_param(self):
        url = "https://api.census.gov/data/2023/acs/acs5?get=NAME&key=abc123def"
        assert _redact_api_key(url) == "https://api.census.gov/data/2023/acs/acs5?get=NAME&key=REDACTED"

    def test_redact_api_key_handles_key_at_start(self):
        url = "https://api.census.gov/data/2023/acs/acs5?key=abc&get=NAME"
        assert "key=REDACTED" in _redact_api_key(url)
        assert "abc" not in _redact_api_key(url)


class TestCensusAPIClientInit:
    """Fail-fast configuration validation."""

    def test_empty_api_key_raises(self):
        with pytest.raises(ValueError, match="Census API key is missing"):
            CensusAPIClient(api_key="")

    def test_placeholder_api_key_raises(self):
        with pytest.raises(ValueError, match="placeholder"):
            CensusAPIClient(api_key=PLACEHOLDER_API_KEY)

    def test_future_acs_year_warns_but_does_not_raise(self, caplog):
        future_year = datetime.now().year + 1

        with caplog.at_level("WARNING"):
            client = CensusAPIClient(api_key="test_key", year=future_year)

        assert client.year == future_year
        assert any(
            "later than the most recent ACS 5-year release" in record.message
            for record in caplog.records
        ), "expected warning about pre-release ACS year"

    def test_current_minus_one_acs_year_does_not_warn(self, caplog):
        latest = datetime.now().year - 1

        with caplog.at_level("WARNING"):
            CensusAPIClient(api_key="test_key", year=latest)

        assert not any(
            "later than the most recent ACS 5-year release" in record.message
            for record in caplog.records
        )


class TestFetchACSDataErrorPropagation:
    """End-to-end: a non-JSON 200 from the mocked transport must raise CensusAPIError."""

    @patch("src.api.census_client.BaseAPIClient.get")
    def test_fetch_acs_data_raises_census_api_error_on_text_body(self, mock_get):
        client = CensusAPIClient(api_key="test_key", year=2023)

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "error: error: unknown variable 'DP04_0014E'"
        mock_response.headers = {"content-type": "text/html"}
        mock_get.return_value = mock_response

        with pytest.raises(CensusAPIError) as excinfo:
            client.fetch_acs_data(["DP04_0014E"], geography="county")

        assert "DP04_0014E" in str(excinfo.value)
        assert "unknown variable" in str(excinfo.value)


VALID_HEX_KEY = "a" * CENSUS_API_KEY_LENGTH  # 40 'a's = valid hex of correct length


class TestNormalizeAPIKey:
    """``_normalize_api_key`` strips ``.env`` paste artifacts."""

    def test_clean_key_unchanged(self):
        cleaned, notes = _normalize_api_key(VALID_HEX_KEY)
        assert cleaned == VALID_HEX_KEY
        assert notes == []

    def test_strips_surrounding_whitespace(self):
        cleaned, notes = _normalize_api_key(f"  {VALID_HEX_KEY}\n")
        assert cleaned == VALID_HEX_KEY
        assert any("whitespace" in n for n in notes)

    def test_strips_double_quotes(self):
        cleaned, notes = _normalize_api_key(f'"{VALID_HEX_KEY}"')
        assert cleaned == VALID_HEX_KEY
        assert any("quotes" in n for n in notes)

    def test_strips_single_quotes(self):
        cleaned, notes = _normalize_api_key(f"'{VALID_HEX_KEY}'")
        assert cleaned == VALID_HEX_KEY
        assert any("quotes" in n for n in notes)

    def test_removes_embedded_whitespace(self):
        wrapped = VALID_HEX_KEY[:20] + "\n" + VALID_HEX_KEY[20:]
        cleaned, notes = _normalize_api_key(wrapped)
        assert cleaned == VALID_HEX_KEY
        assert any("embedded whitespace" in n for n in notes)

    def test_combined_artifacts(self):
        # Quotes + surrounding whitespace + line wrap, all at once.
        raw = f'  "{VALID_HEX_KEY[:20]}\n{VALID_HEX_KEY[20:]}"  '
        cleaned, notes = _normalize_api_key(raw)
        assert cleaned == VALID_HEX_KEY
        assert len(notes) >= 2

    def test_unmatched_quote_not_stripped(self):
        """Only strip quotes when both sides match."""
        cleaned, _ = _normalize_api_key(f'"{VALID_HEX_KEY}')
        assert cleaned.startswith('"'), "leading-only quote must be preserved"


class TestValidateCensusAPIKeyFormat:
    """``validate_census_api_key_format`` returns ``None`` or a reason string."""

    def test_valid_hex_key_returns_none(self):
        assert validate_census_api_key_format(VALID_HEX_KEY) is None

    def test_valid_uppercase_hex_returns_none(self):
        assert validate_census_api_key_format("A" * CENSUS_API_KEY_LENGTH) is None

    def test_valid_mixed_hex_returns_none(self):
        key = "0123456789abcdef" * 2 + "deadbeef"  # 40 chars
        assert len(key) == 40
        assert validate_census_api_key_format(key) is None

    def test_empty_key(self):
        assert validate_census_api_key_format("") == "empty"

    def test_too_short(self):
        reason = validate_census_api_key_format("a" * 30)
        assert reason is not None
        assert "30" in reason
        assert "40" in reason

    def test_too_long(self):
        reason = validate_census_api_key_format("a" * 50)
        assert reason is not None
        assert "50" in reason

    def test_non_hex_characters(self):
        # Right length, contains 'g' and 'z' (non-hex).
        key = "g" + "a" * 38 + "z"
        reason = validate_census_api_key_format(key)
        assert reason is not None
        assert "non-hexadecimal" in reason
        # The reason should mention the bad chars (so the user can find them).
        assert "g" in reason or "z" in reason


class TestMaskAPIKey:
    """``_mask_api_key`` keeps display safe but recognizable."""

    def test_full_length_key_shows_first_and_last_four(self):
        masked = _mask_api_key(VALID_HEX_KEY)
        assert masked.startswith("aaaa")
        assert masked.endswith("aaaa")
        assert "*" in masked
        assert VALID_HEX_KEY not in masked  # full key never appears

    def test_short_key_fully_masked(self):
        assert _mask_api_key("abc") == "***"
        assert _mask_api_key("abcdefgh") == "********"


class TestConfirmSuspectAPIKey:
    """TTY-gated CLI prompt with ``--yes`` and non-interactive fallbacks."""

    def test_valid_key_returns_true_silently(self, capsys):
        stream = io.StringIO()
        result = confirm_suspect_api_key(key=VALID_HEX_KEY, stream=stream)
        assert result is True
        assert stream.getvalue() == "", "valid key must not prompt or print"

    def test_assume_yes_continues_without_prompt(self):
        stream = io.StringIO()
        with patch("sys.stdin.isatty", return_value=True):
            result = confirm_suspect_api_key(
                key="bad", assume_yes=True, stream=stream
            )
        assert result is True
        out = stream.getvalue()
        assert "may not be valid" in out
        assert "--yes" in out

    def test_non_tty_continues_with_warning(self):
        stream = io.StringIO()
        with patch("sys.stdin.isatty", return_value=False):
            result = confirm_suspect_api_key(key="bad", stream=stream)
        assert result is True
        out = stream.getvalue()
        assert "Non-interactive" in out

    def test_tty_prompt_yes_continues(self):
        stream = io.StringIO()
        with patch("sys.stdin.isatty", return_value=True), \
             patch("builtins.input", return_value="y"):
            result = confirm_suspect_api_key(key="bad", stream=stream)
        assert result is True

    def test_tty_prompt_no_aborts(self):
        stream = io.StringIO()
        with patch("sys.stdin.isatty", return_value=True), \
             patch("builtins.input", return_value="n"):
            result = confirm_suspect_api_key(key="bad", stream=stream)
        assert result is False

    def test_tty_prompt_default_aborts(self):
        """Empty answer = no, by convention (capital N in prompt)."""
        stream = io.StringIO()
        with patch("sys.stdin.isatty", return_value=True), \
             patch("builtins.input", return_value=""):
            result = confirm_suspect_api_key(key="bad", stream=stream)
        assert result is False

    def test_eof_aborts(self):
        """Ctrl-D / piped-then-closed stdin must not crash."""
        stream = io.StringIO()
        with patch("sys.stdin.isatty", return_value=True), \
             patch("builtins.input", side_effect=EOFError):
            result = confirm_suspect_api_key(key="bad", stream=stream)
        assert result is False

    def test_prompt_does_not_leak_full_key(self):
        suspicious_key = "sk-supersecret123456789suspicious"  # not 40 hex
        stream = io.StringIO()
        with patch("sys.stdin.isatty", return_value=False):
            confirm_suspect_api_key(key=suspicious_key, stream=stream)
        out = stream.getvalue()
        assert "supersecret123" not in out, "raw key body must be masked"


class TestInitNormalizesAndWarns:
    """``CensusAPIClient.__init__`` strips paste artifacts and warns on suspect keys."""

    def test_init_strips_quotes_and_warns(self, caplog):
        with caplog.at_level("WARNING"):
            client = CensusAPIClient(api_key=f'"{VALID_HEX_KEY}"')
        assert client.api_key == VALID_HEX_KEY
        assert any("quotes" in r.message for r in caplog.records)

    def test_init_warns_on_short_key(self, caplog):
        with caplog.at_level("WARNING"):
            client = CensusAPIClient(api_key="abc123")
        assert client.api_key == "abc123"  # accepted, just warned
        assert any("does not match expected format" in r.message for r in caplog.records)

    def test_init_does_not_warn_on_valid_key(self, caplog):
        with caplog.at_level("WARNING"):
            CensusAPIClient(api_key=VALID_HEX_KEY)
        # No format warning. (Year warning may fire if test machine clock is in
        # the future relative to ACS_YEAR; we filter to format-related lines.)
        format_warnings = [
            r for r in caplog.records
            if "expected format" in r.message or "quotes" in r.message
        ]
        assert format_warnings == []


@pytest.mark.integration
@pytest.mark.requires_api
class TestCensusAPIClientIntegration:
    """
    Integration tests that make real API calls.

    These tests are skipped by default. Run with:
        pytest -m integration
    """

    def test_real_api_call(self):
        """Test real API call (requires valid API key in .env)"""
        client = CensusAPIClient()

        # Fetch just one column for one state
        df = client.fetch_acs_data(
            ["B01001_001E"],  # Total population
            geography="county",
        )

        # Basic sanity checks
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0
        assert "B01001_001E" in df.columns
        assert df.index.name == "GEO_ID"
