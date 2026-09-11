"""
Base API client with retry logic and error handling.

All API clients should inherit from BaseAPIClient to get
consistent retry behavior, timeout handling, and logging.
"""

from typing import Optional, Dict, Any
import re
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import logging

logger = logging.getLogger(__name__)


def _redact_url(url: str) -> str:
    """Strip ``key=...`` from a URL so it is safe to write to logs."""
    return re.sub(r"([?&])key=[^&]*", r"\1key=REDACTED", url)


class BaseAPIClient:
    """
    Base class for all API clients with retry logic.

    Provides:
    - Automatic retries with exponential backoff
    - Timeout handling
    - Error logging
    - Session management

    Example:
        class MyAPIClient(BaseAPIClient):
            def __init__(self):
                super().__init__(base_url="https://api.example.com")

            def fetch_data(self, endpoint: str) -> dict:
                response = self.get(endpoint)
                return response.json()
    """

    def __init__(
        self,
        base_url: str,
        timeout: int = 30,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
    ):
        """
        Initialize base API client.

        Args:
            base_url: Base URL for API (e.g., "https://api.census.gov/data")
            timeout: Request timeout in seconds (default: 30)
            max_retries: Maximum number of retries (default: 3)
            backoff_factor: Backoff factor for retries (default: 0.5)
                           Wait time = {backoff_factor} * (2 ** retry_count)
        """
        self.base_url = base_url.rstrip("/")  # Remove trailing slash
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self._session = self._create_session()

    def _create_session(self) -> requests.Session:
        """
        Create requests session with retry logic.

        Returns:
            Configured requests.Session with retry adapter
        """
        session = requests.Session()

        # Configure retry strategy
        retry = Retry(
            total=self.max_retries,
            backoff_factor=self.backoff_factor,
            status_forcelist=[500, 502, 503, 504],  # Retry on server errors
            allowed_methods=["HEAD", "GET", "OPTIONS"],  # Safe methods only
        )

        # Mount adapter with retry strategy
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        return session

    def get(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> requests.Response:
        """
        Make GET request with error handling.

        Args:
            endpoint: API endpoint (will be appended to base_url)
            params: Query parameters
            **kwargs: Additional arguments to pass to requests.get()

        Returns:
            Response object

        Raises:
            requests.exceptions.RequestException: On request failure
        """
        # Build full URL
        if endpoint.startswith("http"):
            url = endpoint  # Full URL provided
        else:
            url = f"{self.base_url}/{endpoint.lstrip('/')}"

        # Set default timeout if not provided
        if "timeout" not in kwargs:
            kwargs["timeout"] = self.timeout

        # Log request (URL redacted to keep API keys out of logs)
        safe_url = _redact_url(url)
        logger.debug(f"GET {safe_url}")
        if params:
            logger.debug(f"  Params: {params}")

        try:
            response = self._session.get(url, params=params, **kwargs)
            response.raise_for_status()  # Raise exception for 4xx/5xx status codes

            logger.debug(f"  Status: {response.status_code}")
            return response

        except requests.exceptions.Timeout as e:
            logger.error(f"Request timeout: {safe_url}")
            raise

        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error: {safe_url}")
            raise

        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error {response.status_code}: {safe_url}")
            logger.error(f"  Response: {response.text[:200]}")
            raise

        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {safe_url}, Error: {e}")
            raise

    def post(
        self,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> requests.Response:
        """
        Make POST request with error handling.

        Args:
            endpoint: API endpoint (will be appended to base_url)
            data: Form data
            json: JSON data
            **kwargs: Additional arguments to pass to requests.post()

        Returns:
            Response object

        Raises:
            requests.exceptions.RequestException: On request failure
        """
        # Build full URL
        if endpoint.startswith("http"):
            url = endpoint
        else:
            url = f"{self.base_url}/{endpoint.lstrip('/')}"

        # Set default timeout
        if "timeout" not in kwargs:
            kwargs["timeout"] = self.timeout

        safe_url = _redact_url(url)
        logger.debug(f"POST {safe_url}")

        try:
            response = self._session.post(url, data=data, json=json, **kwargs)
            response.raise_for_status()

            logger.debug(f"  Status: {response.status_code}")
            return response

        except requests.exceptions.RequestException as e:
            logger.error(f"POST request failed: {safe_url}, Error: {e}")
            raise

    def close(self):
        """Close the session."""
        self._session.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - close session."""
        self.close()

    def __repr__(self) -> str:
        """String representation."""
        return f"{self.__class__.__name__}(base_url={self.base_url})"
