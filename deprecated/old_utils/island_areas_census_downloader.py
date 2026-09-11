"""island_areas_census_downloader.py

Download 2020 Island‑Areas Decennial indicators (counts / percents) for
American Samoa, Guam, the Commonwealth of the Northern Mariana Islands, and the
U.S. Virgin Islands.  The code is intentionally written in a clean, object‑
oriented style with **pathlib** for file‑system work and **logging** for
transparent progress / error messages.

Update – 2025‑06‑04
===================
* **Completed `INDICATOR_MAP`** so it now contains every indicator listed in
your spreadsheet that can be sourced from the Island‑Areas Census API.
* Added support for **three geography levels** – `state`, `county` (county‑
equivalents), and `tract` – via a new `geography` field in each indicator’s
config.
* `CensusEndpoint` now handles `tract:*` URLs automatically when an indicator
sets `geography='tract'`.

The rest of the design is unchanged:
* `CensusEndpoint` builds a single API URL for one territory.
* `IslandAreasDownloader` loops through indicators × territories, downloads JSON
  via `requests`, and writes tidy CSV files.
* You can extend output targets, swap in `pandas`, or go async by replacing the
  small `_fetch_json` helper.

Run:
-----
```bash
export CENSUS_API_KEY="<your key>"
python island_areas_census_downloader.py --out data/islands --log-level DEBUG
```

Folders like `data/islands/no_smartphone/78.csv` (USVI) will appear, each with
header row + data rows.
"""

from __future__ import annotations

import csv
import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import requests

# Local Import
from utils.utils_logger import LoggerSetup

# Initialize logger
logger = LoggerSetup.setup_logger(
    name="main", log_dir=Path("logs"), level=logging.DEBUG
)
logger.info("Logger initialized for US Territory Census Downloader")


###############################################################################
# Territory‑specific dataset suffixes
###############################################################################

DATASET_BY_TERRITORY: dict[str, str] = {
    "60": "as",  # American Samoa
    "66": "gu",  # Guam
    "69": "mp",  # Northern Mariana Islands
    "78": "vi",  # U.S. Virgin Islands
}

###############################################################################
# Indicator → variable map (completed)
###############################################################################
# Each entry:
#   table        – two‑letter table ID (CT#, DP#, HBG#)
#   numerator    – list[str] variables (counts) to sum for numerator
#   denominator  – list[str] | None – vars to sum for denominator
#   geography    – 'county', 'tract', or 'state'. Default = 'county'.
#
# NOTE 1  – Variables always end with **C** (count) in Island‑Areas files.
# NOTE 2  – Percent versions are identical but with a trailing **P** (swap if
#           you prefer percentages).
###############################################################################

INDICATOR_MAP: Mapping[str, dict] = {
    # --- Demographics -----------------------------------------------------
    "age_over_65": {
        "table": "CT1",
        "numerator": ["CT1_035C"],
        "denominator": ["CT1_001C"],
        "geography": "county",
    },
    "low_edu_attainment": {
        "table": "CT27",
        "numerator": ["CT27_007C", "CT27_010C"],
        "denominator": ["CT27_006C"],
        "geography": "county",
    },
    "disability": {
        "table": "CT16",
        "numerator": ["CT16_003C"],
        "denominator": ["CT16_001C"],
        "geography": "county",
    },
    "limited_english": {
        "table": "CT25",
        "numerator": ["CT25_003C"],
        "denominator": ["CT25_001C"],
        "geography": "county",
    },
    "no_health_insurance": {
        "table": "CT16",
        "numerator": ["CT16_005C"],
        "denominator": ["CT16_001C"],
        "geography": "county",
    },
    "no_vehicle": {
        "table": "DP4",
        "numerator": ["DP4_0021C"],  # Households with no vehicle available
        "denominator": ["DP4_0001C"],
        "geography": "county",
    },
    "unemployment_rate": {
        "table": "CT28",
        "numerator": ["CT28_005C"],  # Unemployed
        "denominator": ["CT28_003C"],  # Civilian labour force
        "geography": "county",
    },
    "median_household_income": {
        "table": "CT14",
        "numerator": ["CT14_001C"],  # Median value (count field – treat as scalar)
        "denominator": None,
        "geography": "county",
    },
    "home_ownership": {
        "table": "DP4",
        "numerator": ["DP4_0046C"],  # Owner‑occupied housing units
        "denominator": ["DP4_0001C"],
        "geography": "county",
    },
    "single_parent_household": {
        "table": "HBG4",
        "numerator": ["HBG4_004C", "HBG4_005C"],  # Male‑ / Female‑headed, no spouse
        "denominator": ["HBG4_001C"],
        "geography": "tract",  # Table only published at tract + state totals
    },
    "presence_mobile_homes": {
        "table": "DP4",
        "numerator": ["DP4_0014C"],  # Mobile homes
        "denominator": ["DP4_0001C"],
        "geography": "county",
    },
    "medical_professional_capacity": {
        "table": "CT10",
        "numerator": ["CT10_016C"],  # Health‑diagnosing & treating practitioners
        "denominator": ["CT1_001C"],  # Total pop (from CT1) – present in same dataset
        "geography": "county",
    },
    "unemployed_women": {
        "table": "CT28",
        "numerator": ["CT28_013C"],  # Female unemployed
        "denominator": ["CT28_012C"],  # Female labor force
        "geography": "county",
    },
    "employment_dominant_sector": {
        "table": "CT10",
        "numerator": [  # rows 33‑45 = industry break‑outs
            "CT10_033C",
            "CT10_034C",
            "CT10_035C",
            "CT10_036C",
            "CT10_037C",
            "CT10_038C",
            "CT10_039C",
            "CT10_040C",
            "CT10_041C",
            "CT10_042C",
            "CT10_043C",
            "CT10_044C",
            "CT10_045C",
        ],
        "denominator": ["CT10_001C"],  # Employed pop >16
        "geography": "county",
    },
    "no_smartphone": {
        "table": "HBG41",
        "numerator": ["HBG41_005C"],  # Households without smartphone
        "denominator": ["HBG41_001C"],
        "geography": "tract",
    },
    "poverty": {
        "table": "CT15",
        "numerator": ["CT15_002C"],  # Persons below poverty level
        "denominator": ["CT15_001C"],  # Pop for whom poverty status determined
        "geography": "county",
    },
    # --- Indicators that live in *other* sources (CBP, ARDA, EAVS) are
    # purposely omitted so the downloader will not fail. Add them later via
    # a new subclass that hits those datasets.
}

