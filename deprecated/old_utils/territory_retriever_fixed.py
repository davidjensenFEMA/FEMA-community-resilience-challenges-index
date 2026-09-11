"""
US Territory Census Data Retriever - FIXED VERSION

A clean, object-oriented approach to mapping and retrieving census data
for US territories (AS, GU, MP, VI) where ACS variables need to be mapped
to Decennial Census equivalents using territory-specific API endpoints.
"""

import json
import logging
import pandas as pd
import requests
from pathlib import Path
from typing import Dict, List, Optional, Union
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

# Local Import
from utils.utils_logger import LoggerSetup

# Initialize logger
logger = LoggerSetup.setup_logger("main", Path("logs"), logging.INFO)
logger.info("Logger initialized for US Territory Census Data Retriever")


class TerritoryDataRetriever:
    """
    Handles mapping and retrieval of census data for US territories.

    Think of this like a universal translator between different census "languages" -
    it knows that when you ask for an ACS variable for a territory, you actually
    need to request the equivalent Decennial Census variable instead, AND it uses
    the correct territory-specific API endpoint (like having separate keys for different doors).
    """

    # Territory codes and names
    TERRITORIES = {
        "AS": "American Samoa",
        "GU": "Guam", 
        "MP": "Northern Mariana Islands",
        "VI": "US Virgin Islands",
    }

    # Territory-specific API endpoints (the "special doors")
    TERRITORY_ENDPOINTS = {
        "AS": "dhcas",  # Decennial High-resolution Census American Samoa
        "GU": "dhcgu",  # Decennial High-resolution Census Guam
        "MP": "dhcmp",  # Decennial High-resolution Census Northern Mariana Islands
        "VI": "dhcvi",  # Decennial High-resolution Census Virgin Islands
    }

    def __init__(
        self,
        data_path: Union[str, Path],
        api_key: str,
    ):
        """
        Initialize the retriever.

        Args:
            data_path: Path to directory containing mapping files
            api_key: Census API key
        """
        self.data_path = Path(data_path)
        self.api_key = api_key
        self.session = self._create_session()

        # Set up logging
        self.logger = logger
        self.logger.info(f"Logger initialized for {self.__class__.__name__}")

        # Load variable mappings
        self.variable_mapping = self._load_variable_mapping()

    def _create_session(self) -> requests.Session:
        """Create a robust requests session with retry logic."""
        session = requests.Session()
        retry_strategy = Retry(
            total=3,
            connect=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def _load_variable_mapping(self) -> Dict[str, str]:
        """
        Load the mapping from ACS variables to Decennial Census variables.

        Returns:
            Dictionary mapping ACS codes to Decennial codes
        """
        mapping_file = self.data_path / "feature_summary.csv"

        if not mapping_file.exists():
            self.logger.warning(f"Mapping file not found: {mapping_file}")
            return self._create_default_mapping()

        try:
            df = pd.read_csv(mapping_file)
            # Assuming columns are 'acs_variable' and 'decennial_variable'
            # Adjust column names based on your actual CSV structure
            return dict(zip(df["acs_variable"], df["decennial_variable"]))
        except Exception as e:
            self.logger.error(f"Error loading mapping: {e}")
            return self._create_default_mapping()

    def _create_default_mapping(self) -> Dict[str, str]:
        """
        Create a simplified mapping that works with territory-specific endpoints.
        
        Territory endpoints have different variable structures than mainland Census.
        These mappings focus on basic demographic and housing variables that are
        consistently available across territory datasets.
        """
        return {
            # BASIC POPULATION - Available in all territory datasets
            "B01001_001E": "P1_001N",      # Total population
            "S0101_C01_001E": "P1_001N",   # Total population (from age table)
            "S0101_C01_030E": "P1_024N",   # Population 65 years and over (approximate)
            
            # HOUSING UNITS - Basic housing counts
            "B25001_001E": "H1_001N",      # Total housing units
            "DP04_0001E": "H1_001N",       # Total housing units (DP table equivalent)
            "DP04_0014E": "H1_003N",       # Vacant housing units
            
            # RACE AND ETHNICITY - Core demographic categories
            "B01001A_001E": "P1_003N",     # White alone
            "B01001B_001E": "P1_004N",     # Black or African American alone
            "B01001I_001E": "P1_010N",     # Hispanic or Latino
            
            # HOUSEHOLDS - Basic household structure
            "B09005_001E": "H1_001N",      # Total households (proxy with housing units)
            
            # AGE GROUPS - Simplified age categories
            "B01001_003E": "P1_004N",      # Male under 5 years (approximate)
            "B01001_027E": "P1_028N",      # Female under 5 years (approximate)
            
            # Note: Many complex ACS variables (income, education, employment)
            # are NOT available in territory datasets. Users should expect
            # limited variable availability compared to state/county data.
        }

    def create_territory_api_url(
        self, variables: List[str], territory_code: str, year: int = 2020
    ) -> str:
        """
        Build API URL for territory data using territory-specific endpoints.

        Each territory has its own special endpoint (like having different keys
        for different doors):
        - AS: /dhcas (Decennial High-resolution Census American Samoa)
        - GU: /dhcgu (Decennial High-resolution Census Guam) 
        - MP: /dhcmp (Decennial High-resolution Census Northern Mariana Islands)
        - VI: /dhcvi (Decennial High-resolution Census Virgin Islands)

        Args:
            variables: List of territory-compatible variables to retrieve
            territory_code: Two-letter territory code (AS, GU, MP, VI)
            year: Census year (2020, 2010, etc.)

        Returns:
            Complete API URL string for the specific territory
        """
        base_url = "https://api.census.gov/data"
        
        # Get territory-specific endpoint
        territory_endpoint = self.TERRITORY_ENDPOINTS.get(territory_code.upper())
        if not territory_endpoint:
            raise ValueError(f"Unknown territory code: {territory_code}")

        # Build dataset path using territory-specific endpoint
        dataset_path = f"{year}/dec/{territory_endpoint}"

        # Build variable list - territories use different standard variables
        var_list = ["NAME"] + variables  # Territories may not have GEO_ID
        var_string = ",".join(var_list)

        # Territory geography - use "us" for territory-wide data
        # Territories don't use state FIPS codes in their endpoints
        geography = "us:*"

        url = (
            f"{base_url}/{dataset_path}?"
            f"get={var_string}&"
            f"for={geography}&"
            f"key={self.api_key}"
        )

        self.logger.info(f"Territory API URL for {territory_code}: {url}")
        return url

    def _get_territory_fips(self, territory_code: str) -> str:
        """
        Get FIPS code for territory.
        
        Note: These FIPS codes are used for CBP data, not for the 
        territory-specific Decennial Census endpoints.
        """
        fips_mapping = {
            "AS": "60",  # American Samoa
            "GU": "66",  # Guam
            "MP": "69",  # Northern Mariana Islands
            "VI": "78",  # US Virgin Islands
        }
        return fips_mapping.get(territory_code.upper(), "60")

    def map_variables(self, acs_variables: List[str]) -> List[str]:
        """
        Map ACS variables to their territory-compatible equivalents.

        This is like having a dictionary that translates between the complex
        ACS "language" and the simpler territory data "language".

        Args:
            acs_variables: List of ACS variable codes

        Returns:
            List of corresponding territory-compatible variable codes
        """
        mapped_vars = []
        unmapped_vars = []

        for var in acs_variables:
            if var in self.variable_mapping:
                mapped_vars.append(self.variable_mapping[var])
            else:
                unmapped_vars.append(var)

        if unmapped_vars:
            self.logger.warning(f"Unmapped variables (may not be available in territories): {unmapped_vars}")

        # Remove duplicates while preserving order
        seen = set()
        deduplicated_vars = []
        for var in mapped_vars:
            if var not in seen:
                seen.add(var)
                deduplicated_vars.append(var)

        return deduplicated_vars

    def check_territory_variable_availability(
        self, territory_code: str, year: int = 2020
    ) -> List[str]:
        """
        Check what variables are actually available for a specific territory.
        
        This is like testing which keys work with a particular lock before
        trying to use them all.

        Args:
            territory_code: Territory to check
            year: Census year

        Returns:
            List of available variables for the territory
        """
        # Try to get the variables list from the territory endpoint
        base_url = "https://api.census.gov/data"
        territory_endpoint = self.TERRITORY_ENDPOINTS.get(territory_code.upper())
        
        if not territory_endpoint:
            self.logger.error(f"Unknown territory code: {territory_code}")
            return []

        # Get variables endpoint
        variables_url = f"{base_url}/{year}/dec/{territory_endpoint}/variables.json"
        
        try:
            response = self.session.get(variables_url, timeout=30)
            response.raise_for_status()
            
            variables_data = response.json()
            available_vars = list(variables_data.get('variables', {}).keys())
            
            self.logger.info(f"Found {len(available_vars)} variables for {territory_code}")
            return available_vars
            
        except Exception as e:
            self.logger.error(f"Could not fetch variables for {territory_code}: {e}")
            return []

    def calculate_ratios(
        self,
        data: pd.DataFrame,
        numerator_vars: List[str],
        denominator_var: str,
        ratio_name: str,
    ) -> pd.DataFrame:
        """
        Calculate ratios from retrieved data.

        This handles cases where your original features are ratios like:
        population_65_plus / total_population

        Args:
            data: DataFrame with retrieved territory data
            numerator_vars: List of variables to sum for numerator
            denominator_var: Variable to use as denominator
            ratio_name: Name for the calculated ratio column

        Returns:
            DataFrame with added ratio column
        """
        # Map variables to their territory equivalents
        mapped_num = [self.variable_mapping.get(var, var) for var in numerator_vars]
        mapped_denom = self.variable_mapping.get(denominator_var, denominator_var)

        # Check if mapped variables exist in the data
        available_num = [var for var in mapped_num if var in data.columns]
        
        if not available_num:
            self.logger.warning(f"No numerator variables found for {ratio_name}")
            data[ratio_name] = pd.NA
            return data
            
        if mapped_denom not in data.columns:
            self.logger.warning(f"Denominator variable {mapped_denom} not found for {ratio_name}")
            data[ratio_name] = pd.NA
            return data

        # Calculate numerator (sum if multiple variables)
        numerator = data[available_num].sum(axis=1)
        denominator = data[mapped_denom]

        # Calculate ratio, handling division by zero
        data[ratio_name] = numerator / denominator.replace(0, pd.NA)

        return data

    def retrieve_territory_data(
        self,
        acs_variables: List[str],
        territories: Optional[List[str]] = None,
        year: int = 2020,
    ) -> pd.DataFrame:
        """
        Retrieve data for specified territories using mapped variables.

        IMPORTANT: Territory data has much more limited variable availability
        compared to state/county ACS data. Many complex socioeconomic variables
        are simply not collected for territories.

        Args:
            acs_variables: List of ACS variable codes to map and retrieve
            territories: List of territory codes (default: all territories)
            year: Census year

        Returns:
            DataFrame with territory data
        """
        if territories is None:
            territories = list(self.TERRITORIES.keys())

        # Warn about limitations
        self._warn_about_territory_limitations(acs_variables)

        # Map ACS variables to territory equivalents
        territory_vars = self.map_variables(acs_variables)

        if not territory_vars:
            self.logger.error("No valid variable mappings found for territories")
            return pd.DataFrame()

        all_data = []

        for territory in territories:
            try:
                self.logger.info(f"Retrieving data for {territory} ({self.TERRITORIES[territory]})")
                
                territory_data = self._fetch_territory_data(
                    territory_vars, territory, year
                )
                if territory_data is not None and not territory_data.empty:
                    territory_data["territory_code"] = territory
                    territory_data["territory_name"] = self.TERRITORIES[territory]
                    all_data.append(territory_data)
                else:
                    self.logger.warning(f"No data retrieved for {territory}")

            except Exception as e:
                self.logger.error(f"Error retrieving data for {territory}: {e}")
                continue

        if not all_data:
            self.logger.error("No data retrieved for any territory")
            return pd.DataFrame()

        # Combine all territory data
        combined_data = pd.concat(all_data, ignore_index=True)
        
        self.logger.info(f"Successfully retrieved data for {len(all_data)} territories")
        return combined_data

    def retrieve_cbp_data(
        self,
        naics_codes: List[str],
        territories: Optional[List[str]] = None,
        year: int = 2020,
    ) -> pd.DataFrame:
        """
        Retrieve County Business Patterns data for territories.

        CBP data uses different endpoints than the Decennial Census territory data.
        This handles business-related indicators like:
        - Medical Professional Capacity (NAICS 621, 622)
        - Number of Hospitals (NAICS 622)
        - Civic and Social Organizations (NAICS 813)

        Args:
            naics_codes: List of NAICS industry codes
            territories: List of territory codes
            year: CBP data year

        Returns:
            DataFrame with business establishment data
        """
        if territories is None:
            territories = list(self.TERRITORIES.keys())

        all_cbp_data = []

        for territory in territories:
            for naics in naics_codes:
                try:
                    cbp_data = self._fetch_cbp_data(naics, territory, year)
                    if cbp_data is not None:
                        cbp_data["territory_code"] = territory
                        cbp_data["territory_name"] = self.TERRITORIES[territory]
                        cbp_data["naics_code"] = naics
                        all_cbp_data.append(cbp_data)

                except Exception as e:
                    self.logger.error(
                        f"Error retrieving CBP data for {territory}, NAICS {naics}: {e}"
                    )
                    continue

        if not all_cbp_data:
            return pd.DataFrame()

        return pd.concat(all_cbp_data, ignore_index=True)

    def _fetch_cbp_data(
        self, naics_code: str, territory_code: str, year: int
    ) -> Optional[pd.DataFrame]:
        """
        Fetch CBP data for a single territory and NAICS code.
        
        CBP data uses the standard Census API with FIPS codes,
        not the territory-specific endpoints.

        Args:
            naics_code: NAICS industry code
            territory_code: Territory code
            year: CBP year

        Returns:
            DataFrame with CBP data or None if failed
        """
        base_url = "https://api.census.gov/data"

        # Variables to retrieve
        variables = ["NAME", "ESTAB", "EMP"]  # Establishments and Employment
        var_string = ",".join(variables)

        # Geography for territory using FIPS codes
        geography = f"state:{self._get_territory_fips(territory_code)}"

        url = (
            f"{base_url}/{year}/cbp?"
            f"get={var_string}&"
            f"for={geography}&"
            f"NAICS2017={naics_code}&"
            f"key={self.api_key}"
        )

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()

            data = response.json()

            if len(data) < 2:
                self.logger.warning(
                    f"No CBP data returned for {territory_code}, NAICS {naics_code}"
                )
                return None

            # Convert to DataFrame
            df = pd.DataFrame(data[1:], columns=data[0])

            # Clean up data types
            numeric_cols = ["ESTAB", "EMP"]
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")

            return df

        except requests.exceptions.RequestException as e:
            self.logger.error(f"CBP request failed for {territory_code}: {e}")
            return None
        except json.JSONDecodeError as e:
            self.logger.error(f"CBP JSON decode error for {territory_code}: {e}")
            return None

    def get_business_indicators(
        self, territories: Optional[List[str]] = None, year: int = 2020
    ) -> Dict[str, pd.DataFrame]:
        """
        Retrieve key business indicators for territories using CBP data.

        Returns:
            Dictionary with DataFrames for different business indicators
        """
        business_indicators = {
            "medical_facilities": ["621", "622"],  # Healthcare establishments
            "hospitals": ["622"],  # Hospitals specifically
            "civic_organizations": ["813"],  # Civic and social organizations
        }

        results = {}
        for indicator_name, naics_codes in business_indicators.items():
            self.logger.info(f"Retrieving {indicator_name} data...")
            results[indicator_name] = self.retrieve_cbp_data(
                naics_codes, territories, year
            )

        return results

    def _fetch_territory_data(
        self, variables: List[str], territory_code: str, year: int
    ) -> Optional[pd.DataFrame]:
        """
        Fetch data for a single territory using territory-specific endpoint.

        Args:
            variables: Territory-compatible variables to retrieve
            territory_code: Territory code
            year: Census year

        Returns:
            DataFrame with territory data or None if failed
        """
        url = self.create_territory_api_url(variables, territory_code, year)

        try:
            self.logger.debug(f"Requesting: {url}")
            response = self.session.get(url, timeout=30)
            response.raise_for_status()

            data = response.json()

            if len(data) < 2:
                self.logger.warning(f"No data returned for {territory_code}")
                return None

            # Convert to DataFrame
            df = pd.DataFrame(data[1:], columns=data[0])

            # Clean up data types for numeric variables
            for col in variables:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")

            self.logger.info(f"Successfully retrieved {len(df)} rows for {territory_code}")
            return df

        except requests.exceptions.RequestException as e:
            self.logger.error(f"Request failed for {territory_code}: {e}")
            # Log the actual URL for debugging
            self.logger.error(f"Failed URL: {url}")
            return None
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON decode error for {territory_code}: {e}")
            return None

    def add_variable_mapping(self, acs_var: str, territory_var: str) -> None:
        """
        Add a new variable mapping.

        Args:
            acs_var: ACS variable code
            territory_var: Corresponding territory variable code
        """
        self.variable_mapping[acs_var] = territory_var
        self.logger.info(f"Added mapping: {acs_var} -> {territory_var}")

    def _warn_about_territory_limitations(self, acs_variables: List[str]) -> None:
        """
        Warn users about the significant limitations of territory data.
        """
        self.logger.warning(
            "IMPORTANT: Territory data has much more limited variable availability "
            "than state/county ACS data. Many socioeconomic variables are not available."
        )
        
        # Check for complex variables that likely won't be available
        complex_vars = [
            var for var in acs_variables 
            if any(prefix in var for prefix in [
                "DP03_",  # Economic characteristics
                "S1501_", # Education
                "S1810_", # Disability  
                "S1602_", # Language
                "S2701_", # Health insurance
                "S1903_", # Income
                "B19083", # Gini index
                "S1701_", # Poverty
            ])
        ]

        if complex_vars:
            self.logger.warning(
                f"The following complex variables may not be available in territory data: {complex_vars[:5]}..."
                f" ({len(complex_vars)} total complex variables)"
            )
            self.logger.info(
                "Consider using basic demographic variables (population, age, race) "
                "and County Business Patterns (CBP) data for economic indicators."
            )

    def get_available_variables_summary(self, year: int = 2020) -> Dict[str, List[str]]:
        """
        Get a summary of available variables for each territory.
        
        This is useful for understanding what data is actually available
        before trying to retrieve it.

        Returns:
            Dictionary mapping territory codes to available variable lists
        """
        summary = {}
        
        for territory_code in self.TERRITORIES.keys():
            self.logger.info(f"Checking available variables for {territory_code}...")
            variables = self.check_territory_variable_availability(territory_code, year)
            summary[territory_code] = variables
            
        return summary

    def save_data(self, data: pd.DataFrame, filename: str) -> None:
        """
        Save retrieved data to a file.

        Args:
            data: DataFrame to save
            filename: Output filename (will be saved in data_path)
        """
        output_path = self.data_path / filename

        if filename.endswith(".csv"):
            data.to_csv(output_path, index=False)
        elif filename.endswith((".xlsx", ".xls")):
            data.to_excel(output_path, index=False)
        else:
            # Default to CSV
            data.to_csv(output_path.with_suffix(".csv"), index=False)

        self.logger.info(f"Data saved to: {output_path}")


# Example usage with territory-specific endpoints
if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(level=logging.INFO)

    # Initialize retriever
    data_path = Path("data")  # Adjust to your data directory
    api_key = "d665833afd3f36d12b9a0e2832c3d6b92830a29a"  # Replace with your actual key

    retriever = TerritoryDataRetriever(data_path, api_key)

    # Example 1: Check what variables are actually available
    print("=== Checking Available Variables ===")
    try:
        available_vars = retriever.get_available_variables_summary()
        for territory, vars_list in available_vars.items():
            print(f"{territory}: {len(vars_list)} variables available")
            if vars_list:
                print(f"  Sample variables: {vars_list[:5]}")
    except Exception as e:
        print(f"Error checking variables: {e}")

    # Example 2: Retrieve basic demographic data that should be available
    print("\n=== Retrieving Basic Territory Data ===")
    
    # Use only basic variables that are likely to be available
    basic_features = [
        "B01001_001E",  # Total population
        "B25001_001E",  # Total housing units
    ]

    try:
        territory_data = retriever.retrieve_territory_data(basic_features)
        if not territory_data.empty:
            print("Retrieved basic territory data:")
            print(f"Shape: {territory_data.shape}")
            print(territory_data)
            
            # Save results
            retriever.save_data(territory_data, "basic_territory_data.csv")
        else:
            print("No data retrieved")

    except Exception as e:
        print(f"Error retrieving territory data: {e}")

    # Example 3: Business indicators (these should work since they use CBP)
    print("\n=== Retrieving Business Indicators ===")

    try:
        business_data = retriever.get_business_indicators()

        for indicator, data in business_data.items():
            if not data.empty:
                print(f"\n{indicator.replace('_', ' ').title()}:")
                print(f"Shape: {data.shape}")
                if "ESTAB" in data.columns:
                    establishments_by_territory = data.groupby("territory_name")["ESTAB"].sum()
                    print(establishments_by_territory)

                # Save each business indicator
                retriever.save_data(data, f"territory_{indicator}.csv")
            else:
                print(f"No data available for {indicator}")

    except Exception as e:
        print(f"Error retrieving business data: {e}")

    print("\n=== Processing Complete ===")
    print("Check your data directory for output files.")
    print("\nNote: Many complex ACS variables are not available for territories.")
    print("Focus on basic demographic data and business patterns (CBP) data.")