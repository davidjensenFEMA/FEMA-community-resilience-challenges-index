"""
Census Bureau API client for ACS (American Community Survey) data.

Handles:
- ACS 5-year estimates (detailed tables, subject tables, data profiles)
- Geography levels: state, county, tract, tribal
- Column/variable fetching
- Data labeling and cleaning
"""

from datetime import datetime
from typing import List, Optional, Tuple, Dict
import json
import re
import sys
import pandas as pd
import numpy as np
import logging
import requests

from src.api.base_client import BaseAPIClient
from src.config.settings import settings

logger = logging.getLogger(__name__)


PLACEHOLDER_API_KEY = "your_census_api_key_here"

# Census API keys are 40 lowercase-hex characters. Documented at
# https://api.census.gov/data/key_signup.html. The format has been stable
# for years; if Census ever changes it, the validator will produce a soft
# warning rather than block.
CENSUS_API_KEY_LENGTH = 40
_HEX_CHARS = frozenset("0123456789abcdefABCDEF")


def _normalize_api_key(raw: str) -> Tuple[str, List[str]]:
    """
    Strip common ``.env`` paste artifacts from a key and report what changed.

    pydantic-settings preserves surrounding quotes and whitespace literally,
    so ``CENSUS_API_KEY="abc..."`` in ``.env`` becomes the value ``"abc..."``
    (with quotes) at runtime. Users almost never want that.

    Returns:
        ``(cleaned_key, notes)`` where ``notes`` describes any modification
        applied (empty list if the input was already clean).
    """
    notes: List[str] = []
    cleaned = raw

    # Surrounding whitespace.
    if cleaned != cleaned.strip():
        cleaned = cleaned.strip()
        notes.append("stripped surrounding whitespace")

    # Surrounding quote characters.
    for quote in ('"', "'"):
        if len(cleaned) >= 2 and cleaned.startswith(quote) and cleaned.endswith(quote):
            cleaned = cleaned[1:-1]
            notes.append(f"stripped surrounding {quote!r} quotes")
            break

    # Whitespace inside the key (common paste error: line wrap).
    if any(c.isspace() for c in cleaned):
        cleaned = "".join(c for c in cleaned if not c.isspace())
        notes.append("removed embedded whitespace")

    return cleaned, notes


def validate_census_api_key_format(key: str) -> Optional[str]:
    """
    Heuristic format check for a Census API key.

    Returns:
        ``None`` if the key looks like a Census API key, otherwise a short
        human-readable description of the suspected problem (e.g., ``"length
        36 (expected 40 hexadecimal characters)"``). Callers decide whether
        to warn, prompt, or ignore — this function never raises.

    Notes:
        Census API keys are 40 lowercase-hex characters. This is a heuristic;
        Census could in principle change its key format. A non-``None``
        return is not proof the key is bad — only that it does not look
        like a typical Census key.
    """
    if not key:
        return "empty"
    if len(key) != CENSUS_API_KEY_LENGTH:
        return f"length {len(key)} (expected {CENSUS_API_KEY_LENGTH} hexadecimal characters)"
    bad_chars = sorted({c for c in key if c not in _HEX_CHARS})
    if bad_chars:
        sample = "".join(bad_chars[:5])
        return f"contains non-hexadecimal characters ({sample!r}); Census keys are 0-9 and a-f"
    return None


def _mask_api_key(key: str) -> str:
    """Format a key for display: keep first/last 4 characters, mask the middle."""
    if len(key) <= 8:
        return "*" * len(key)
    return f"{key[:4]}{'*' * (len(key) - 8)}{key[-4:]}"


