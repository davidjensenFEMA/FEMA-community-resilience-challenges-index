"""
US Territory Census Data Retriever

A clean, object-oriented approach to mapping and retrieving census data
for US territories (AS, GU, MP, VI) where ACS variables need to be mapped
to Decennial Census equivalents.
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
logger = LoggerSetup.setup_logger(
    name="main", log_dir=Path("logs"), level=logging.DEBUG
)
logger.info("Logger initialized for US Territory Census Data Retriever")


class TerritoryDataRetriever:
    """
    Handles mapping and retrieval of census data for US territories.

    Think of this like a universal translator between different census "languages" -
    it knows that when you ask for an ACS variable for a territory, you actually
    need to request the equivalent Decennial Census variable instead.
    """

    # Territory codes and names
    TERRITORIES = {
        "AS": "American Samoa",
        "GU": "Guam",
        "MP": "Northern Mariana Islands",
        "VI": "US Virgin Islands",
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
        Create a comprehensive mapping from ACS variables to 2020 Decennial Census
        territory-specific table equivalents.

        Based on the 2020 Decennial Census territory tables:
        CT = Comparison Tables, DP = Detailed Profile, PCT = Population Tables,
        HBG = Household/Group Quarters, CBP = County Business Patterns
        """
        return {
            # HOUSING CHARACTERISTICS (DP04 series) → DP4 tables
            "DP04_0014E": "DP4_0010E",  # Vacant housing units (mobile homes proxy)
            "DP04_0001E": "DP4_0001E",  # Total housing units
            "DP04_0046E": "DP4_0037E",  # Owner-occupied housing units (home ownership)
            # EDUCATION (S1501 series) → CT27 (Educational Attainment)
            "S1501_C01_007E": "CT27_002E",  # Bachelor's degree (Low Educational Attainment inverse)
            "S1501_C01_008E": "CT27_003E",  # Graduate/professional degree
            "S1501_C01_006E": "CT27_001E",  # Total population 25+ for education denominator
            # TRANSPORTATION/VEHICLE (B08201 series) → DP4 (Vehicle availability)
            "B08201_002E": "DP4_0058E",  # No vehicle available
            "B08201_001E": "DP4_0057E",  # Total households (vehicle availability universe)
            # AGE AND SEX (S0101 series) → CT1 (Age tables)
            "S0101_C01_030E": "CT1_015E",  # Age 65 and over
            "S0101_C01_001E": "CT1_001E",  # Total population
            # DISABILITY (S1810 series) → CT16 (Disability Status)
            "S1810_C02_001E": "CT16_002E",  # With a disability
            "S1810_C01_001E": "CT16_001E",  # Total civilian noninstitutionalized population
            # LANGUAGE (S1602 series) → CT25 (Language Spoken at Home)
            "S1602_C03_001E": "CT25_005E",  # Speak English less than "very well"
            "S1602_C01_001E": "CT25_001E",  # Total population 5+ years
            # HOUSEHOLD RELATIONSHIPS (B09005 series) → HBG4 (Household Type)
            "B09005_004E": "HBG4_004E",  # Single-parent households with children
            "B09005_005E": "HBG4_005E",  # Single-parent households (additional category)
            "B09005_001E": "HBG4_001E",  # Total households
            # COMPUTER/INTERNET (S2801 series) → HBG41 (Technology)
            "S2801_C01_005E": "HBG41_003E",  # No smartphone (technology access proxy)
            "S2801_C01_001E": "HBG41_001E",  # Total households
            # EMPLOYMENT (DP03 series) → CT28 (Employment Status)
            "DP03_0005E": "CT28_003E",  # Unemployed
            "DP03_0003E": "CT28_002E",  # In labor force
            "DP03_0013E": "CT28_006E",  # Unemployed women
            "DP03_0012E": "CT28_005E",  # Women in labor force
            # INCOME (S1903 series) → CT14 (Income)
            "S1903_C03_001E": "CT14_001E",  # Median household income
            # GINI INDEX (B19083 series) → PCT61 (Income Inequality)
            "B19083_001E": "PCT61_001E",  # Gini Index of Income Inequality
            # INCOME BRACKETS (DP03 series) → CT14 (Income Distribution)
            "DP03_0033E": "CT14_002E",  # Less than $10,000
            "DP03_0034E": "CT14_003E",  # $10,000 to $14,999
            "DP03_0035E": "CT14_004E",  # $15,000 to $24,999
            "DP03_0036E": "CT14_005E",  # $25,000 to $34,999
            "DP03_0037E": "CT14_006E",  # $35,000 to $49,999
            "DP03_0038E": "CT14_007E",  # $50,000 to $74,999
            "DP03_0039E": "CT14_008E",  # $75,000 to $99,999
            "DP03_0040E": "CT14_009E",  # $100,000 to $149,999
            "DP03_0041E": "CT14_010E",  # $150,000 to $199,999
            "DP03_0042E": "CT14_011E",  # $200,000 or more
            "DP03_0043E": "CT14_012E",  # Additional income bracket
            "DP03_0044E": "CT14_013E",  # Additional income bracket
            "DP03_0045E": "CT14_014E",  # Additional income bracket
            "DP03_0032E": "CT14_001E",  # Total households (income universe)
            # POVERTY (S1701 series) → CT15 (Poverty Status)
            "S1701_C02_001E": "CT15_002E",  # Below poverty level
            "S1701_C01_001E": "CT15_001E",  # Total population for poverty determination
            # OCCUPATION (S2401 series) → CT10 (Occupation)
            "S2401_C01_016E": "CT10_010E",  # Healthcare practitioners (medical professional capacity)
            # HEALTH INSURANCE (S2701 series) → CT16 (Health Insurance)
            "S2701_C04_001E": "CT16_008E",  # No health insurance coverage
            "S2701_C01_001E": "CT16_007E",  # Total civilian noninstitutionalized population
            # Standard population and housing totals
            "B01001_001E": "CT1_001E",  # Total population
            "B25001_001E": "DP4_0001E",  # Total housing units
        }

    def create_territory_api_url(
        self, variables: List[str], territory_code: str, year: int = 2020
    ) -> str:
        """
        Build API URL for territory data retrieval using appropriate table types.

        Handles different Decennial Census table types for territories:
        - CT (Comparison Tables): ct/
        - DP4 (Detailed Profile 4): profile4/
        - PCT (Population and Housing Tables): /
        - HBG (Household and Group Quarters): /

        Args:
            variables: List of Decennial Census variables to retrieve
            territory_code: Two-letter territory code (AS, GU, MP, VI)
            year: Census year (2020, 2010, etc.)

        Returns:
            Complete API URL string
        """
        base_url = "https://api.census.gov/data"

        # Determine dataset path based on variable types
        dataset_path = self._get_dataset_path(variables, year)

        # Build variable list - always include NAME and GEO_ID
        var_list = ["NAME", "GEO_ID"] + variables
        var_string = ",".join(var_list)

        # Territory-specific geography parameter
        geography = f"state:{self._get_territory_fips(territory_code)}"

        url = (
            f"{base_url}/{dataset_path}?"
            f"get={var_string}&"
            f"for={geography}&"
            f"key={self.api_key}"
        )

        return url

    def _get_dataset_path(self, variables: List[str], year: int) -> str:
        """
        Determine the appropriate dataset path based on variable prefixes.

        Args:
            variables: List of variables to analyze
            year: Census year

        Returns:
            Dataset path for the API URL
        """
        # Analyze variable prefixes to determine table type
        var_prefixes = set(var.split("_")[0] for var in variables if "_" in var)

        if any(prefix.startswith("CT") for prefix in var_prefixes):
            # Comparison Tables
            return f"{year}/dec/ct"
        elif any(prefix == "DP4" for prefix in var_prefixes):
            # Detailed Profile 4
            return f"{year}/dec/profile4"
        elif any(prefix.startswith("PCT") for prefix in var_prefixes):
            # Population and Housing Tables
            return f"{year}/dec/pl"
        elif any(prefix.startswith("HBG") for prefix in var_prefixes):
            # Household and Group Quarters
            return f"{year}/dec/hgq"  # Note: verify this path
        else:
            # Default to PL (Population and Housing) tables
            return f"{year}/dec/pl"

    def _get_territory_fips(self, territory_code: str) -> str:
        """Get FIPS code for territory."""
        fips_mapping = {
            "AS": "60",  # American Samoa
            "GU": "66",  # Guam
            "MP": "69",  # Northern Mariana Islands
            "VI": "78",  # US Virgin Islands
        }
        return fips_mapping.get(territory_code.upper(), "60")

    def map_variables(self, acs_variables: List[str]) -> List[str]:
        """
        Map ACS variables to their Decennial Census equivalents.

        This is like having a dictionary that translates between two related
        but different data "languages" used by the Census Bureau.

        Args:
            acs_variables: List of ACS variable codes

        Returns:
            List of corresponding Decennial Census variable codes
        """
        mapped_vars = []
        unmapped_vars = []

        for var in acs_variables:
            if var in self.variable_mapping:
                mapped_vars.append(self.variable_mapping[var])
            else:
                unmapped_vars.append(var)

        if unmapped_vars:
            self.logger.warning(f"Unmapped variables: {unmapped_vars}")

        return mapped_vars

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
        B09005_004E + B09005_005E / B09005_001E

        Args:
            data: DataFrame with retrieved territory data
            numerator_vars: List of variables to sum for numerator
            denominator_var: Variable to use as denominator
            ratio_name: Name for the calculated ratio column

        Returns:
            DataFrame with added ratio column
        """
        # Map variables to their decennial equivalents
        mapped_num = [self.variable_mapping.get(var, var) for var in numerator_vars]
        mapped_denom = self.variable_mapping.get(denominator_var, denominator_var)

        # Calculate numerator (sum if multiple variables)
        numerator = data[mapped_num].sum(axis=1)
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

        IMPORTANT LIMITATION: Many ACS variables don't have direct equivalents
        in Decennial Census data for territories. This method will warn you about
        variables that are using proxy mappings (like total population as a substitute).

        Args:
            acs_variables: List of ACS variable codes to map and retrieve
            territories: List of territory codes (default: all territories)
            year: Census year

        Returns:
            DataFrame with territory data, indexed by GEO_ID
        """
        if territories is None:
            territories = list(self.TERRITORIES.keys())

        # Check for problematic mappings and warn user
        self._warn_about_proxy_mappings(acs_variables)

        # Map ACS variables to Decennial equivalents
        decennial_vars = self.map_variables(acs_variables)

        if not decennial_vars:
            raise ValueError("No valid variable mappings found")

        all_data = []

        for territory in territories:
            try:
                territory_data = self._fetch_territory_data(
                    decennial_vars, territory, year
                )
                if territory_data is not None:
                    territory_data["territory_code"] = territory
                    territory_data["territory_name"] = self.TERRITORIES[territory]
                    all_data.append(territory_data)

            except Exception as e:
                self.logger.error(f"Error retrieving data for {territory}: {e}")
                continue

        if not all_data:
            return pd.DataFrame()

        # Combine all territory data
        combined_data = pd.concat(all_data, ignore_index=True)

        # Set GEO_ID as index if it exists
        if "GEO_ID" in combined_data.columns:
            combined_data = combined_data.set_index("GEO_ID")

        return combined_data

    def retrieve_cbp_data(
        self,
        naics_codes: List[str],
        territories: Optional[List[str]] = None,
        year: int = 2020,
    ) -> pd.DataFrame:
        """
        Retrieve County Business Patterns data for territories.

        This handles business-related indicators like:
        - Medical Professional Capacity (NAICS 621, 622)
        - Number of Hospitals (NAICS 622)
        - Civic and Social Organizations (NAICS 813)
        - Employment in Dominant Sector (various NAICS)

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

        Args:
            naics_code: NAICS industry code
            territory_code: Territory code
            year: CBP year

        Returns:
            DataFrame with CBP data or None if failed
        """
        # CBP API structure for territories
        base_url = "https://api.census.gov/data"

        # Variables to retrieve
        variables = ["NAME", "GEO_ID", "ESTAB", "EMP"]  # Establishments and Employment
        var_string = ",".join(variables)

        # Geography for territory
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
        Retrieve key business indicators for territories.

        Returns:
            Dictionary with DataFrames for different business indicators
        """
        business_indicators = {
            "medical_facilities": ["621", "622"],  # Healthcare establishments
            "hospitals": ["622"],  # Hospitals specifically
            "civic_organizations": ["813"],  # Civic and social organizations
            "dominant_sectors": [
                "11",
                "21",
                "22",
                "23",
                "31-33",
                "42",
                "44-45",
                "48-49",
                "51",
                "52",
                "53",
                "54",
                "55",
                "56",
                "61",
                "62",
                "71",
                "72",
                "81",
                "92",
            ],  # Major sectors
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
        Fetch data for a single territory.

        Args:
            variables: Decennial Census variables to retrieve
            territory_code: Territory code
            year: Census year

        Returns:
            DataFrame with territory data or None if failed
        """
        url = self.create_territory_api_url(variables, territory_code, year)

        try:

            response = self.session.get(url, timeout=30)
            response.raise_for_status()

            data = response.json()

            if len(data) < 2:
                self.logger.warning(f"No data returned for {territory_code}")
                return None

            # Convert to DataFrame
            df = pd.DataFrame(data[1:], columns=data[0])

            # Clean up data types
            for col in variables:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
            self.logger.info(f"working: {url}")
            return df

        except requests.exceptions.RequestException as e:
            self.logger.error(f"Request failed for {territory_code}: {e}")
            return None
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON decode error for {territory_code}: {e}")
            return None

    def add_variable_mapping(self, acs_var: str, decennial_var: str) -> None:
        """
        Add a new variable mapping.

        Args:
            acs_var: ACS variable code
            decennial_var: Corresponding Decennial Census variable code
        """
        self.variable_mapping[acs_var] = decennial_var
        self.logger.info(f"Added mapping: {acs_var} -> {decennial_var}")

    def _warn_about_proxy_mappings(self, acs_variables: List[str]) -> None:
        """
        Warn users about variables that might have limitations in territory data.
        """
        # Check for any unmapped variables
        unmapped_vars = [
            var for var in acs_variables if var not in self.variable_mapping
        ]

        if unmapped_vars:
            self.logger.warning(
                f"The following variables don't have territory mappings defined: {unmapped_vars}"
            )

        # Note about business/economic data that may require CBP tables
        business_vars = [
            var
            for var in acs_variables
            if any(prefix in var for prefix in ["S2401_C01_016E"])
        ]  # Medical professionals

        if business_vars:
            self.logger.info(
                f"Variables {business_vars} may require County Business Patterns (CBP) data "
                f"which uses different API endpoints. Consider separate retrieval for business data."
            )

        # Note about data that may not be available for all territories
        limited_vars = [
            var
            for var in acs_variables
            if any(prefix in var for prefix in ["S2801", "HBG41"])
        ]  # Technology data

        if limited_vars:
            self.logger.info(
                f"Technology/communication variables {limited_vars} may have limited "
                f"availability for some territories."
            )

    def save_data(self, data: pd.DataFrame, filename: str) -> None:
        """
        Save retrieved data to a file.

        Args:
            data: DataFrame to save
            filename: Output filename (will be saved in data_path)
        """
        output_path = self.data_path / filename

        if filename.endswith(".csv"):
            data.to_csv(output_path)
        elif filename.endswith((".xlsx", ".xls")):
            data.to_excel(output_path)
        else:
            # Default to CSV
            data.to_csv(output_path.with_suffix(".csv"))

        self.logger.info(f"Data saved to: {output_path}")


