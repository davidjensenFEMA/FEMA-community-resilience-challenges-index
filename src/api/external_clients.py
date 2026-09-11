"""
External API clients for non-Census data sources.

Includes:
- EAVSClient: Election Administration and Voting Survey (voter registration)
- ARDAClient: Association of Religion Data Archives (religion census)
- POPClient: Population estimates and migration data
"""

import io
from typing import Optional, List
import pandas as pd
import numpy as np
import requests
import logging

from src.api.base_client import BaseAPIClient
from src.config.settings import settings
from src.config.paths import paths

logger = logging.getLogger(__name__)


class EAVSClient(BaseAPIClient):
    """
    Client for Election Administration and Voting Survey data.

    EAVS provides voter registration and voting statistics by county.

    Example:
        >>> client = EAVSClient()
        >>> df = client.fetch_eavs_data()
        >>> print(df[['A1a', 'A1c']].head())  # Total reg, inactive voters
    """

    def __init__(self):
        """Initialize EAVS client."""
        super().__init__(base_url="https://www.eac.gov")
        logger.info("EAVSClient initialized")

    def fetch_eavs_data(
        self,
        year: Optional[int] = None,
        counties_ref: Optional[pd.DataFrame] = None,
    ) -> pd.DataFrame:
        """
        Fetch EAVS data from EAC website.

        Args:
            year: EAVS year (defaults to 2022 for now)
            counties_ref: County reference DataFrame for merging

        Returns:
            DataFrame indexed by GEO_ID with voter registration data

        Note:
            EAVS data requires manual matching to county GEOIDs
            because their FIPS codes don't always align perfectly.
        """
        logger.info("Fetching EAVS data (voter registration)")

        # URL for 2022 EAVS data
        url = (
            "https://www.eac.gov/sites/default/files/2023-12/"
            "2022_EAVS_for_Public_Release_nolabel_V1.1_CSV.zip"
        )

        logger.debug(f"  URL: {url}")

        # Download and extract CSV from ZIP
        response = self.get(url)

        # Extract CSV from ZIP file and read it
        # The ZIP contains a single CSV file that we need to extract first
        import zipfile
        try:
            with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
                # Find the CSV file in the ZIP
                csv_files = [f for f in zf.namelist() if f.endswith('.csv')]
                if not csv_files:
                    raise ValueError("No CSV file found in EAVS ZIP archive")

                # Read the CSV from the ZIP
                with zf.open(csv_files[0]) as csv_file:
                    df = pd.read_csv(csv_file, encoding='utf-8', low_memory=False)
        except zipfile.BadZipFile:
            # Fall back to direct CSV read if it's not actually a ZIP
            logger.warning("EAVS file is not a ZIP, trying direct CSV read")
            df = pd.read_csv(io.BytesIO(response.content), encoding='latin-1')
        except Exception as e:
            logger.error(f"Failed to read EAVS data: {e}")
            raise

        logger.info(f"  Downloaded {len(df)} records")

        # Select relevant columns
        cols_to_keep = ["FIPSCode", "Jurisdiction_Name", "State_Abbr", "A1a", "A1c"]
        cols_available = [c for c in cols_to_keep if c in df.columns]
        df = df[cols_available]

        # Clean column names (jurisdiction and state)
        df["Jurisdiction_Name"] = df["Jurisdiction_Name"].str.lower().str.strip()
        df["State_Abbr"] = df["State_Abbr"].str.lower().str.strip()
        df["name_abbr"] = df["Jurisdiction_Name"] + ", " + df["State_Abbr"]

        # Handle missing/special values
        # -88 = Does not apply -> NaN (not zero — "does not apply" is missing data)
        # -99 = Data not available -> NaN
        eavs_issues = {
            -88: np.nan,  # RespondedDoesNotApply
            -99: np.nan,  # RespondedDataNotAvailable
        }
        df = df.replace(eavs_issues)

        # If counties_ref provided, merge to get GEO_IDs
        if counties_ref is not None:
            # Prepare counties reference - reset index if GEO_ID is the index
            counties_ref = counties_ref.copy()
            if counties_ref.index.name == "GEO_ID":
                counties_ref = counties_ref.reset_index()

            counties_ref["name_abbr"] = (
                counties_ref["county_name"].str.lower().str.strip()
                + ", "
                + counties_ref["state_abbr"].str.lower().str.strip()
            )

            # Merge
            df = df.merge(
                counties_ref[["name_abbr", "GEO_ID"]],
                on="name_abbr",
                how="left",
            )

            # Set index
            df = df.set_index("GEO_ID").sort_index()

        logger.info(f"  Processed {len(df)} EAVS records")

        return df

    def __repr__(self) -> str:
        return "EAVSClient()"


