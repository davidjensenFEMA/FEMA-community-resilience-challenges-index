"""
Pytest configuration and shared fixtures.

This file is automatically loaded by pytest and makes fixtures
available to all test files without importing.
"""

import os
import sys
from pathlib import Path
from typing import Generator

import pytest
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# Add src to Python path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import after path is set
from src.config.settings import settings
from src.config.paths import paths


# =============================================================================
# Session-scoped Fixtures (run once per test session)
# =============================================================================

@pytest.fixture(scope="session")
def test_database_url() -> str:
    """Get test database URL from settings"""
    if settings.test_database_url:
        return settings.test_database_url
    # Fallback for when .env doesn't exist yet
    return "postgresql://cria_user:cria_password@localhost:5432/cria_test_db"


@pytest.fixture(scope="session")
def test_engine(test_database_url):
    """Create SQLAlchemy engine for test database (session-scoped)"""
    from src.db.models import Base

    engine = create_engine(test_database_url, echo=False)

    # Create all tables
    Base.metadata.create_all(engine)

    yield engine

    # Drop all tables after tests
    Base.metadata.drop_all(engine)
    engine.dispose()


# =============================================================================
# Function-scoped Fixtures (run once per test function)
# =============================================================================

@pytest.fixture
def db_session(test_engine) -> Generator[Session, None, None]:
    """
    Create a clean database session for each test.

    Automatically rolls back changes after each test to keep tests isolated.
    """
    connection = test_engine.connect()
    transaction = connection.begin()

    SessionLocal = sessionmaker(bind=connection)
    session = SessionLocal()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def sample_reference_data() -> pd.DataFrame:
    """Sample reference indicator data for testing"""
    return pd.DataFrame({
        'Indicator': ['Poverty', 'GINI', 'Unemployment'],
        'Source': ['ACS', 'ACS', 'ACS'],
        'Function': ['divide', 'divide', 'divide'],
        'numerator': ['B17001_002E', 'B19083_001E', 'B23025_005E'],
        'denominator': ['B17001_001E', '1', 'B23025_002E'],
        'Order_2023': [1, 2, 3],
    })


@pytest.fixture
def sample_acs_data() -> pd.DataFrame:
    """Sample ACS data for testing"""
    return pd.DataFrame({
        'GEO_ID': ['0500000US01001', '0500000US01003'],
        'NAME': ['Autauga County, Alabama', 'Baldwin County, Alabama'],
        'B17001_002E': [5000, 8000],   # Poverty count
        'B17001_001E': [55000, 200000], # Total population
        'B19083_001E': [0.45, 0.42],    # GINI
    }).set_index('GEO_ID')


@pytest.fixture
def sample_geography_data() -> pd.DataFrame:
    """Sample geography reference data"""
    return pd.DataFrame({
        'GEO_ID': ['0500000US01001', '0500000US01003'],
        'NAME': ['Autauga County, Alabama', 'Baldwin County, Alabama'],
        'state': [1, 1],
        'county': [1, 3],
        'state_name': ['Alabama', 'Alabama'],
        'state_abbr': ['AL', 'AL'],
        'county_name': ['Autauga County', 'Baldwin County'],
        'region': ['South', 'South'],
    }).set_index('GEO_ID')


@pytest.fixture
def sample_years() -> dict:
    """Sample years configuration"""
    return {
        'acs': 2021,
        'cbp': 2020,
        'naics': 2017,
        'pop': 2020,
        'asarb': 2020,
        'acs_labels': 2020,
    }


# =============================================================================
# Mock Fixtures
# =============================================================================

@pytest.fixture
def mock_census_api_response():
    """Mock Census API response"""
    return [
        ['NAME', 'GEO_ID', 'B01001_001E', 'state', 'county'],
        ['Autauga County, Alabama', '0500000US01001', '55000', '01', '001'],
        ['Baldwin County, Alabama', '0500000US01003', '200000', '01', '003'],
    ]


@pytest.fixture
def temp_output_dir(tmp_path):
    """Create temporary output directory for testing"""
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    return output_dir


@pytest.fixture
def temp_data_dir(tmp_path):
    """Create temporary data directory for testing"""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    return data_dir


# =============================================================================
# Pytest Hooks
# =============================================================================

def pytest_configure(config):
    """Configure pytest environment"""
    # Set test mode
    os.environ['TEST_MODE'] = 'True'
    os.environ['LOG_LEVEL'] = 'DEBUG'


def pytest_collection_modifyitems(config, items):
    """
    Auto-mark tests based on their location.

    Tests in tests/unit/ get @pytest.mark.unit
    Tests in tests/integration/ get @pytest.mark.integration
    """
    for item in items:
        # Get test file path relative to tests/
        rel_path = Path(item.fspath).relative_to(Path(__file__).parent)

        # Auto-mark by directory
        if 'unit' in rel_path.parts:
            item.add_marker(pytest.mark.unit)
        elif 'integration' in rel_path.parts:
            item.add_marker(pytest.mark.integration)
        elif 'smoke' in rel_path.parts:
            item.add_marker(pytest.mark.smoke)
        elif 'calibration' in rel_path.parts:
            item.add_marker(pytest.mark.calibration)


# =============================================================================
# Example Usage in Tests
# =============================================================================
"""
# Example test using fixtures:

def test_something(db_session, sample_reference_data):
    # db_session is a clean database session
    # sample_reference_data is a DataFrame with test data

    # Your test code here
    assert sample_reference_data.shape[0] == 3

# Example test with markers:

@pytest.mark.unit
def test_fast_unit_test():
    # Fast test, no external dependencies
    pass

@pytest.mark.integration
@pytest.mark.requires_db
def test_database_integration(db_session):
    # Test that uses database
    pass

@pytest.mark.slow
@pytest.mark.requires_api
def test_api_call():
    # Test that makes real API calls
    pass
"""
