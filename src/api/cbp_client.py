"""
Census Bureau County Business Patterns (CBP) API client.

Handles fetching establishment counts by NAICS industry code.
"""

from typing import Optional
import json
import pandas as pd
import numpy as np
import logging

from src.api.base_client import BaseAPIClient
from src.config.settings import settings

logger = logging.getLogger(__name__)


class CBPClient(BaseAPIClient):
    """
    Client for Census Bureau County Business Patterns API.

    CBP provides annual statistics on number of establishments,
    employment, and payroll by industry (NAICS code) and geography.

    Example:
        >>> client = CBPClient()
        >>> # Fetch religious organizations (NAICS 8131)
        >>> df = client.fetch_cbp_data(8131)
        >>> print(df.head())
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        cbp_year: Optional[int] = None,
        naics_year: Optional[int] = None,
    ):
        """
        Initialize CBP API client.

        Args:
            api_key: Census API key (defaults to settings.census_api_key)
            cbp_year: CBP data year (defaults to settings.cbp_year)
            naics_year: NAICS classification year (defaults to settings.naics_year)
        """
        super().__init__(base_url="https://api.census.gov/data")

        self.api_key = api_key or settings.census_api_key
        self.cbp_year = cbp_year or settings.cbp_year
        self.naics_year = naics_year or settings.naics_year

        logger.info(
            f"CBPClient initialized for CBP year {self.cbp_year}, "
            f"NAICS year {self.naics_year}"
        )

    def build_cbp_url(self, naics_code: int) -> str:
        """
        Build CBP API URL for a specific NAICS code.

        Args:
            naics_code: NAICS industry code (e.g., 8131 for religious orgs)

        Returns:
            Complete API URL string
        """
        url = (
            f"{self.base_url}/{self.cbp_year}/cbp?"
            f"get=NAME,GEO_ID,NAICS{self.naics_year}_LABEL,ESTAB"
            f"&for=county:*&in=state:*"
            f"&NAICS{self.naics_year}={naics_code}"
            f"&key={self.api_key}"
        )

        return url

    def fetch_cbp_data(
        self,
        naics_code: int,
        fill_missing: bool = True,
    ) -> pd.DataFrame:
        """
        Fetch CBP data for a specific NAICS code.

        Args:
            naics_code: NAICS industry code
            fill_missing: Fill NaN values with 0 (default: True)
                         Missing CBP data typically means 0 establishments

        Returns:
            DataFrame indexed by GEO_ID with establishment counts

        Example:
            >>> client = CBPClient()
            >>> # Religious organizations
            >>> df = client.fetch_cbp_data(8131)
            >>> # Hospitals
            >>> df = client.fetch_cbp_data(622)
        """
        url = self.build_cbp_url(naics_code)

        logger.info(
            f"Fetching CBP data: NAICS {naics_code}, "
            f"year {self.cbp_year}"
        )

        # Make request
        response = self.get(url)
        data = json.loads(response.text)

        # Convert to DataFrame
        df = pd.DataFrame(data=data[1:], columns=data[0])

        # Get industry label
        label_col = f"NAICS{self.naics_year}_LABEL"
        if label_col in df.columns and len(df) > 0:
            industry_label = df[label_col].iloc[0]
            logger.debug(f"  Industry: {industry_label}")
        else:
            industry_label = f"NAICS {naics_code}"

        # Rename ESTAB column to NAICS code
        df = df.rename(columns={"ESTAB": str(naics_code)})

        # Convert to numeric
        df[str(naics_code)] = pd.to_numeric(df[str(naics_code)], errors="coerce")

        # Fill missing with 0 (no establishments)
        if fill_missing:
            df[str(naics_code)] = df[str(naics_code)].fillna(0)

        # Drop unnecessary columns
        cols_to_drop = [
            label_col,
            f"NAICS{self.naics_year}",
            "NAME",
            "state",
            "county",
        ]
        cols_to_drop = [c for c in cols_to_drop if c in df.columns]
        df = df.drop(columns=cols_to_drop)

        # Set index
        df = df.set_index("GEO_ID").sort_index()

        logger.info(f"  Fetched {len(df)} counties")

        return df

    def fetch_multiple_naics(
        self,
        naics_codes: list[int],
        fill_missing: bool = True,
    ) -> pd.DataFrame:
        """
        Fetch CBP data for multiple NAICS codes.

        Args:
            naics_codes: List of NAICS industry codes
            fill_missing: Fill NaN values with 0

        Returns:
            DataFrame indexed by GEO_ID with one column per NAICS code

        Example:
            >>> client = CBPClient()
            >>> codes = [8131, 622, 611]  # Religious, hospitals, schools
            >>> df = client.fetch_multiple_naics(codes)
        """
        logger.info(f"Fetching CBP data for {len(naics_codes)} NAICS codes")

        dfs = []
        for naics_code in naics_codes:
            try:
                df = self.fetch_cbp_data(naics_code, fill_missing=fill_missing)
                dfs.append(df)
            except Exception as e:
                logger.error(f"  Failed to fetch NAICS {naics_code}: {e}")
                # Create empty DataFrame with this column
                df = pd.DataFrame({str(naics_code): []})
                dfs.append(df)

        # Merge all DataFrames
        if dfs:
            result = dfs[0]
            for df in dfs[1:]:
                result = result.merge(
                    df, left_index=True, right_index=True, how="outer"
                )

            # Fill any remaining NaN with 0
            if fill_missing:
                result = result.fillna(0)

            logger.info(f"  Combined CBP data: {result.shape}")
            return result
        else:
            return pd.DataFrame()

    def __repr__(self) -> str:
        """String representation."""
        return f"CBPClient(cbp_year={self.cbp_year}, naics_year={self.naics_year})"
