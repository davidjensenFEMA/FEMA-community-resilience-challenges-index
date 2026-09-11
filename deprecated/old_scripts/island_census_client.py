"""
Island Areas Census API Client

A clean, object-oriented solution for building Census API endpoints and retrieving
data for US territories (American Samoa, Guam, Northern Mariana Islands, US Virgin Islands).

The design separates concerns:
- CensusURLBuilder: Constructs valid API URLs following 2020 Island Areas patterns
- TerritoryDataDownloader: Manages HTTP requests and data persistence
- Variable/Territory configuration: Clean data structures for maintainability

Usage:
    url_builder = CensusURLBuilder(api_key="your_key")
    downloader = TerritoryDataDownloader(output_dir=Path("data"))

    # Build and fetch a single indicator
    url = url_builder.build_url("dhc", "as", ["HBG41_005N", "HBG41_001N"], "county")
    data = downloader.fetch_data(url)

    # Or use the integrated workflow
    downloader.download_indicator("no_smartphone", url_builder)
"""

from __future__ import annotations

import csv
import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Union

import requests

# Local Import
from utils.utils_logger import LoggerSetup

# Initialize logger
logger = LoggerSetup.setup_logger(
    name="main", log_dir=Path("logs"), level=logging.DEBUG
)
logger.info("Logger initialized for Island Census API Client")


# Territory configuration
TERRITORY_CONFIG = {
    "as": {"name": "American Samoa", "fips": "60"},
    "gu": {"name": "Guam", "fips": "66"},
    "mp": {"name": "Northern Mariana Islands", "fips": "69"},
    "vi": {"name": "US Virgin Islands", "fips": "78"},
}

# Updated indicator definitions with correct variable patterns
# Updated indicator definitions matching your working API endpoints
INDICATOR_DEFINITIONS = {
    "age_over_65": {
        "description": "Population age 65 and over",
        "dataset_type": "dp",
        "numerator": ["DP1_0024C"],  # Age 65+
        "denominator": ["DP1_0001C"],  # Total population
        "geography": "county",
    },
    "low_education": {
        "description": "Population with less than high school education",
        "dataset_type": "dp",
        "numerator": ["DP2_0101C"],  # Less than high school
        "denominator": ["DP2_0102C"],  # Total population 25+ for education
        "geography": "county",
    },
    "disability_rate": {
        "description": "Population with a disability",
        "dataset_type": "dhc",
        "numerator": ["PBG32_014N"],  # With disability
        "denominator": ["PBG32_009N"],  # Total civilian noninstitutionalized population
        "geography": "county",
    },
    "limited_english": {
        "description": "Population with limited English proficiency",
        "dataset_type": "dhc",
        "numerator": ["PBG112_003N"],  # Limited English proficiency
        "denominator": ["PBG112_001N"],  # Total population
        "geography": "county",
    },
    "uninsured": {
        "description": "Population without health insurance",
        "dataset_type": "dhc",
        "numerator": ["PBG127_013N"],  # Uninsured civilian
        "denominator": ["PBG127_001N"],  # Total population for insurance status
        "geography": "county",
    },
    "unemployment_rate": {
        "description": "Unemployment rate in civilian labor force",
        "dataset_type": "dhc",
        "numerator": ["PBG112_001N"],  # Unemployed
        "denominator": ["PBG112_003N"],  # Civilian labor force
        "geography": "county",
    },
    "median_household_income": {
        "description": "Median household income",
        "dataset_type": "dhc",
        "numerator": ["PBG43_001N"],  # Median household income (single value)
        "denominator": None,
        "geography": "county",
    },
    "medical_practitioners": {
        "description": "Medical practitioners per population",
        "dataset_type": "dhc",
        "numerator": ["PCT54_053N", "PCT54_017N"],  # Healthcare practitioners
        "denominator": ["PCT54_001N"],  # Total employed population
        "geography": "county",
    },
    "unemployed_women": {
        "description": "Unemployed women in labor force",
        "dataset_type": "dhc",
        "numerator": ["PBG32_014N"],  # Unemployed women
        "denominator": [
            "PBG32_012N"
        ],  # Total employed population (proxy for labor force)
        "geography": "county",
    },
    "poverty_rate": {
        "description": "Population below poverty level",
        "dataset_type": "dhc",
        "numerator": ["PBG73_002N"],  # Below poverty level
        "denominator": ["PBG73_001N"],  # Total population for poverty determination
        "geography": "county",
    },
    "single_parent_household": {
        "description": "Single-parent households",
        "dataset_type": "dp",
        "numerator": ["DP2_0008C", "DP2_0009C"],  # Single-parent household types
        "denominator": ["DP2_0007C"],  # Total households with children
        "geography": "county",
    },
    "no_smartphone": {
        "description": "Households without smartphone access",
        "dataset_type": "dhc",
        "numerator": ["HBG41_005N"],  # Households without smartphone
        "denominator": ["HBG41_001N"],  # Total households
        "geography": "county",
    },
}