###############################################################################
# Logging helper
###############################################################################


def setup_logger(
    name: str = "island_areas", level: int = logging.INFO
) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.hasHandlers():
        return logger
    logger.setLevel(level)
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s"))
    logger.addHandler(h)
    return logger


###############################################################################
# CensusEndpoint – URL builder
###############################################################################


@dataclass
class CensusEndpoint:
    dataset_stub: str  # e.g. "crosstabmp" or "dpvi"
    variables: Sequence[str]
    state_fips: str
    geography: str = "county"  # 'county', 'tract', or 'state'

    def url(self, api_key: str | None = None) -> str:
        base = f"https://api.census.gov/data/2020/dec/{self.dataset_stub}"
        var_clause = ",".join(self.variables)

        if self.geography == "county":
            geo_clause = f"for=county:*&in=state:{self.state_fips}"
        elif self.geography == "tract":
            geo_clause = f"for=tract:*&in=state:{self.state_fips}"
        else:  # state‑level totals
            geo_clause = f"for=state:{self.state_fips}"

        parts = [f"get=NAME,{var_clause}", geo_clause]
        if api_key:
            parts.append(f"key={api_key}")
        return f"{base}?{'&'.join(parts)}"


###############################################################################
# Downloader orchestrator
###############################################################################


class IslandAreasDownloader:
    def __init__(
        self, api_key: str, output_dir: Path, logger: logging.Logger | None = None
    ):
        self.api_key = api_key
        self.out = output_dir.expanduser().resolve()
        self.out.mkdir(parents=True, exist_ok=True)
        self.logger = logger or setup_logger()

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def run(self, indicators: Mapping[str, dict] = INDICATOR_MAP) -> None:
        for ind_name, cfg in indicators.items():
            self.logger.info("⏬ %s", ind_name.replace("_", " ").title())
            self._download_indicator(ind_name, cfg)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _download_indicator(self, name: str, cfg: dict) -> None:
        numerator: list[str] = cfg["numerator"]
        denominator: list[str] | None = cfg.get("denominator")
        vars_all = numerator + (denominator or [])
        geography = cfg.get("geography", "county")

        table_prefix = cfg["table"]
        if table_prefix.startswith("DP"):
            dataset_type = "dp"
        elif table_prefix.startswith(("CT", "HBG")):
            dataset_type = "dhc"  # dhcas, dhcgu, dhcmp, dhcvi
        else:
            dataset_type = "crosstab"  # reserve for true Crosstab tables later

        for state_fips, terr_stub in DATASET_BY_TERRITORY.items():
            dataset_stub = f"{dataset_type}{terr_stub}"
            endpoint = CensusEndpoint(
                dataset_stub, vars_all, state_fips, geography=geography
            )
            url = endpoint.url(self.api_key)
            self.logger.debug("URL → %s", url)
            rows = self._fetch_json(url)
            if not rows:
                self.logger.warning("No data for %s (%s)", name, state_fips)
                continue
            self._write_csv(name, state_fips, rows)
            self.logger.info(
                "✔  %s – state %s (%d rows)", name, state_fips, len(rows) - 1
            )

    def _fetch_json(self, url: str) -> list[list[str]] | None:
        try:
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            self.logger.error("HTTP error: %s", exc)
            return None

    def _write_csv(
        self, indicator: str, state_fips: str, rows: list[list[str]]
    ) -> None:
        out_dir = self.out / indicator
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{state_fips}.csv"
        with out_path.open("w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerows(rows)


###############################################################################
# CLI
###############################################################################

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Download 2020 Island‑Areas indicators to CSV files."
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("CENSUS_API_KEY"),
        help="Census API key or env var CENSUS_API_KEY",
    )
    parser.add_argument(
        "--out", type=Path, default=Path("output"), help="Output directory root"
    )
    parser.add_argument(
        "--log-level", default="INFO", help="Logging level: DEBUG, INFO, WARNING …"
    )
    args = parser.parse_args()

    # log = setup_logger(level=getattr(logging, args.log_level.upper(), logging.INFO))
    log = logger

    if not args.api_key:
        log.error("Missing --api-key (or $CENSUS_API_KEY)")
        sys.exit(1)

    IslandAreasDownloader(api_key=args.api_key, output_dir=args.out, logger=log).run()
