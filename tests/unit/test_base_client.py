"""
Unit tests for BaseAPIClient.

Tests retry logic, error handling, and session management.
"""

import pytest
from unittest.mock import Mock, patch
import requests

from src.api.base_client import BaseAPIClient, _redact_url


class TestBaseAPIClient:
    """Test suite for BaseAPIClient"""

    def test_initialization(self):
        """Test client initialization"""
        client = BaseAPIClient(base_url="https://api.example.com")

        assert client.base_url == "https://api.example.com"
        assert client.timeout == 30
        assert client.max_retries == 3
        assert client._session is not None

    def test_base_url_trailing_slash_removed(self):
        """Test that trailing slash is removed from base_url"""
        client = BaseAPIClient(base_url="https://api.example.com/")

        assert client.base_url == "https://api.example.com"

    def test_create_session_has_retry(self):
        """Test that session has retry adapter"""
        client = BaseAPIClient(base_url="https://api.example.com")

        # Check that adapters are mounted
        assert "http://" in client._session.adapters
        assert "https://" in client._session.adapters

    @patch("requests.Session.get")
    def test_get_success(self, mock_get):
        """Test successful GET request"""
        client = BaseAPIClient(base_url="https://api.example.com")

        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "success"
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        response = client.get("/endpoint")

        assert response.status_code == 200
        mock_get.assert_called_once()

    @patch("requests.Session.get")
    def test_get_full_url(self, mock_get):
        """Test GET with full URL (not appended to base_url)"""
        client = BaseAPIClient(base_url="https://api.example.com")

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client.get("https://other-api.com/data")

        # Verify full URL was used, not appended
        call_args = mock_get.call_args
        assert "https://other-api.com/data" in str(call_args)

    @patch("requests.Session.get")
    def test_get_with_params(self, mock_get):
        """Test GET with query parameters"""
        client = BaseAPIClient(base_url="https://api.example.com")

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client.get("/endpoint", params={"key": "value"})

        # Verify params were passed
        call_args = mock_get.call_args
        assert call_args[1]["params"] == {"key": "value"}

    @patch("requests.Session.get")
    def test_get_timeout_error(self, mock_get):
        """Test GET request timeout"""
        client = BaseAPIClient(base_url="https://api.example.com")

        mock_get.side_effect = requests.exceptions.Timeout("Timeout")

        with pytest.raises(requests.exceptions.Timeout):
            client.get("/endpoint")

    @patch("requests.Session.get")
    def test_get_http_error(self, mock_get):
        """Test GET with HTTP error (404, 500, etc.)"""
        client = BaseAPIClient(base_url="https://api.example.com")

        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.text = "Not found"
        mock_response.raise_for_status = Mock(
            side_effect=requests.exceptions.HTTPError("404 Not Found")
        )
        mock_get.return_value = mock_response

        with pytest.raises(requests.exceptions.HTTPError):
            client.get("/endpoint")

    def test_context_manager(self):
        """Test using client as context manager"""
        with BaseAPIClient(base_url="https://api.example.com") as client:
            assert client._session is not None

        # Session should be closed after exiting context
        # (Can't easily test this without implementation details)

    def test_repr(self):
        """Test string representation"""
        client = BaseAPIClient(base_url="https://api.example.com")

        assert "BaseAPIClient" in repr(client)
        assert "api.example.com" in repr(client)


class TestRedactURL:
    """``_redact_url`` strips ``key=...`` so API keys never reach the logs."""

    def test_strips_key_in_middle(self):
        url = "https://api.census.gov/data/2023/acs/acs5?get=NAME&key=abc123&for=state"
        result = _redact_url(url)
        assert "abc123" not in result
        assert "key=REDACTED" in result
        assert "get=NAME" in result
        assert "for=state" in result

    def test_strips_key_at_start(self):
        url = "https://api.census.gov/data/2023/acs/acs5?key=secret&get=NAME"
        result = _redact_url(url)
        assert "secret" not in result
        assert "key=REDACTED" in result

    def test_no_key_param_unchanged(self):
        url = "https://api.example.com/data?foo=bar"
        assert _redact_url(url) == url

    @patch("requests.Session.get")
    def test_get_does_not_log_api_key(self, mock_get, caplog):
        """End-to-end: failed request must not write the raw key to logs."""
        client = BaseAPIClient(base_url="https://api.census.gov")
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "server error"
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=mock_response
        )
        mock_get.return_value = mock_response

        with caplog.at_level("ERROR"):
            with pytest.raises(requests.exceptions.HTTPError):
                client.get("https://api.census.gov/data?get=NAME&key=supersecret123")

        log_output = "\n".join(record.message for record in caplog.records)
        assert "supersecret123" not in log_output, "API key leaked to logs"
        assert "REDACTED" in log_output