@dataclass
class CensusVariable:
    """Represents a Census variable with metadata."""

    name: str
    description: str
    table_prefix: str
    suffix: str

    @classmethod
    def parse(cls, variable_name: str, description: str = "") -> CensusVariable:
        """Parse variable name to extract components."""
        parts = variable_name.split("_")
        table_prefix = parts[0]

        if variable_name.endswith("N"):
            suffix = "N"
        elif variable_name.endswith("C"):
            suffix = "C"
        elif "COL" in variable_name and "R" in variable_name:
            suffix = "R"
        else:
            suffix = "Unknown"

        return cls(variable_name, description, table_prefix, suffix)


class CensusURLBuilder:
    """Builds Census API URLs for Island Areas datasets."""

    BASE_URL = "https://api.census.gov/data/2020/dec/"

    def __init__(self, api_key: str, logger: Optional[logging.Logger] = None):
        self.api_key = api_key
        self.logger = logger or self._setup_default_logger()

    def _setup_default_logger(self) -> logging.Logger:
        """Create a default logger if none provided."""
        logger = logging.getLogger("census_url_builder")
        if not logger.hasHandlers():
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(
                logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s")
            )
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return logger

    def build_url(
        self,
        dataset_type: str,
        territory: str,
        variables: Sequence[str],
        geography: str = "county",
    ) -> str:
        """
        Build a complete Census API URL.

        Args:
            dataset_type: "dhc", "dp", or "crosstab"
            territory: "as", "gu", "mp", or "vi"
            variables: List of variable names to retrieve
            geography: Geographic level ("county", "tract", "state")

        Returns:
            Complete API URL string
        """
        if territory not in TERRITORY_CONFIG:
            raise ValueError(
                f"Invalid territory: {territory}. Must be one of {list(TERRITORY_CONFIG.keys())}"
            )

        # Construct dataset endpoint
        endpoint = f"{self.BASE_URL}{dataset_type}{territory}"

        # Build variable clause
        var_clause = ",".join(["NAME"] + list(variables))

        # Build geography clause
        fips_code = TERRITORY_CONFIG[territory]["fips"]
        if geography == "county":
            geo_clause = f"for=county:*&in=state:{fips_code}"
        elif geography == "tract":
            geo_clause = f"for=tract:*&in=state:{fips_code}"
        elif geography == "state":
            geo_clause = f"for=state:{fips_code}"
        else:
            raise ValueError(f"Invalid geography: {geography}")

        # Assemble final URL
        url = f"{endpoint}?get={var_clause}&{geo_clause}&key={self.api_key}"

        self.logger.debug(f"Built URL: {url}")
        return url

    def build_indicator_urls(self, indicator_name: str) -> Dict[str, str]:
        """
        Build URLs for a specific indicator across all territories.

        Args:
            indicator_name: Key from INDICATOR_DEFINITIONS

        Returns:
            Dictionary mapping territory codes to URLs
        """
        if indicator_name not in INDICATOR_DEFINITIONS:
            raise ValueError(f"Unknown indicator: {indicator_name}")

        indicator = INDICATOR_DEFINITIONS[indicator_name]
        variables = indicator["numerator"][:]
        if indicator["denominator"]:
            variables.extend(indicator["denominator"])

        urls = {}
        for territory in TERRITORY_CONFIG.keys():
            try:
                url = self.build_url(
                    dataset_type=indicator["dataset_type"],
                    territory=territory,
                    variables=variables,
                    geography=indicator["geography"],
                )
                urls[territory] = url
            except Exception as e:
                self.logger.warning(f"Failed to build URL for {territory}: {e}")

        return urls