def confirm_suspect_api_key(
    key: Optional[str] = None,
    *,
    assume_yes: bool = False,
    stream=None,
) -> bool:
    """
    CLI preflight: prompt the user to continue when the configured Census
    API key does not look right.

    Designed to be called from CLI entry points (``run_full_pipeline.py``,
    ``sync_geographies.py``) before any API request is issued.

    Behavior:
        - If the key passes ``validate_census_api_key_format``: returns ``True``
          silently.
        - If the key looks suspect AND ``assume_yes`` is set OR stdin is not
          a TTY (CI, Docker, batch run): logs a warning, returns ``True``.
        - If the key looks suspect AND we have an interactive TTY: prompts
          the user. Returns ``True`` on ``y``/``yes``, ``False`` otherwise.

    Args:
        key: Key to validate (defaults to ``settings.census_api_key``).
        assume_yes: Skip the prompt and return ``True`` (for ``--yes`` flags).
        stream: Output stream for the prompt (defaults to ``sys.stderr``);
                used by tests to capture output.
    """
    if key is None:
        key = settings.census_api_key
    if stream is None:
        stream = sys.stderr

    reason = validate_census_api_key_format(key)
    if reason is None:
        return True

    masked = _mask_api_key(key)
    msg = (
        f"\nCENSUS_API_KEY in your environment may not be valid:\n"
        f"  Got:      {masked} (reason: {reason})\n"
        f"  Expected: 40 hexadecimal characters\n"
        f"  Source:   .env or environment variable\n"
        f"\nThis may still work if Census changed key formats, but is "
        f"more often a paste error or the wrong .env file.\n"
    )
    print(msg, file=stream)
    logger.warning(f"Suspect CENSUS_API_KEY format: {reason}")

    if assume_yes:
        print("Continuing because --yes was passed.", file=stream)
        return True
    if not sys.stdin.isatty():
        print(
            "Non-interactive session detected; continuing. Pass --yes to "
            "suppress this prompt explicitly.",
            file=stream,
        )
        return True

    try:
        answer = input("Continue anyway? [y/N]: ").strip().lower()
    except EOFError:
        return False
    return answer in ("y", "yes")


class CensusAPIError(RuntimeError):
    """
    Raised when the Census API returns a non-JSON response on HTTP 200.

    The Census API does not always use HTTP error codes for problems like
    unknown variables, unknown datasets, or invalid keys. Instead it returns
    HTTP 200 with a plain-text or HTML error body. The default ``json.loads``
    in that case fails with a cryptic ``Expecting value: line 2 column 1``
    error and discards the actual server message.

    This exception preserves the URL (with the API key redacted), HTTP
    status, content-type, and a body excerpt so the underlying cause is
    visible in logs.
    """


def _redact_api_key(url: str) -> str:
    """Strip ``key=...`` from a Census URL so it is safe to log."""
    return re.sub(r"([?&])key=[^&]*", r"\1key=REDACTED", url)


def _parse_census_response(
    response: requests.Response,
    columns: List[str],
    url: str,
) -> list:
    """
    Parse a Census API response body as JSON, raising a clear error if it isn't.

    Args:
        response: ``requests.Response`` returned by ``self.get(url)``.
        columns: Variables requested (included in the error message so the
                 sponsor can see which variable Census rejected).
        url: The URL that was requested (will be redacted before logging).

    Returns:
        Parsed JSON (a list-of-lists from the Census API).

    Raises:
        CensusAPIError: If the body is not valid JSON. Includes the redacted
                        URL, status code, content-type, and a 500-char body
                        excerpt with the actual Census error text.
    """
    try:
        return json.loads(response.text)
    except json.JSONDecodeError as exc:
        body_excerpt = (response.text or "").strip()[:500]
        content_type = response.headers.get("content-type", "unknown")
        raise CensusAPIError(
            f"Census API returned non-JSON response (HTTP {response.status_code}, "
            f"content-type={content_type}) for variables {columns}. "
            f"URL: {_redact_api_key(url)}. "
            f"Body excerpt: {body_excerpt!r}"
        ) from exc