class ARDAClient:
    """
    Client for Association of Religion Data Archives.

    ARDA provides county-level religion census data (2010 and 2020).

    Example:
        >>> client = ARDAClient()
        >>> df = client.fetch_arda_data(year=2020)
        >>> print(df[['TOTADH', 'POP2020']].head())
    """

    def __init__(self):
        """Initialize ARDA client."""
        logger.info("ARDAClient initialized")

    def fetch_arda_data(
        self,
        year: int = 2020,
    ) -> pd.DataFrame:
        """
        Fetch ARDA religion census data.

        Args:
            year: Data year (2010 or 2020)

        Returns:
            DataFrame indexed by GEO_ID with religion data

        Note:
            2010 data is read from local Excel file (old format).
            2020 data is fetched from online source (ASARB).
        """
        logger.info(f"Fetching ARDA religion data for year {year}")

        if year == 2010:
            # Read from local file
            df = pd.read_excel(paths.arda_file)

            # Create GEO_ID from STCODE and CNTYCODE
            df["STCODE"] = df["STCODE"].astype(str).str.zfill(2)
            df["CNTYCODE"] = df["CNTYCODE"].astype(str).str.zfill(3)
            df["GEO_ID"] = "0500000US" + df["STCODE"] + df["CNTYCODE"]

            # Select relevant columns
            df = df[["GEO_ID", "TOTADH", "POP2010"]]
            df = df.rename(columns={"POP2010": f"POP{year}"})

        elif year == 2020:
            # Fetch 2020 ASARB data
            url = (
                "https://www.usreligioncensus.org/sites/default/files/"
                "2022-11/2020%20USRC%20Summaries.xlsx"
            )

            logger.debug(f"  Fetching from: {url}")

            try:
                xls = pd.ExcelFile(url)
                df = pd.read_excel(xls, sheet_name="2020 County Summary")
            except Exception as e:
                logger.warning(f"Failed to fetch online, using local file: {e}")
                # Fallback to local file if available
                local_file = paths.data / "2020 USRC Summaries.xlsx"
                if local_file.exists():
                    df = pd.read_excel(local_file, sheet_name="2020 County Summary")
                else:
                    raise

            # Drop rows with missing state name
            df = df.dropna(subset=["STATE NAME"])

            # Create GEO_ID from FIPS
            df["FIPS"] = df["FIPS"].astype(str).str.zfill(5)
            df["GEO_ID"] = "0500000US" + df["FIPS"]

            # Rename columns to match 2010 format
            df = df.rename(
                columns={
                    "TOTAL POPULATION": f"POP{year}",
                    "ADHERENTS": "TOTADH",
                }
            )

            # Select relevant columns
            df = df[["GEO_ID", "TOTADH", f"POP{year}"]]

        else:
            raise ValueError(f"Unsupported ARDA year: {year}. Use 2010 or 2020.")

        # Add a generic 'POP' column for calculations (Religion indicator uses 'POP' as denominator)
        pop_col = f"POP{year}"
        if pop_col in df.columns:
            df["POP"] = df[pop_col]

        # Set index
        df = df.set_index("GEO_ID").sort_index()

        logger.info(f"  Fetched {len(df)} records")

        return df

    def __repr__(self) -> str:
        return "ARDAClient()"


class POPClient(BaseAPIClient):
    """
    Client for Census Population Estimates (migration data).

    Provides annual net migration estimates by county.

    Example:
        >>> client = POPClient()
        >>> df = client.fetch_pop_data(years=[2020, 2019, 2018])
        >>> print(df.head())
    """

    def __init__(self):
        """Initialize POP client."""
        super().__init__(base_url="https://www2.census.gov")
        logger.info("POPClient initialized")

    def fetch_pop_data(
        self,
        years: Optional[List[int]] = None,
        pop_year: Optional[int] = None,
    ) -> pd.DataFrame:
        """
        Fetch population migration data.

        Args:
            years: List of years to fetch (e.g., [2020, 2019, 2018])
            pop_year: Base year for dataset (defaults to settings.pop_year)

        Returns:
            DataFrame indexed by GEO_ID with NETMIG columns

        Example:
            >>> client = POPClient()
            >>> # Fetch last 5 years
            >>> df = client.fetch_pop_data(years=[2020, 2019, 2018, 2017, 2016])
        """
        pop_year = pop_year or settings.pop_year

        # Compute decade base year (e.g., 2020 for any pop_year 2021-2029)
        # Census popest files only contain data from the decade census onward
        year_remainder = pop_year % 10
        if year_remainder == 0:
            year_remainder = 10
        year_base = pop_year - year_remainder

        if years is None:
            # Default: up to 5 years, but never earlier than the decade base
            earliest = max(pop_year - 4, year_base)
            years = list(range(pop_year, earliest - 1, -1))

        # Clamp any explicitly provided years to the available range
        years = [y for y in years if y >= year_base]
        if not years:
            raise ValueError(
                f"No valid years for POP dataset (decade base {year_base}, pop_year {pop_year})"
            )

        logger.info(f"Fetching population migration data for years {years}")

        # Build file URL
        year_range = f"{year_base}-{pop_year}"

        file_name = f"co-est{pop_year}-alldata.csv"
        url = (
            f"{self.base_url}/programs-surveys/popest/"
            f"datasets/{year_range}/counties/totals/{file_name}"
        )

        logger.debug(f"  URL: {url}")

        # Columns to fetch
        cols_years = [f"NETMIG{year}" for year in years]
        cols_geo = ["STATE", "COUNTY"]
        cols_full = cols_years + cols_geo

        # Fetch data
        response = self.get(url)
        df = pd.read_csv(
            io.StringIO(response.content.decode("ISO-8859-1")),
            usecols=cols_full,
        )

        # Create GEO_ID
        df["STATE"] = df["STATE"].astype(str).str.zfill(2)
        df["COUNTY"] = df["COUNTY"].astype(str).str.zfill(3)
        df["GEO_ID"] = "0500000US" + df["STATE"] + df["COUNTY"]

        # Drop STATE and COUNTY columns
        df = df.drop(columns=["STATE", "COUNTY"])

        # Set index
        df = df.set_index("GEO_ID").sort_index()

        logger.info(f"  Fetched {len(df)} counties, {len(cols_years)} years")

        return df

    def __repr__(self) -> str:
        return "POPClient()"