class TerritoryDataDownloader:
    """Handles data retrieval and persistence for Census API calls."""

    def __init__(
        self,
        output_dir: Path,
        timeout: int = 30,
        logger: Optional[logging.Logger] = None,
    ):
        self.output_dir = Path(output_dir).expanduser().resolve()
        self.timeout = timeout
        self.logger = logger or self._setup_default_logger()

        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _setup_default_logger(self) -> logging.Logger:
        """Create a default logger if none provided."""
        logger = logging.getLogger("territory_downloader")
        if not logger.hasHandlers():
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(
                logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s")
            )
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return logger

    def fetch_data(self, url: str) -> Optional[List[List[str]]]:
        """
        Fetch JSON data from Census API URL.

        Args:
            url: Complete Census API URL

        Returns:
            List of rows (including header) or None if failed
        """
        try:
            self.logger.debug(f"Fetching: {url}")
            response = requests.get(url, timeout=self.timeout)
            response.raise_for_status()

            data = response.json()
            if not data or len(data) == 0:
                self.logger.warning("API returned empty data")
                return None

            return data

        except requests.exceptions.RequestException as e:
            self.logger.error(f"HTTP request failed: {e}")
            return None
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse JSON response: {e}")
            return None

    def save_csv(
        self, data: List[List[str]], indicator_name: str, territory: str
    ) -> Path:
        """
        Save data to CSV file with organized directory structure.

        Args:
            data: List of rows including header
            indicator_name: Name of the indicator for directory organization
            territory: Territory code for filename

        Returns:
            Path to saved file
        """
        # Create indicator subdirectory
        indicator_dir = self.output_dir / indicator_name
        indicator_dir.mkdir(parents=True, exist_ok=True)

        # Create filename with territory info
        territory_name = TERRITORY_CONFIG[territory]["name"].replace(" ", "_").lower()
        filename = f"{territory}_{territory_name}.csv"
        filepath = indicator_dir / filename

        # Write CSV data
        with filepath.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerows(data)

        self.logger.info(f"Saved {len(data)-1} rows to {filepath}")
        return filepath

    def download_indicator(
        self, indicator_name: str, url_builder: CensusURLBuilder
    ) -> Dict[str, Optional[Path]]:
        """
        Download data for an indicator across all territories.

        Args:
            indicator_name: Key from INDICATOR_DEFINITIONS
            url_builder: Configured CensusURLBuilder instance

        Returns:
            Dictionary mapping territory codes to saved file paths (or None if failed)
        """
        self.logger.info(f"Downloading indicator: {indicator_name}")

        urls = url_builder.build_indicator_urls(indicator_name)
        results = {}

        for territory, url in urls.items():
            territory_name = TERRITORY_CONFIG[territory]["name"]
            self.logger.info(f"  Fetching {territory_name} ({territory})...")

            data = self.fetch_data(url)
            if data:
                filepath = self.save_csv(data, indicator_name, territory)
                results[territory] = filepath
            else:
                self.logger.warning(f"  Failed to get data for {territory}")
                results[territory] = None

        return results

    def download_all_indicators(
        self, url_builder: CensusURLBuilder
    ) -> Dict[str, Dict[str, Optional[Path]]]:
        """
        Download all defined indicators across all territories.

        Args:
            url_builder: Configured CensusURLBuilder instance

        Returns:
            Nested dictionary: {indicator_name: {territory: filepath}}
        """
        all_results = {}

        for indicator_name in INDICATOR_DEFINITIONS.keys():
            try:
                results = self.download_indicator(indicator_name, url_builder)
                all_results[indicator_name] = results
            except Exception as e:
                self.logger.error(f"Failed to download {indicator_name}: {e}")
                all_results[indicator_name] = {}

        return all_results


def main():
    """Example usage of the Island Areas Census API client."""
    import argparse

    parser = argparse.ArgumentParser(description="Download Census Island Areas data")
    parser.add_argument(
        "--api-key",
        default=os.getenv("CENSUS_API_KEY"),
        help="Census API key (or set CENSUS_API_KEY env var)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/island_data"),
        help="Output directory for CSV files",
    )
    parser.add_argument(
        "--indicator", help="Specific indicator to download (default: all)"
    )
    parser.add_argument(
        "--log-level", default="DEBUG", choices=["DEBUG", "INFO", "WARNING", "ERROR"]
    )

    args = parser.parse_args()

    if not args.api_key:
        print(
            "Error: Census API key required. Set CENSUS_API_KEY env var or use --api-key"
        )
        sys.exit(1)

    # # Setup logging
    # logging.basicConfig(
    #     level=getattr(logging, args.log_level),
    #     format="%(asctime)s | %(levelname)-8s | %(message)s"
    # )
    # logger = logging.getLogger("main")

    # Initialize components
    url_builder = CensusURLBuilder(api_key=args.api_key, logger=logger)
    downloader = TerritoryDataDownloader(output_dir=args.output_dir, logger=logger)

    # Download data
    if args.indicator:
        if args.indicator not in INDICATOR_DEFINITIONS:
            logger.error(f"Unknown indicator: {args.indicator}")
            logger.info(f"Available indicators: {list(INDICATOR_DEFINITIONS.keys())}")
            sys.exit(1)
        results = downloader.download_indicator(args.indicator, url_builder)
        logger.info(f"Download complete. Results: {results}")
    else:
        logger.info("Downloading all indicators...")
        results = downloader.download_all_indicators(url_builder)

        # Summary
        total_files = sum(
            1
            for indicator_results in results.values()
            for filepath in indicator_results.values()
            if filepath
        )
        logger.info(
            f"Download complete. {total_files} files saved to {args.output_dir}"
        )


if __name__ == "__main__":
    main()