class CensusAPIClient(BaseAPIClient):
    """
    Client for Census Bureau ACS API.

    Supports fetching data from:
    - Detailed tables (B-tables)
    - Subject tables (S-tables)
    - Data profiles (DP-tables)
    - Comparison profiles (CP-tables)

    Example:
        >>> client = CensusAPIClient()
        >>> df = client.fetch_acs_data(['B01001_001E'], geography='county')
        >>> print(df.head())
    """

    def __init__(self, api_key: Optional[str] = None, year: Optional[int] = None):
        """
        Initialize Census API client.

        Args:
            api_key: Census API key (defaults to settings.census_api_key)
            year: ACS year (defaults to settings.acs_year)

        Raises:
            ValueError: If the API key is empty or still set to the
                        ``.env.example`` placeholder. ACS 5-year data for the
                        configured year is also checked: if it has not been
                        released yet, a warning is logged (not raised) so
                        users running against pre-release years see the
                        problem before the first request fails.
        """
        super().__init__(base_url="https://api.census.gov/data")

        # ``None`` means "fall back to settings"; an explicit ``""`` is
        # treated as the caller's stated value and will trip the
        # missing-key check below (instead of silently falling back).
        raw_key = settings.census_api_key if api_key is None else api_key

        # Strip ``.env`` paste artifacts (quotes, surrounding whitespace,
        # embedded newlines from line wrap) before any validation so the
        # heuristic check sees the user's intended key, not their .env
        # syntax mistake.
        normalized_key, normalize_notes = _normalize_api_key(raw_key) if raw_key else (raw_key, [])
        for note in normalize_notes:
            logger.warning(f"CENSUS_API_KEY: {note} (check your .env syntax)")

        self.api_key = normalized_key
        self.year = year or settings.acs_year

        if not self.api_key:
            raise ValueError(
                "Census API key is missing. Set CENSUS_API_KEY in .env "
                "(get one at https://api.census.gov/data/key_signup.html)."
            )
        if self.api_key == PLACEHOLDER_API_KEY:
            raise ValueError(
                f"Census API key is still set to the .env.example placeholder "
                f"({PLACEHOLDER_API_KEY!r}). Replace it with a real key in .env."
            )

        # Soft format check. Non-blocking: the request will fail loudly
        # via CensusAPIError if Census actually rejects the key, and the
        # CLI entry points additionally call ``confirm_suspect_api_key``
        # for an interactive prompt.
        format_concern = validate_census_api_key_format(self.api_key)
        if format_concern is not None:
            logger.warning(
                f"CENSUS_API_KEY does not match expected format: {format_concern}. "
                f"Proceeding anyway; if Census rejects the key, the error will be "
                f"surfaced on the first request."
            )

        latest_acs_year = datetime.now().year - 1
        if self.year > latest_acs_year:
            logger.warning(
                f"ACS_YEAR={self.year} is later than the most recent ACS 5-year "
                f"release ({latest_acs_year}); requests will likely fail with "
                f"'unknown dataset' from the Census API. ACS 5-year data is "
                f"published in December of year+1."
            )

        logger.info(f"CensusAPIClient initialized for year {self.year}")

    def build_acs_url(
        self,
        columns: List[str],
        geography: str = "county",
        year: Optional[int] = None,
        state_codes: Optional[List[str]] = None,
    ) -> str:
        """
        Build ACS API URL.

        Args:
            columns: List of ACS column names (e.g., ['B01001_001E'])
            geography: Geographic level ('state', 'county', 'tract', 'tribal')
            year: ACS year (defaults to self.year)
            state_codes: List of state FIPS codes (for tract geography)

        Returns:
            Complete API URL string

        Raises:
            ValueError: If geography or table type is not supported
        """
        year = year or self.year

        # Determine table type from first column
        if not columns:
            raise ValueError("Must provide at least one column")

        table_id = columns[0].split("_")[0]

        # Determine dataset path based on table type
        if table_id.startswith("B"):
            # Detailed table
            dataset = f"{year}/acs/acs5"
        elif table_id.startswith("S"):
            # Subject table
            dataset = f"{year}/acs/acs5/subject"
        elif table_id.startswith("DP"):
            # Data profile
            dataset = f"{year}/acs/acs5/profile"
        elif table_id.startswith("CP"):
            # Comparison profile
            dataset = f"{year}/acs/acs5/cprofile"
        else:
            raise ValueError(f"Unknown table type for column: {columns[0]}")

        # Build variable list
        vars_str = "NAME,GEO_ID," + ",".join(columns)

        # Build geography predicate
        if geography == "county":
            geo_str = "county:*&in=state:*"
        elif geography == "state":
            geo_str = "state:*"
        elif geography == "tract":
            if state_codes:
                # Specific states
                states_str = ",".join(state_codes)
                geo_str = f"tract:*&in=state:{states_str}&in=county:*"
            else:
                # All states (requires iteration)
                geo_str = "tract:*&in=state:*&in=county:*"
        elif geography == "tribal":
            geo_str = (
                r"american%20indian%20area/alaska%20native%20area/"
                r"hawaiian%20home%20land:*"
            )
        elif geography == "tribal_tract":
            geo_str = (
                r"tribal%20census%20tract:*&in="
                r"american%20indian%20area/alaska%20native%20area/"
                r"hawaiian%20home%20land:*"
            )
        else:
            raise ValueError(f"Unsupported geography: {geography}")

        # Construct full URL
        url = (
            f"{self.base_url}/{dataset}?"
            f"get={vars_str}&for={geo_str}"
            f"&key={self.api_key}"
        )

        return url

    def fetch_acs_data(
        self,
        columns: List[str],
        geography: str = "county",
        year: Optional[int] = None,
        clean_missing: bool = True,
    ) -> pd.DataFrame:
        """
        Fetch ACS data and return as DataFrame.

        Args:
            columns: List of ACS column names
            geography: Geographic level
            year: ACS year (defaults to self.year)
            clean_missing: Replace Census missing codes with NaN (default: True)

        Returns:
            DataFrame indexed by GEO_ID with requested columns

        Example:
            >>> client = CensusAPIClient()
            >>> df = client.fetch_acs_data(
            ...     ['B17001_002E', 'B17001_001E'],
            ...     geography='county'
            ... )

        Note:
            For tract geography, the Census API doesn't allow state wildcards.
            This method automatically iterates over all states.
        """
        year = year or self.year

        logger.info(
            f"Fetching ACS data: {len(columns)} columns, "
            f"{geography} geography, year {year}"
        )
        logger.debug(f"  Columns: {columns[:5]}{'...' if len(columns) > 5 else ''}")

        # For tract geography, we need to iterate state by state
        if geography == "tract":
            return self._fetch_acs_data_by_state(columns, year, clean_missing)

        # For other geographies, use single API call
        url = self.build_acs_url(columns, geography, year)

        # Make request
        response = self.get(url)
        data = _parse_census_response(response, columns, url)

        # Convert to DataFrame
        df = pd.DataFrame(data=data[1:], columns=data[0])

        # Clean and process
        df = self._clean_acs_dataframe(df, columns, geography, clean_missing)

        logger.info(f"  Fetched {df.shape[0]} rows, {df.shape[1]} columns")

        return df

    def _fetch_acs_data_by_state(
        self,
        columns: List[str],
        year: int,
        clean_missing: bool = True,
    ) -> pd.DataFrame:
        """
        Fetch ACS tract data by iterating over each state.

        The Census API doesn't allow state wildcards for tract queries,
        so we must query each state individually and combine results.

        Args:
            columns: List of ACS column names
            year: ACS year
            clean_missing: Replace Census missing codes with NaN

        Returns:
            DataFrame indexed by GEO_ID with requested columns
        """
        # State FIPS codes (50 states + DC + PR)
        state_fips = [
            "01", "02", "04", "05", "06", "08", "09", "10", "11", "12",
            "13", "15", "16", "17", "18", "19", "20", "21", "22", "23",
            "24", "25", "26", "27", "28", "29", "30", "31", "32", "33",
            "34", "35", "36", "37", "38", "39", "40", "41", "42", "44",
            "45", "46", "47", "48", "49", "50", "51", "53", "54", "55",
            "56", "72"  # 72 = Puerto Rico
        ]

        logger.info(f"  Fetching tract data for {len(state_fips)} states...")

        all_dfs = []

        for i, state in enumerate(state_fips, 1):
            try:
                url = self.build_acs_url(columns, "tract", year, state_codes=[state])

                response = self.get(url)
                data = _parse_census_response(response, columns, url)

                if len(data) > 1:  # Has data beyond header
                    df = pd.DataFrame(data=data[1:], columns=data[0])
                    df = self._clean_acs_dataframe(df, columns, "tract", clean_missing)
                    all_dfs.append(df)

                if i % 10 == 0:
                    logger.info(f"    Progress: {i}/{len(state_fips)} states")

            except Exception as e:
                logger.warning(f"  Failed to fetch state {state}: {e}")
                continue

        # Combine all state DataFrames
        if all_dfs:
            result = pd.concat(all_dfs, axis=0)
            result = result.sort_index()
            logger.info(f"  Fetched {result.shape[0]} tract rows from {len(all_dfs)} states")
            return result
        else:
            logger.error("Failed to fetch any tract data")
            return pd.DataFrame()

    def _clean_acs_dataframe(
        self,
        df: pd.DataFrame,
        columns: List[str],
        geography: str,
        clean_missing: bool,
    ) -> pd.DataFrame:
        """
        Clean and standardize ACS DataFrame.

        Args:
            df: Raw DataFrame from Census API
            columns: List of requested columns
            geography: Geographic level
            clean_missing: Replace Census missing codes with NaN

        Returns:
            Cleaned DataFrame indexed by GEO_ID
        """
        # Clean missing data codes
        if clean_missing:
            for col in columns:
                if col in df.columns:
                    # Convert to numeric
                    df[col] = pd.to_numeric(df[col], errors="coerce")

                    # Census uses -666666666 for missing data
                    df.loc[df[col] == -666666666, col] = np.nan

        # Drop geography columns (state, county, tract codes)
        geo_cols_to_drop = []
        if geography == "county":
            geo_cols_to_drop = ["state", "county"]
        elif geography == "tract":
            geo_cols_to_drop = ["state", "county", "tract"]
        elif geography == "state":
            geo_cols_to_drop = ["state"]

        # Only drop if they exist
        geo_cols_to_drop = [c for c in geo_cols_to_drop if c in df.columns]
        if geo_cols_to_drop:
            df = df.drop(columns=geo_cols_to_drop)

        # Set index and sort
        if "GEO_ID" in df.columns:
            df = df.set_index("GEO_ID").sort_index()

        return df

    def fetch_labels(
        self,
        year: Optional[int] = None,
        table_types: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """
        Fetch variable labels/metadata from Census API.

        Args:
            year: ACS year (defaults to settings.acs_labels_year)
            table_types: List of table types to fetch
                        (default: ['', 'subject/', 'profile/', 'cprofile/'])

        Returns:
            DataFrame with columns: [name, label, concept, ...]

        Example:
            >>> client = CensusAPIClient()
            >>> labels = client.fetch_labels()
            >>> label = labels.loc['B01001_001E', 'label']
        """
        year = year or settings.acs_labels_year

        if table_types is None:
            table_types = ["", "subject/", "profile/", "cprofile/"]

        logger.info(f"Fetching ACS variable labels for year {year}")

        all_labels = []

        for table_type in table_types:
            url = f"{self.base_url}/{year}/acs/acs5/{table_type}variables.json"

            logger.debug(f"  Fetching labels from: {table_type or 'detailed tables'}")

            try:
                response = self.get(url)
                data = _parse_census_response(response, [f"variables.json ({table_type or 'detailed'})"], url)
                variables = data["variables"]

                # Convert to DataFrame
                df = pd.DataFrame.from_dict(variables, orient="index")
                all_labels.append(df)

            except Exception as e:
                logger.warning(f"  Failed to fetch labels from {table_type}: {e}")
                continue

        # Combine all labels
        if all_labels:
            labels_df = pd.concat(all_labels, axis=0)
            logger.info(f"  Fetched {len(labels_df)} variable labels")
            return labels_df
        else:
            logger.error("Failed to fetch any variable labels")
            return pd.DataFrame()

    def get_geographies(
        self,
        geography: str,
        year: Optional[int] = None,
    ) -> pd.DataFrame:
        """
        Fetch geography reference data.

        Gets basic info for all geographies at a specific level
        (just GEO_ID, NAME, and population).

        Args:
            geography: Geographic level
            year: ACS year (defaults to self.year)

        Returns:
            DataFrame with geography metadata

        Example:
            >>> client = CensusAPIClient()
            >>> counties = client.get_geographies('county')
        """
        year = year or self.year

        logger.info(f"Fetching {geography} geography data for year {year}")

        # Fetch population column to get all geographies
        df = self.fetch_acs_data(
            ["B01001_001E"],  # Total population
            geography=geography,
            year=year,
        )

        # Rename population column
        df = df.rename(columns={"B01001_001E": "population"})

        # Reset index to get GEO_ID as column
        df = df.reset_index()

        logger.info(f"  Fetched {len(df)} {geography} geographies")

        return df

    def __repr__(self) -> str:
        """String representation."""
        return f"CensusAPIClient(year={self.year})"
