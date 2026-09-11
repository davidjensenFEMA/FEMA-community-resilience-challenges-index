# FEMA CRIA Refactoring Plan - Pipeline Dev Branch

**Date**: 2025-10-30
**Branch**: `pipeline-dev`
**Status**: Planning → Implementation
**Goal**: Transform functional codebase to professional OOP architecture with Docker, PostgreSQL, and modern testing

---

## Table of Contents

1. [Overview](#overview)
2. [Current State Analysis](#current-state-analysis)
3. [Target Architecture](#target-architecture)
4. [Technology Stack](#technology-stack)
5. [Phase-by-Phase Implementation](#phase-by-phase-implementation)
6. [Database Schema Design](#database-schema-design)
7. [Docker Architecture](#docker-architecture)
8. [Testing Strategy](#testing-strategy)
9. [Migration Strategy](#migration-strategy)
10. [Timeline & Effort Estimates](#timeline--effort-estimates)

---

## Overview

### Project Purpose
Community Resilience Indicator Analysis (CRIA) - A data analysis toolkit for collecting, transforming, and aggregating community resilience indicators from various government data sources (Census ACS, CBP, EAVS, ARDA, etc.).

### Refactoring Goals

**Primary Objectives**:
1. ✅ **Professional code organization** - Move from functional scripts to OOP architecture
2. ✅ **Modern development practices** - Testing, Docker, CI/CD ready
3. ✅ **Database-backed** - Migrate from Excel outputs to PostgreSQL
4. ✅ **Reproducible environment** - Docker containers for development and production
5. ✅ **Maintainable & extensible** - Clear separation of concerns, testable components

**Inspiration Sources**:
- `docs/README.md` - MAUT Elicitation Management System (structure reference)
- `docs/CLAUDE.md` - Professional repository standards
- `docs/20251023_TESTING_GUIDE.md` - Testing philosophy and patterns

---

## Current State Analysis

### Current Workflow
```
utils_api.py → cria_pull_data.py → cria_create_indicators.py → cria_create_aggregate_indicator.py
                                                                 ↓
                                                    [cria_create_aggregate_tract.py]
                                                    [cria_create_indicators_tribal.py]
```

### Current Structure Issues

❌ **Anti-patterns identified**:
1. All workflow scripts at root level (not in `src/`)
2. Functional programming style (no classes, no encapsulation)
3. Hard-coded paths scattered throughout files
4. No environment variable usage (years, API keys, paths all hard-coded)
5. No test suite
6. Excel-based outputs (not scalable, not queryable)
7. Conda environment (difficult to share/reproduce)
8. Path handling inconsistent (mix of `pathlib` and strings)

✅ **Current strengths**:
- Working pipeline with clear workflow
- Good logging infrastructure (`utils_logger.py`)
- Comprehensive reference data system (`cria_data_reference.xlsx`)
- Multiple geography levels supported (county, tract, tribal, state)
- API retry logic implemented

### Key Files (To Refactor)

**Core Workflow**:
- `utils/utils_api.py` - API clients, data retrieval (603 lines)
- `cria_pull_data.py` - Data collection orchestration (184 lines)
- `cria_create_indicators.py` - Indicator calculation (168 lines)
- `cria_create_aggregate_indicator.py` - Aggregation & binning (main)
- `cria_functions.py` - Utility functions (cleaning, scaling, binning)

**Supporting Files**:
- `utils/utils_logger.py` - Logging setup
- `utils/utils_excel_table_save.py` - Excel export utilities
- `utils/utils_excel_tools.py` - Excel manipulation
- `utils/utils_combinations.py` - Combinatorial utilities

**To Deprecate** (non-workflow):
- `fps_tier_subtask_BERT.py`
- `fema_broadband.py`
- `bin_local_data.py`
- `cria_compare_*.py`
- `exp_averages.py`
- `pop_age_race.py`
- `zip_reader.py`
- `hpc_output.py`
- Jupyter notebooks (`*.ipynb`)
- R analysis files (`*.R`)

---

## Target Architecture

### Directory Structure

```
fema_cria/
├── src/
│   ├── __init__.py
│   ├── config/                   # Configuration management
│   │   ├── __init__.py
│   │   ├── settings.py           # Pydantic settings (loads .env)
│   │   └── paths.py              # PathConfig class (pathlib-based)
│   │
│   ├── api/                      # External API clients
│   │   ├── __init__.py
│   │   ├── base_client.py        # BaseAPIClient (retry logic, session)
│   │   ├── census_client.py      # CensusAPIClient (ACS data)
│   │   ├── cbp_client.py         # CBPClient (business patterns)
│   │   ├── eavs_client.py        # EAVSClient (voter data)
│   │   ├── arda_client.py        # ARDAClient (religion census)
│   │   └── pop_client.py         # POPClient (migration data)
│   │
│   ├── core/                     # Main CRIA logic
│   │   ├── __init__.py
│   │   ├── data_puller.py        # DataPuller class (orchestrates API calls)
│   │   ├── indicators.py         # IndicatorCalculator class
│   │   ├── aggregator.py         # AggregateIndicator class
│   │   ├── binning.py            # BinningEngine class (mapclassify)
│   │   └── transformations.py    # Data cleaning, scaling, z-scores
│   │
│   ├── db/                       # Database layer (NEW)
│   │   ├── __init__.py
│   │   ├── models.py             # SQLAlchemy ORM models
│   │   ├── session.py            # Database session management
│   │   └── repositories.py       # Data access layer (CRUD operations)
│   │
│   ├── schemas/                  # Pydantic models (NEW)
│   │   ├── __init__.py
│   │   ├── geography.py          # Geography data models
│   │   ├── indicator.py          # Indicator data models
│   │   └── reference.py          # Reference data models
│   │
│   └── utils/                    # Helper utilities
│       ├── __init__.py
│       ├── logger.py             # Refactored logging
│       ├── excel_tools.py        # Excel import/export (legacy support)
│       └── validators.py         # Data validation utilities
│
├── tests/                        # All tests (NEW)
│   ├── __init__.py
│   ├── unit/                     # Fast, isolated tests
│   │   ├── test_census_client.py
│   │   ├── test_data_puller.py
│   │   ├── test_indicators.py
│   │   ├── test_aggregator.py
│   │   └── test_transformations.py
│   ├── integration/              # Multi-component tests
│   │   ├── test_full_workflow.py
│   │   ├── test_database.py
│   │   └── test_api_clients.py
│   ├── fixtures/                 # Test data
│   │   ├── sample_reference.py
│   │   └── sample_api_responses.py
│   └── conftest.py               # Shared pytest fixtures
│
├── scripts/                      # Executable scripts (NEW)
│   ├── run_county_workflow.py    # County-level pipeline
│   ├── run_tract_workflow.py     # Tract-level pipeline
│   ├── run_tribal_workflow.py    # Tribal-level pipeline
│   ├── import_reference_data.py  # Import Excel reference to DB
│   ├── export_to_excel.py        # Export DB results to Excel
│   └── run_tests.sh              # Test runner script
│
├── docker/                       # Docker configuration (NEW)
│   ├── Dockerfile                # Python app container
│   ├── Dockerfile.dev            # Development container
│   ├── docker-compose.yml        # Multi-service orchestration
│   └── init.sql                  # Database initialization
│
├── alembic/                      # Database migrations (NEW)
│   ├── versions/
│   ├── env.py
│   └── script.py.mako
│
├── deprecated/                   # Old code (NEW)
│   └── [non-workflow files moved here]
│
├── data/                         # Data files (gitignored)
│   └── cria_data_reference.xlsx  # Reference data (still used)
│
├── output/                       # Outputs (gitignored)
│   └── reports/
│
├── logs/                         # Application logs (gitignored)
│
├── docs/                         # Documentation
│   ├── 20251030_REFACTOR_PLAN.md # This file
│   ├── 20251030_DATABASE_SCHEMA.md
│   ├── 20251030_DOCKER_GUIDE.md
│   ├── 20251023_TESTING_GUIDE.md
│   ├── README.md
│   └── CLAUDE.md
│
├── .env                          # Environment variables (gitignored)
├── .env.example                  # Template for .env
├── .gitignore
├── pyproject.toml                # Poetry dependencies & config (NEW)
├── poetry.lock                   # Locked dependencies (NEW)
├── pytest.ini                    # Pytest configuration (NEW)
├── alembic.ini                   # Alembic configuration (NEW)
└── README.md                     # Updated project README
```

---

## Technology Stack

### Core Technologies

**Language & Framework**:
- Python 3.11+ (modern type hints, dataclasses)
- Poetry (dependency management, replacing conda)

**Database**:
- PostgreSQL 16 (primary data store)
- SQLAlchemy 2.0 (ORM)
- Alembic (database migrations)
- Psycopg2 (PostgreSQL adapter)

**Development Environment**:
- Docker & Docker Compose (containerization)
- Poetry (dependency management)

**Testing**:
- pytest (testing framework)
- pytest-cov (coverage reporting)
- pytest-mock (mocking)
- pytest-asyncio (async testing, if needed)

**Configuration**:
- pydantic (settings validation)
- python-dotenv (environment variable loading)

**Data Processing** (existing):
- pandas (data manipulation)
- numpy (numerical operations)
- mapclassify (binning algorithms)

**API Clients** (existing):
- requests (HTTP client)
- openpyxl / xlsxwriter (Excel I/O, legacy support)

### New Dependencies (Poetry)

```toml
[tool.poetry.dependencies]
python = "^3.11"
pandas = "^2.1.0"
numpy = "^1.26.0"
sqlalchemy = "^2.0.0"
psycopg2-binary = "^2.9.9"
alembic = "^1.12.0"
pydantic = "^2.5.0"
pydantic-settings = "^2.1.0"
python-dotenv = "^1.0.0"
requests = "^2.31.0"
mapclassify = "^2.6.0"
openpyxl = "^3.1.0"
xlsxwriter = "^3.1.0"

[tool.poetry.group.dev.dependencies]
pytest = "^7.4.0"
pytest-cov = "^4.1.0"
pytest-mock = "^3.12.0"
black = "^23.12.0"
ruff = "^0.1.0"
mypy = "^1.7.0"

[tool.poetry.group.test.dependencies]
pytest-env = "^1.1.0"
faker = "^21.0.0"
```

---

## Phase-by-Phase Implementation

### Phase 1: Foundation & Setup (2-3 hours)

**Goal**: Create project structure, configuration system, Docker environment

**Tasks**:

1. **Create directory structure**
   ```bash
   mkdir -p src/{config,api,core,db,schemas,utils}
   mkdir -p tests/{unit,integration,fixtures}
   mkdir -p scripts docker alembic deprecated
   touch src/__init__.py tests/__init__.py
   ```

2. **Initialize Poetry**
   ```bash
   poetry init
   poetry add pandas numpy sqlalchemy psycopg2-binary alembic pydantic pydantic-settings python-dotenv requests mapclassify openpyxl xlsxwriter
   poetry add --group dev pytest pytest-cov pytest-mock black ruff mypy
   ```

3. **Create `.env.example`**
   ```bash
   # API Keys
   CENSUS_API_KEY=your_census_api_key_here

   # Data Years
   ACS_YEAR=2021
   CBP_YEAR=2020
   NAICS_YEAR=2017
   POP_YEAR=2020
   ASARB_YEAR=2020
   ACS_LABELS_YEAR=2020

   # Database
   DATABASE_URL=postgresql://cria_user:cria_password@localhost:5432/cria_db

   # Paths (relative to project root)
   DATA_DIR=data
   OUTPUT_DIR=output
   LOGS_DIR=logs

   # Processing
   DEFAULT_GEOGRAPHY=county
   DEBUG=True
   LOG_LEVEL=INFO

   # Testing
   TEST_DATABASE_URL=postgresql://cria_user:cria_password@localhost:5432/cria_test_db
   ```

4. **Create `src/config/settings.py`**
   ```python
   from pathlib import Path
   from typing import Optional
   from pydantic_settings import BaseSettings, SettingsConfigDict

   class Settings(BaseSettings):
       """Application settings loaded from .env file"""

       model_config = SettingsConfigDict(
           env_file=".env",
           env_file_encoding="utf-8",
           case_sensitive=False
       )

       # API Keys
       census_api_key: str

       # Data Years
       acs_year: int = 2021
       cbp_year: int = 2020
       naics_year: int = 2017
       pop_year: int = 2020
       asarb_year: int = 2020
       acs_labels_year: int = 2020

       # Database
       database_url: str
       test_database_url: Optional[str] = None

       # Paths
       data_dir: str = "data"
       output_dir: str = "output"
       logs_dir: str = "logs"

       # Processing
       default_geography: str = "county"
       debug: bool = True
       log_level: str = "INFO"

   settings = Settings()
   ```

5. **Create `src/config/paths.py`**
   ```python
   from pathlib import Path
   from dataclasses import dataclass
   from typing import Optional
   from src.config.settings import settings

   @dataclass
   class PathConfig:
       """Centralized path management using pathlib"""

       # Project root (auto-detect from this file's location)
       root: Path = Path(__file__).parent.parent.parent

       # Main directories
       @property
       def data(self) -> Path:
           path = self.root / settings.data_dir
           path.mkdir(exist_ok=True)
           return path

       @property
       def output(self) -> Path:
           path = self.root / settings.output_dir
           path.mkdir(exist_ok=True)
           return path

       @property
       def logs(self) -> Path:
           path = self.root / settings.logs_dir
           path.mkdir(exist_ok=True)
           return path

       # Data files
       @property
       def reference_file(self) -> Path:
           return self.data / "cria_data_reference.xlsx"

       @property
       def arda_file(self) -> Path:
           return self.data / (
               "U.S. Religion Census Religious Congregations "
               "and Membership Study, 2010 (County File).xlsx"
           )

       # Output subdirectories
       @property
       def reports(self) -> Path:
           path = self.output / "reports"
           path.mkdir(exist_ok=True)
           return path

       def get_output_file(self, filename: str, geography: str = None) -> Path:
           """Generate output file path with optional geography"""
           if geography:
               filename = f"{geography}_{filename}"
           return self.output / filename

   paths = PathConfig()
   ```

6. **Create Docker setup**

   `docker/Dockerfile`:
   ```dockerfile
   FROM python:3.11-slim

   # Install system dependencies
   RUN apt-get update && apt-get install -y \
       gcc \
       postgresql-client \
       && rm -rf /var/lib/apt/lists/*

   # Install Poetry
   RUN pip install poetry

   # Set working directory
   WORKDIR /app

   # Copy dependency files
   COPY pyproject.toml poetry.lock ./

   # Install dependencies (no dev deps in production)
   RUN poetry config virtualenvs.create false \
       && poetry install --no-dev --no-interaction --no-ansi

   # Copy application code
   COPY . .

   # Run migrations and start app
   CMD ["python", "-m", "scripts.run_county_workflow"]
   ```

   `docker/Dockerfile.dev`:
   ```dockerfile
   FROM python:3.11-slim

   # Install system dependencies
   RUN apt-get update && apt-get install -y \
       gcc \
       postgresql-client \
       git \
       vim \
       && rm -rf /var/lib/apt/lists/*

   # Install Poetry
   RUN pip install poetry

   # Set working directory
   WORKDIR /app

   # Copy dependency files
   COPY pyproject.toml poetry.lock ./

   # Install ALL dependencies (including dev)
   RUN poetry config virtualenvs.create false \
       && poetry install --no-interaction --no-ansi

   # Copy application code
   COPY . .

   # Default to bash for development
   CMD ["/bin/bash"]
   ```

   `docker/docker-compose.yml`:
   ```yaml
   version: '3.8'

   services:
     postgres:
       image: postgres:16
       container_name: cria_postgres
       environment:
         POSTGRES_USER: cria_user
         POSTGRES_PASSWORD: cria_password
         POSTGRES_DB: cria_db
       ports:
         - "5432:5432"
       volumes:
         - postgres_data:/var/lib/postgresql/data
         - ./init.sql:/docker-entrypoint-initdb.d/init.sql
       healthcheck:
         test: ["CMD-SHELL", "pg_isready -U cria_user"]
         interval: 10s
         timeout: 5s
         retries: 5

     app:
       build:
         context: ..
         dockerfile: docker/Dockerfile.dev
       container_name: cria_app
       depends_on:
         postgres:
           condition: service_healthy
       environment:
         DATABASE_URL: postgresql://cria_user:cria_password@postgres:5432/cria_db
       volumes:
         - ..:/app
         - /app/.venv  # Don't mount venv
       ports:
         - "8000:8000"
       stdin_open: true
       tty: true

   volumes:
     postgres_data:
   ```

   `docker/init.sql`:
   ```sql
   -- Create test database
   CREATE DATABASE cria_test_db;
   GRANT ALL PRIVILEGES ON DATABASE cria_test_db TO cria_user;
   ```

7. **Create pytest configuration**

   `pytest.ini`:
   ```ini
   [pytest]
   testpaths = tests
   python_files = test_*.py
   python_classes = Test*
   python_functions = test_*

   # Markers
   markers =
       unit: Fast unit tests (no external dependencies)
       integration: Integration tests (database, API calls)
       slow: Tests that take > 10 seconds
       requires_db: Tests that require database connection
       requires_api: Tests that require external API calls

   # Coverage
   addopts =
       --verbose
       --strict-markers
       --tb=short

   # Test environment
   env =
       TEST_MODE=True
       LOG_LEVEL=DEBUG
   ```

8. **Update `.gitignore`**
   ```
   # Add to existing .gitignore
   .env
   postgres_data/
   poetry.lock
   .pytest_cache/
   .ruff_cache/
   .mypy_cache/
   alembic/versions/*.py  # except initial migration
   ```

**Deliverables**:
- ✅ Full directory structure created
- ✅ Poetry initialized with dependencies
- ✅ Configuration system (`settings.py`, `paths.py`)
- ✅ Docker environment ready
- ✅ Test configuration ready

---

### Phase 2: API Client Refactoring (3-4 hours)

**Goal**: Convert `utils_api.py` to OOP client classes

**Tasks**:

1. **Create base client** (`src/api/base_client.py`)
   ```python
   from typing import Optional
   import requests
   from requests.adapters import HTTPAdapter
   from urllib3.util.retry import Retry
   from src.utils.logger import logger

   class BaseAPIClient:
       """Base class for all API clients with retry logic"""

       def __init__(self, base_url: str, timeout: int = 30):
           self.base_url = base_url
           self.timeout = timeout
           self._session = self._create_session()

       def _create_session(self) -> requests.Session:
           """Create session with retry logic"""
           session = requests.Session()
           retry = Retry(
               total=3,
               backoff_factor=0.5,
               status_forcelist=[500, 502, 503, 504]
           )
           adapter = HTTPAdapter(max_retries=retry)
           session.mount("http://", adapter)
           session.mount("https://", adapter)
           return session

       def get(self, endpoint: str, params: Optional[dict] = None) -> requests.Response:
           """Make GET request with error handling"""
           url = f"{self.base_url}/{endpoint}"
           try:
               response = self._session.get(url, params=params, timeout=self.timeout)
               response.raise_for_status()
               return response
           except requests.exceptions.RequestException as e:
               logger.error(f"API request failed: {url}, Error: {e}")
               raise
   ```

2. **Create Census API client** (`src/api/census_client.py`)
   ```python
   from typing import List, Dict, Optional
   import json
   import pandas as pd
   from src.api.base_client import BaseAPIClient
   from src.config.settings import settings
   from src.utils.logger import logger

   class CensusAPIClient(BaseAPIClient):
       """Client for Census Bureau ACS API"""

       def __init__(self, api_key: Optional[str] = None):
           super().__init__(base_url="https://api.census.gov/data")
           self.api_key = api_key or settings.census_api_key
           self.year = settings.acs_year

       def build_acs_url(
           self,
           columns: List[str],
           geography: str = "county",
           year: Optional[int] = None
       ) -> str:
           """Build ACS API URL"""
           year = year or self.year

           # Determine table type from first column
           table_id = columns[0].split("_")[0]

           if table_id.startswith("B"):
               dataset = f"{year}/acs/acs5"
               get_param = "get"
           elif table_id.startswith("S"):
               dataset = f"{year}/acs/acs5/subject"
               get_param = "get"
           elif table_id.startswith("DP"):
               dataset = f"{year}/acs/acs5/profile"
               get_param = "get"
           elif table_id.startswith("CP"):
               dataset = f"{year}/acs/acs5/cprofile"
               get_param = "get"
           else:
               raise ValueError(f"Unknown table type: {table_id}")

           # Build variable list
           vars_str = "NAME,GEO_ID," + ",".join(columns)

           # Build geography predicate
           if geography == "county":
               geo_str = "county:*&in=state:*"
           elif geography == "tract":
               geo_str = "tract:*&in=state:*&in=county:*"
           elif geography == "state":
               geo_str = "state:*"
           else:
               raise ValueError(f"Unsupported geography: {geography}")

           url = (
               f"{self.base_url}/{dataset}?"
               f"{get_param}={vars_str}&for={geo_str}"
               f"&key={self.api_key}"
           )

           return url

       def fetch_acs_data(
           self,
           columns: List[str],
           geography: str = "county",
           year: Optional[int] = None
       ) -> pd.DataFrame:
           """Fetch ACS data and return as DataFrame"""
           url = self.build_acs_url(columns, geography, year)

           logger.info(f"Fetching ACS data: {columns[:3]}... ({len(columns)} cols)")

           response = self._session.get(url, timeout=self.timeout)
           response.raise_for_status()

           data = json.loads(response.text)
           df = pd.DataFrame(data=data[1:], columns=data[0])

           # Convert -666666666 to NaN (Census missing data code)
           for col in columns:
               if col in df.columns:
                   df[col] = pd.to_numeric(df[col], errors='coerce')
                   df.loc[df[col] == -666666666, col] = pd.NA

           # Set index
           df = df.set_index("GEO_ID").sort_index()

           return df
   ```

3. **Create CBP client** (`src/api/cbp_client.py`)
   ```python
   import json
   import pandas as pd
   from src.api.base_client import BaseAPIClient
   from src.config.settings import settings
   from src.utils.logger import logger

   class CBPClient(BaseAPIClient):
       """Client for Census Bureau County Business Patterns API"""

       def __init__(self, api_key: str = None):
           super().__init__(base_url="https://api.census.gov/data")
           self.api_key = api_key or settings.census_api_key
           self.cbp_year = settings.cbp_year
           self.naics_year = settings.naics_year

       def fetch_cbp_data(self, naics_code: int) -> pd.DataFrame:
           """Fetch CBP data for NAICS code"""
           logger.info(f"Fetching CBP data for NAICS {naics_code}")

           url = (
               f"{self.base_url}/{self.cbp_year}/cbp?"
               f"get=NAME,GEO_ID,NAICS{self.naics_year}_LABEL,ESTAB"
               f"&for=county:*&in=state:*"
               f"&NAICS{self.naics_year}={naics_code}"
               f"&key={self.api_key}"
           )

           response = self._session.get(url, timeout=self.timeout)
           response.raise_for_status()

           data = json.loads(response.text)
           df = pd.DataFrame(data=data[1:], columns=data[0])

           # Rename ESTAB column to NAICS code
           label = df[f"NAICS{self.naics_year}_LABEL"].iloc[0]
           df = df.rename(columns={"ESTAB": str(naics_code)})
           df[str(naics_code)] = pd.to_numeric(df[str(naics_code)], errors='coerce')

           # Fill NaN with 0 for CBP (missing = no establishments)
           df[str(naics_code)] = df[str(naics_code)].fillna(0)

           # Set index
           df = df.set_index("GEO_ID").sort_index()
           df = df.drop(columns=[f"NAICS{self.naics_year}_LABEL",
                                  f"NAICS{self.naics_year}",
                                  "state", "county", "NAME"])

           return df
   ```

4. **Create other external clients** (`src/api/external_clients.py`)
   - `EAVSClient` - Election Administration and Voting Survey
   - `ARDAClient` - Association of Religion Data Archives
   - `POPClient` - Population estimates and migration

5. **Write unit tests** for each client (`tests/unit/test_*_client.py`)

**Deliverables**:
- ✅ All API clients as classes
- ✅ Shared retry logic in base class
- ✅ Unit tests for each client
- ✅ API key from environment variables

---

### Phase 3: Core Logic Refactoring (4-5 hours)

**Goal**: Convert data pulling, indicator calculation, and aggregation to OOP

**Tasks**:

1. **Create DataPuller** (`src/core/data_puller.py`)
   ```python
   from typing import Optional, Dict
   import pandas as pd
   from src.api.census_client import CensusAPIClient
   from src.api.cbp_client import CBPClient
   from src.api.external_clients import EAVSClient, ARDAClient, POPClient
   from src.config.paths import paths
   from src.utils.logger import logger

   class DataPuller:
       """Orchestrates data collection from multiple sources"""

       def __init__(self, geography: str = "county"):
           self.geography = geography

           # Initialize clients
           self.census = CensusAPIClient()
           self.cbp = CBPClient()
           self.eavs = EAVSClient()
           self.arda = ARDAClient()
           self.pop = POPClient()

           # Load reference data
           self.reference = self._load_reference()
           self.years = self._load_years()

       def _load_reference(self) -> pd.DataFrame:
           """Load reference Excel file"""
           xl = pd.ExcelFile(paths.reference_file)
           ref = xl.parse("Status")
           ref = ref.dropna(subset=["Order_2023"], axis=0)
           ref = ref.sort_values("Order_2023")
           return ref

       def _load_years(self) -> Dict[str, int]:
           """Load year configuration"""
           xl = pd.ExcelFile(paths.reference_file)
           years_df = xl.parse("Years")
           return dict(zip(years_df.label, years_df.year_ref))

       def pull_all_data(self) -> pd.DataFrame:
           """Pull all CRIA source data"""
           logger.info(f"Starting data pull for {self.geography} level")

           data = pd.DataFrame()

           for idx, indicator in enumerate(self.reference['Indicator']):
               source = self.reference.loc[idx, 'Source']

               logger.info(f"[{idx}] {indicator} from {source}")

               if source == "ACS":
                   df = self._pull_acs_indicator(idx)
               elif source == "CBP":
                   df = self._pull_cbp_indicator(idx)
               elif source == "EAVS":
                   df = self._pull_eavs_indicator(idx)
               elif source == "ARDA":
                   df = self._pull_arda_indicator(idx)
               elif source == "POP":
                   df = self._pull_pop_indicator(idx)
               else:
                   logger.warning(f"Skipping {indicator}, unknown source: {source}")
                   continue

               # Merge into main dataframe
               if data.empty:
                   data = df
               else:
                   data = data.merge(df, left_index=True, right_index=True, how="outer")

           logger.info(f"Data pull complete. Shape: {data.shape}")
           return data

       def _pull_acs_indicator(self, idx: int) -> pd.DataFrame:
           """Pull single ACS indicator"""
           num = self.reference.loc[idx, 'numerator'].split(',')
           denom = self.reference.loc[idx, 'denominator']

           if isinstance(denom, str):
               denom = denom.split(',')
           else:
               denom = [denom]

           # Combine and clean columns
           cols = [c.strip() for c in num + denom if len(str(c)) > 6]

           return self.census.fetch_acs_data(cols, self.geography)

       # ... similar methods for CBP, EAVS, ARDA, POP
   ```

2. **Create IndicatorCalculator** (`src/core/indicators.py`)
   ```python
   from typing import Optional
   import pandas as pd
   import numpy as np
   from src.core.data_puller import DataPuller
   from src.utils.logger import logger

   class IndicatorCalculator:
       """Calculate CRIA indicators from source data"""

       def __init__(self, geography: str = "county"):
           self.geography = geography
           self.data_puller = DataPuller(geography)
           self.reference = self.data_puller.reference
           self.years = self.data_puller.years

       def calculate_all_indicators(
           self,
           source_data: Optional[pd.DataFrame] = None
       ) -> pd.DataFrame:
           """Calculate all indicators from source data"""
           if source_data is None:
               source_data = self.data_puller.pull_all_data()

           indicators = pd.DataFrame(index=source_data.index)

           for idx, indicator_name in enumerate(self.reference['Indicator']):
               function = self.reference.loc[idx, 'Function']

               logger.info(f"[{idx}] Calculating {indicator_name} ({function})")

               indicators[indicator_name] = self._calculate_indicator(
                   idx, source_data
               )

           return indicators

       def _calculate_indicator(
           self,
           idx: int,
           data: pd.DataFrame
       ) -> pd.Series:
           """Calculate single indicator based on function type"""
           function = self.reference.loc[idx, 'Function']

           if function == "divide":
               return self._divide_function(idx, data)
           elif function == "max":
               return self._max_function(idx, data)
           elif function == "mean":
               return self._mean_function(idx, data)
           elif function == "divide_scalar":
               return self._divide_scalar_function(idx, data)
           elif function == "reverse_divide":
               return self._reverse_divide_function(idx, data)
           else:
               logger.warning(f"Unknown function: {function}")
               return pd.Series(index=data.index, dtype=float)

       def _divide_function(self, idx: int, data: pd.DataFrame) -> pd.Series:
           """Numerator / Denominator"""
           num_cols = self._get_numerator_columns(idx)
           denom_col = self.reference.loc[idx, 'denominator']

           if isinstance(denom_col, str):
               result = data[num_cols].sum(axis=1) / data[denom_col]
               # Set to 0 where denominator is 0
               result.loc[data[denom_col] == 0] = 0
           else:
               result = data[num_cols].sum(axis=1) / denom_col

           # Set to NaN where numerator is missing
           result.loc[data[num_cols].isna().any(axis=1)] = np.nan

           return result

       # ... other function implementations
   ```

3. **Create AggregateIndicator** (`src/core/aggregator.py`)
   - Clean indicators
   - Scale and normalize
   - Bin into classes
   - Aggregate into final index

4. **Create BinningEngine** (`src/core/binning.py`)
   - Wrapper around mapclassify
   - Support multiple binning strategies

5. **Create transformations module** (`src/core/transformations.py`)
   - `clean_series()`, `calc_z_scores()`, `center_scale()`, etc.

6. **Write tests** for each core module

**Deliverables**:
- ✅ OOP core workflow (DataPuller, IndicatorCalculator, AggregateIndicator)
- ✅ All functions refactored to methods
- ✅ Unit tests for each class
- ✅ Integration test for full workflow

---

### Phase 4: Database Migration (5-6 hours)

**Goal**: Replace Excel outputs with PostgreSQL database

**Database Schema Design**:

See separate document: `docs/20251030_DATABASE_SCHEMA.md`

**Key Tables**:
1. `geographies` - Geographic reference data (counties, tracts, states, tribes)
2. `reference_indicators` - Indicator definitions from Excel
3. `source_data` - Raw data from APIs
4. `indicators` - Calculated indicators
5. `aggregate_indicators` - Final aggregated scores
6. `data_years` - Year tracking for reproducibility

**Tasks**:

1. **Create SQLAlchemy models** (`src/db/models.py`)
2. **Create database session management** (`src/db/session.py`)
3. **Create repositories** (`src/db/repositories.py`)
4. **Initialize Alembic** and create initial migration
5. **Create import script** to load reference Excel into database
6. **Update core classes** to use database instead of Excel
7. **Create export script** for Excel reports (legacy compatibility)

**Deliverables**:
- ✅ Full database schema
- ✅ Alembic migrations
- ✅ Repository pattern for data access
- ✅ Import/export scripts
- ✅ Database tests

---

### Phase 5: Docker Environment (2-3 hours)

**Goal**: Containerized development and production environments

**Tasks**:

1. **Test Docker Compose setup**
   ```bash
   cd docker
   docker-compose up -d
   docker-compose exec app poetry run pytest
   ```

2. **Create development workflow documentation** (`docs/20251030_DOCKER_GUIDE.md`)

3. **Create database initialization scripts**

4. **Test full workflow in Docker**

**Deliverables**:
- ✅ Working Docker environment
- ✅ Docker documentation
- ✅ Database persists between restarts

---

### Phase 6: Testing Suite (3-4 hours)

**Goal**: Comprehensive test coverage following C3PO guide

**Tasks**:

1. **Create unit tests** (fast, isolated)
   - Test each API client
   - Test each core class
   - Test transformations/utilities

2. **Create integration tests** (multi-component)
   - Test full workflow (pull → calculate → aggregate)
   - Test database operations
   - Test API error handling

3. **Create fixtures** (`tests/fixtures/`)
   - Sample reference data
   - Sample API responses
   - Sample database records

4. **Create test runner script** (`scripts/run_tests.sh`)
   ```bash
   #!/bin/bash

   case "$1" in
       unit)
           pytest -m unit -v
           ;;
       integration)
           pytest -m integration -v
           ;;
       coverage)
           pytest --cov=src --cov-report=html --cov-report=term
           ;;
       all)
           pytest -v
           ;;
       *)
           echo "Usage: ./run_tests.sh {unit|integration|coverage|all}"
           exit 1
           ;;
   esac
   ```

5. **Achieve coverage targets**
   - Core modules: > 80%
   - Utilities: > 70%
   - Overall: > 60%

**Deliverables**:
- ✅ Comprehensive test suite
- ✅ Test documentation
- ✅ Coverage reports
- ✅ CI/CD ready

---

### Phase 7: Migration & Cleanup (2-3 hours)

**Goal**: Move old code, update documentation, validate everything works

**Tasks**:

1. **Move deprecated files**
   ```bash
   mv fps_tier_subtask_BERT.py deprecated/
   mv fema_broadband.py deprecated/
   mv bin_local_data.py deprecated/
   # ... etc (all non-workflow files)
   ```

2. **Create executable scripts** (`scripts/`)
   - `run_county_workflow.py`
   - `run_tract_workflow.py`
   - `run_tribal_workflow.py`
   - `import_reference_data.py`
   - `export_to_excel.py`

3. **Update main README.md**
   - New architecture diagram
   - Docker setup instructions
   - Usage examples
   - Testing instructions

4. **Update `docs/CLAUDE.md`** with new conventions

5. **Create session documentation** (`docs/20251030_SESSION_NOTES.md`)

6. **Validation**
   - Run full workflow (county, tract, tribal)
   - Compare outputs to old system
   - Run all tests
   - Generate coverage report

**Deliverables**:
- ✅ Clean repository structure
- ✅ All deprecated code moved
- ✅ Complete documentation
- ✅ Validated outputs match original

---

## Database Schema Design

See full schema in: `docs/20251030_DATABASE_SCHEMA.md`

**Core tables summary**:

```sql
-- Geographic reference data
geographies (id, geo_id, name, level, state, county, tract, ...)

-- Indicator definitions (from Excel reference)
reference_indicators (id, name, source, function, numerator, denominator, ...)

-- Raw source data from APIs
source_data (id, geo_id, indicator_id, year, value, label, ...)

-- Calculated indicators
indicators (id, geo_id, indicator_id, year, value, ...)

-- Aggregated scores
aggregate_indicators (id, geo_id, year, aggregate_score, bin, ...)

-- Year tracking
data_years (id, source, year, last_updated, ...)
```

**Indexes for performance**:
- `geo_id` on all tables
- `indicator_id` on source_data, indicators
- Composite index on (geo_id, year)

---

## Docker Architecture

### Services

**Development (`docker-compose.yml`)**:
- `postgres` - PostgreSQL 16 database
- `app` - Python application (development mode)

**Production** (future):
- `postgres` - PostgreSQL 16 database
- `app` - Python application (production mode)
- `nginx` - Reverse proxy (if API endpoints added)

### Volumes

- `postgres_data` - Persistent database storage
- `./:/app` - Live code mounting (dev only)

### Environment Variables

Passed from `.env` file to containers

### Usage

```bash
# Start services
docker-compose up -d

# Run workflow
docker-compose exec app poetry run python scripts/run_county_workflow.py

# Run tests
docker-compose exec app poetry run pytest

# View logs
docker-compose logs -f app

# Access database
docker-compose exec postgres psql -U cria_user -d cria_db

# Stop services
docker-compose down

# Reset database
docker-compose down -v
docker-compose up -d
```

---

## Testing Strategy

### Test Organization (following C3PO guide)

```
tests/
├── unit/              # Fast, isolated tests (< 1 second each)
├── integration/       # Multi-component tests (may be slower)
├── fixtures/          # Reusable test data
└── conftest.py        # Shared pytest configuration
```

### Test Markers

```python
@pytest.mark.unit              # Fast unit test
@pytest.mark.integration       # Integration test
@pytest.mark.slow              # Takes > 10 seconds
@pytest.mark.requires_db       # Needs database
@pytest.mark.requires_api      # Makes external API calls
```

### AAA Pattern (Arrange-Act-Assert)

All tests follow this pattern:

```python
def test_calculate_poverty_indicator():
    # ARRANGE - Set up test data
    data = pd.DataFrame({
        'B17001_002E': [100, 200],
        'B17001_001E': [1000, 2000]
    })
    calculator = IndicatorCalculator()

    # ACT - Execute the function
    result = calculator._divide_function(0, data)

    # ASSERT - Verify results
    assert result[0] == 0.1  # 100/1000
    assert result[1] == 0.1  # 200/2000
```

### Coverage Targets

- **Core modules** (`src/core/`): > 80%
- **API clients** (`src/api/`): > 70%
- **Utilities** (`src/utils/`): > 70%
- **Overall project**: > 60%

### Running Tests

```bash
# All tests
pytest

# Unit tests only (fast)
pytest -m unit

# Integration tests
pytest -m integration

# With coverage
pytest --cov=src --cov-report=html

# Specific test file
pytest tests/unit/test_indicators.py -v

# Watch mode (requires pytest-watch)
ptw
```

---

## Migration Strategy

### From Functional to OOP

**Step 1**: Create OOP classes that wrap existing functions
**Step 2**: Test OOP implementation against functional implementation
**Step 3**: Switch main scripts to use OOP classes
**Step 4**: Move functional code to `deprecated/`

### From Excel to Database

**Step 1**: Keep Excel as source of truth initially
**Step 2**: Import Excel data to database on each run
**Step 3**: Verify database outputs match Excel outputs
**Step 4**: Switch to database as source of truth
**Step 5**: Keep Excel export for compatibility

### From Conda to Poetry/Docker

**Step 1**: Document current conda environment
**Step 2**: Create equivalent `pyproject.toml`
**Step 3**: Test in Docker with Poetry
**Step 4**: Update documentation to recommend Docker
**Step 5**: Keep conda instructions as legacy option

---

## Timeline & Effort Estimates

### Detailed Breakdown

| Phase | Tasks | Estimated Hours | Dependencies |
|-------|-------|-----------------|--------------|
| **1. Foundation** | Directory structure, .env, paths, Docker setup | 2-3 | None |
| **2. API Clients** | Refactor utils_api.py to classes | 3-4 | Phase 1 |
| **3. Core Logic** | DataPuller, Indicators, Aggregator | 4-5 | Phase 2 |
| **4. Database** | Models, migrations, repositories | 5-6 | Phase 1 |
| **5. Docker** | Test containers, documentation | 2-3 | Phases 1, 4 |
| **6. Testing** | Unit tests, integration tests, fixtures | 3-4 | Phases 2, 3 |
| **7. Migration** | Move deprecated, scripts, docs | 2-3 | All previous |

**Total Estimated Time**: 21-28 hours

### Recommended Schedule

**Week 1** (10-12 hours):
- Phase 1: Foundation (2-3 hrs)
- Phase 2: API Clients (3-4 hrs)
- Phase 3: Core Logic (4-5 hrs)

**Week 2** (10-12 hours):
- Phase 4: Database (5-6 hrs)
- Phase 5: Docker (2-3 hrs)
- Phase 6: Testing (3-4 hrs)

**Week 3** (2-3 hours):
- Phase 7: Migration & Cleanup (2-3 hrs)

### Milestones

✅ **Milestone 1** (End of Phase 3): OOP workflow complete, tested against old system
✅ **Milestone 2** (End of Phase 4): Database operational, can store/retrieve data
✅ **Milestone 3** (End of Phase 6): Full test suite passing, > 60% coverage
✅ **Milestone 4** (End of Phase 7): Production ready, documentation complete

---

## Critical Success Factors

1. ✅ **Backward compatibility** - Can still export to Excel for legacy users
2. ✅ **Test coverage** - Validate new implementation matches old outputs
3. ✅ **Documentation** - Clear instructions for Docker, testing, database
4. ✅ **Incremental migration** - Don't break existing workflow during refactor
5. ✅ **Environment consistency** - Docker ensures reproducibility

---

## Next Steps

1. **Review this plan** - Get approval/feedback from stakeholder
2. **Create `.env` file** - Add Census API key and configuration
3. **Start Phase 1** - Begin with foundation (directories, config, Docker)
4. **Iterative development** - Complete one phase, test, then move to next
5. **Document as we go** - Keep session notes in `docs/yyyymmdd_*.md`

---

## Questions & Decisions Log

**Q1**: Should we support both SQLite (local testing) and PostgreSQL (production)?
**A1**: TBD - PostgreSQL only for now, can add SQLite later if needed

**Q2**: How to handle API rate limiting?
**A2**: Existing retry logic sufficient for now, can add caching layer later

**Q3**: Should we parallelize API calls?
**A3**: Not in initial refactor, keep sequential for simplicity

**Q4**: Export format - Excel only or also CSV/JSON?
**A4**: Excel for now (legacy compatibility), can add others later

---

## References

- [MAUT System Structure](README.md) - Professional project organization
- [Claude Code Session Rules](CLAUDE.md) - Development standards
- [Testing Guide](20251023_TESTING_GUIDE.md) - Testing philosophy and patterns
- [Poetry Documentation](https://python-poetry.org/docs/)
- [SQLAlchemy 2.0 Documentation](https://docs.sqlalchemy.org/en/20/)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [pytest Documentation](https://docs.pytest.org/)

---

**Document Version**: 1.0
**Last Updated**: 2025-10-30
**Author**: Planning session with Claude Code
**Status**: Ready for implementation ✅