# Example usage with comprehensive territory mappings
if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(level=logging.INFO)

    # Initialize retriever
    data_path = Path("data")  # Adjust to your data directory
    api_key = "d665833afd3f36d12b9a0e2832c3d6b92830a29a"  # Replace with your actual key

    retriever = TerritoryDataRetriever(data_path, api_key)

    # Example 1: Retrieve your specific features with proper territory mappings
    print("=== Retrieving Territory Census Data ===")

    # Your original feature list - now properly mapped!
    your_features = [
        "DP04_0014E",  # Vacant housing → Mobile homes presence
        "DP04_0001E",  # Total housing units
        "DP04_0046E",  # Home ownership
        "S1501_C01_007E",  # Education: Bachelor's degree
        "S1501_C01_008E",  # Education: Graduate degree
        "S1501_C01_006E",  # Education: Population 25+
        "B08201_002E",  # No vehicle available
        "B08201_001E",  # Total households (vehicle)
        "S0101_C01_030E",  # Age 65+
        "S0101_C01_001E",  # Total population
        "S1810_C02_001E",  # With disability
        "S1810_C01_001E",  # Total population (disability)
        "S1602_C03_001E",  # Limited English
        "S1602_C01_001E",  # Total population 5+ (language)
        "S2701_C04_001E",  # No health insurance
        "S2701_C01_001E",  # Total population (health insurance)
        "DP03_0005E",  # Unemployed
        "DP03_0003E",  # In labor force
        "DP03_0013E",  # Unemployed women
        "DP03_0012E",  # Women in labor force
        "S1903_C03_001E",  # Median household income
        "B19083_001E",  # Gini index
        "S1701_C02_001E",  # Below poverty
        "S1701_C01_001E",  # Total population (poverty)
    ]

    try:
        territory_data = retriever.retrieve_territory_data(your_features)
        print("Retrieved comprehensive territory data:")
        print(f"Shape: {territory_data.shape}")
        print(territory_data.head())

        # Save results
        retriever.save_data(territory_data, "comprehensive_territory_data.csv")

    except Exception as e:
        print(f"Error retrieving territory data: {e}")

    # Example 2: Calculate your specific ratios
    print("\n=== Calculating Territory Ratios ===")

    try:
        # Calculate ratios based on your feature specifications
        ratios_to_calculate = [
            {
                "numerator": ["DP04_0014E"],
                "denominator": "DP04_0001E",
                "name": "vacant_housing_rate",
            },
            {
                "numerator": ["DP04_0046E"],
                "denominator": "DP04_0001E",
                "name": "home_ownership_rate",
            },
            {
                "numerator": ["S1501_C01_007E", "S1501_C01_008E"],
                "denominator": "S1501_C01_006E",
                "name": "higher_education_rate",
            },
            {
                "numerator": ["B08201_002E"],
                "denominator": "B08201_001E",
                "name": "no_vehicle_rate",
            },
            {
                "numerator": ["S0101_C01_030E"],
                "denominator": "S0101_C01_001E",
                "name": "elderly_population_rate",
            },
            {
                "numerator": ["S1810_C02_001E"],
                "denominator": "S1810_C01_001E",
                "name": "disability_rate",
            },
            {
                "numerator": ["S1602_C03_001E"],
                "denominator": "S1602_C01_001E",
                "name": "limited_english_rate",
            },
            {
                "numerator": ["S2701_C04_001E"],
                "denominator": "S2701_C01_001E",
                "name": "no_health_insurance_rate",
            },
            {
                "numerator": ["DP03_0005E"],
                "denominator": "DP03_0003E",
                "name": "unemployment_rate",
            },
            {
                "numerator": ["DP03_0013E"],
                "denominator": "DP03_0012E",
                "name": "women_unemployment_rate",
            },
            {
                "numerator": ["S1701_C02_001E"],
                "denominator": "S1701_C01_001E",
                "name": "poverty_rate",
            },
        ]

        # Get all variables needed for ratios
        all_ratio_vars = set()
        for ratio in ratios_to_calculate:
            all_ratio_vars.update(ratio["numerator"])
            all_ratio_vars.add(ratio["denominator"])

        # Retrieve data
        ratio_data = retriever.retrieve_territory_data(list(all_ratio_vars))

        # Calculate all ratios
        for ratio in ratios_to_calculate:
            ratio_data = retriever.calculate_ratios(
                ratio_data,
                numerator_vars=ratio["numerator"],
                denominator_var=ratio["denominator"],
                ratio_name=ratio["name"],
            )

        # Display calculated ratios
        ratio_columns = [r["name"] for r in ratios_to_calculate]
        print("Calculated territory ratios:")
        print(ratio_data[ratio_columns + ["territory_name"]].round(4))

        retriever.save_data(ratio_data, "territory_calculated_ratios.csv")

    except Exception as e:
        print(f"Error calculating ratios: {e}")

    # Example 3: Business indicators using CBP data
    print("\n=== Retrieving Business Indicators ===")

    try:
        business_data = retriever.get_business_indicators()

        for indicator, data in business_data.items():
            if not data.empty:
                print(f"\n{indicator.replace('_', ' ').title()}:")
                print(f"Shape: {data.shape}")
                print(data.groupby("territory_name")["ESTAB"].sum())

                # Save each business indicator
                retriever.save_data(data, f"territory_{indicator}.csv")

    except Exception as e:
        print(f"Error retrieving business data: {e}")

    # Example 4: Summary report combining all data
    print("\n=== Creating Summary Report ===")

    try:
        # Combine key indicators
        summary_vars = [
            "S0101_C01_001E",  # Total population
            "DP04_0001E",  # Total housing
            "S0101_C01_030E",  # Age 65+
            "S1701_C02_001E",  # Poverty
            "DP03_0005E",  # Unemployment
        ]

        summary_data = retriever.retrieve_territory_data(summary_vars)

        # Add some basic calculations
        summary_data["elderly_rate"] = (
            summary_data[retriever.variable_mapping["S0101_C01_030E"]]
            / summary_data[retriever.variable_mapping["S0101_C01_001E"]]
        )

        print("Territory Summary:")
        display_cols = (
            ["territory_name"]
            + [retriever.variable_mapping[var] for var in summary_vars]
            + ["elderly_rate"]
        )
        available_cols = [col for col in display_cols if col in summary_data.columns]
        print(summary_data[available_cols].round(2))

        retriever.save_data(summary_data, "territory_summary_report.csv")

    except Exception as e:
        print(f"Error creating summary: {e}")

    print("\n=== Processing Complete ===")
    print("Check your data directory for output files:")
