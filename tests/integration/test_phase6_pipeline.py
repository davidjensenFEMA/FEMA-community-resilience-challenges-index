"""
Integration test for Phase 6: Complete pipeline with database integration.

Tests the full workflow with database storage:
1. Import reference data
2. Create sample geographies
3. Pull data (mock/sample) → Store in database
4. Calculate indicators → Store in database
5. Create aggregates → Store in database
6. Verify all data in database

This demonstrates the complete end-to-end flow through database layer.
"""

import pytest
import pandas as pd
import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.db.models import Base
from src.db.repositories import (
    GeographyRepository, ReferenceIndicatorRepository,
    SourceDataRepository, IndicatorRepository, AggregateIndicatorRepository
)
from src.core.data_puller import DataPuller
from src.core.indicators import IndicatorCalculator
from src.core.aggregator import AggregateIndicator


@pytest.fixture(scope="function")
def db_session():
    """Create test database session using in-memory SQLite."""
    engine = create_engine(
        'sqlite:///:memory:',
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestSessionLocal()
    yield session
    session.close()


def setup_reference_data(db_session):
    """Setup reference indicators in database."""
    ref_repo = ReferenceIndicatorRepository(db_session)

    indicators = [
        {
            "indicator_name": "Poverty",
            "source": "ACS",
            "function": "divide",
            "numerator": "B17001_002E",
            "denominator": "B17001_001E",
            "order_2023": 1,
            "is_active": True
        },
        {
            "indicator_name": "Unemployment",
            "source": "ACS",
            "function": "divide",
            "numerator": "DP03_0005E",
            "denominator": "DP03_0003E",
            "order_2023": 2,
            "is_active": True
        },
        {
            "indicator_name": "Education",
            "source": "ACS",
            "function": "divide",
            "numerator": "S1501_C01_007E",
            "denominator": "S1501_C01_006E",
            "order_2023": 3,
            "is_active": True
        }
    ]

    ref_repo.bulk_create(indicators)
    db_session.commit()


def setup_geographies(db_session):
    """Setup sample geographies in database."""
    geo_repo = GeographyRepository(db_session)

    geographies = [
        {
            "geo_id": "01001",
            "name": "Autauga County, AL",
            "geography_level": "county",
            "state_code": "01",
            "state_name": "Alabama",
            "population": 58805
        },
        {
            "geo_id": "01003",
            "name": "Baldwin County, AL",
            "geography_level": "county",
            "state_code": "01",
            "state_name": "Alabama",
            "population": 231767
        },
        {
            "geo_id": "01005",
            "name": "Barbour County, AL",
            "geography_level": "county",
            "state_code": "01",
            "state_name": "Alabama",
            "population": 25223
        }
    ]

    geo_repo.bulk_create(geographies)
    db_session.commit()

    return ["01001", "01003", "01005"]


def create_mock_source_data(geo_ids):
    """Create mock source data DataFrame (simulates API response)."""
    data = pd.DataFrame(index=geo_ids)

    # Poverty indicator (numerator and denominator)
    data["B17001_002E"] = [8820, 34765, 3783]  # People in poverty
    data["B17001_001E"] = [58805, 231767, 25223]  # Total population

    # Unemployment indicator
    data["DP03_0005E"] = [1470, 5794, 631]  # Unemployed
    data["DP03_0003E"] = [29403, 115884, 12612]  # In labor force

    # Education indicator
    data["S1501_C01_007E"] = [5880, 23177, 2522]  # Bachelor's or higher
    data["S1501_C01_006E"] = [39203, 154513, 16815]  # 25 years and over

    return data


def test_complete_phase6_pipeline(db_session):
    """
    Test complete Phase 6 pipeline with database integration.

    This is the main integration test showing:
    1. Setup reference data and geographies
    2. Mock data pull → Save to database
    3. Calculate indicators → Save to database
    4. Create aggregates → Save to database
    5. Verify all data stored correctly
    """
    print("\n" + "="*80)
    print("PHASE 6: COMPLETE PIPELINE TEST")
    print("="*80)

    # ==========================================
    # STEP 1: Setup reference data
    # ==========================================
    print("\n[1] Setting up reference data...")
    setup_reference_data(db_session)

    ref_repo = ReferenceIndicatorRepository(db_session)
    all_indicators = ref_repo.get_all()
    assert len(all_indicators) == 3
    print(f"✓ Created {len(all_indicators)} reference indicators")

    # ==========================================
    # STEP 2: Setup geographies
    # ==========================================
    print("\n[2] Setting up geographies...")
    geo_ids = setup_geographies(db_session)

    geo_repo = GeographyRepository(db_session)
    # Get all created geographies
    all_geos = [geo_repo.get_by_geo_id(gid) for gid in geo_ids]
    assert len(all_geos) == 3
    assert all(g is not None for g in all_geos)
    print(f"✓ Created {len(all_geos)} geographies")

    # ==========================================
    # STEP 3: Mock data pull and save to database
    # ==========================================
    print("\n[3] Pulling source data and saving to database...")

    # Create mock source data (in real scenario, DataPuller.pull_all_data() would call APIs)
    source_data = create_mock_source_data(geo_ids)

    # Create DataPuller with database session
    puller = DataPuller(geography="county", db=db_session)

    # Save source data to database
    puller.save_to_database(source_data, year=2021, db=db_session)

    # Verify source data saved
    source_repo = SourceDataRepository(db_session)
    all_source = source_repo.get_for_geography(all_geos[0].id, 2021)
    assert len(all_source) > 0
    print(f"✓ Saved source data records")

    # ==========================================
    # STEP 4: Calculate indicators and save to database
    # ==========================================
    print("\n[4] Calculating indicators and saving to database...")

    # Create IndicatorCalculator with database session
    calculator = IndicatorCalculator(geography="county", db=db_session)

    # IMPORTANT: Create mock reference that matches our mock data
    # (In real scenario, reference would match the pulled data)
    mock_reference = pd.DataFrame([
        {
            "Indicator": "Poverty",
            "Function": "divide",
            "numerator": "B17001_002E",
            "denominator": "B17001_001E"
        },
        {
            "Indicator": "Unemployment",
            "Function": "divide",
            "numerator": "DP03_0005E",
            "denominator": "DP03_0003E"
        },
        {
            "Indicator": "Education",
            "Function": "divide",
            "numerator": "S1501_C01_007E",
            "denominator": "S1501_C01_006E"
        }
    ])
    calculator.reference = mock_reference

    # Calculate indicators from source data
    indicators = calculator.calculate_all_indicators(source_data=source_data)

    # Verify calculated correctly
    assert "Poverty" in indicators.columns
    assert "Unemployment" in indicators.columns
    assert "Education" in indicators.columns
    assert len(indicators) == 3

    # Save indicators to database
    calculator.save_to_database(indicators, year=2021, db=db_session)

    # Verify indicators saved
    ind_repo = IndicatorRepository(db_session)
    saved_indicators = ind_repo.get_for_geography(all_geos[0].id, 2021)
    assert len(saved_indicators) == 3
    print(f"✓ Saved {len(indicators) * 3} indicator records (3 geos × 3 indicators)")

    # ==========================================
    # STEP 5: Create aggregates and save to database
    # ==========================================
    print("\n[5] Creating aggregates and saving to database...")

    # Create AggregateIndicator with database session
    aggregator = AggregateIndicator(geography="county", bins=5, db=db_session)

    # Create aggregate scores - use filtered reference
    reference_df = calculator.reference  # Use filtered reference
    results = aggregator.create_aggregate(
        indicators=indicators,
        reference=reference_df,
        bin_indicators=True
    )

    # Verify aggregates created
    agg_df = results["agg"]
    assert len(agg_df) == 3
    assert "cria_score" in agg_df.columns or "cria_p" in agg_df.columns

    # Save aggregates to database
    aggregator.save_to_database(results, year=2021, db=db_session)

    # Verify aggregates saved
    agg_repo = AggregateIndicatorRepository(db_session)
    saved_aggregates = agg_repo.get_all_for_year(2021)
    assert len(saved_aggregates) == 3
    print(f"✓ Saved {len(saved_aggregates)} aggregate records")

    # ==========================================
    # STEP 6: Verify complete data flow
    # ==========================================
    print("\n[6] Verifying complete data flow...")

    # Query for a specific geography
    geo = geo_repo.get_by_geo_id("01001")
    assert geo is not None

    # Verify source data exists
    source_records = source_repo.get_for_geography(geo.id, 2021)
    assert len(source_records) > 0
    print(f"  ✓ Geography 01001 has {len(source_records)} source data records")

    # Verify indicators exist
    indicator_records = ind_repo.get_for_geography(geo.id, 2021)
    assert len(indicator_records) == 3
    print(f"  ✓ Geography 01001 has {len(indicator_records)} indicator records")

    # Verify aggregate exists
    aggregate = agg_repo.get_for_geography(geo.id, 2021)
    assert aggregate is not None
    print(f"  ✓ Geography 01001 has aggregate score")

    # Verify relationships work
    assert aggregate.geography.name == "Autauga County, AL"
    print(f"  ✓ Relationship: aggregate → geography works")

    # ==========================================
    # SUCCESS
    # ==========================================
    print("\n" + "="*80)
    print("PHASE 6 PIPELINE TEST: SUCCESS")
    print("="*80)
    print("Complete data flow verified:")
    print(f"  • {len(all_indicators)} reference indicators")
    print(f"  • {len(all_geos)} geographies")
    print(f"  • Source data → Database")
    print(f"  • {len(indicators) * 3} indicators → Database")
    print(f"  • {len(saved_aggregates)} aggregates → Database")
    print("="*80)


def test_pipeline_without_database(db_session):
    """
    Test that pipeline still works WITHOUT database (backward compatibility).

    This ensures existing code that doesn't use database continues to work.
    """
    print("\n" + "="*80)
    print("BACKWARD COMPATIBILITY TEST (No Database)")
    print("="*80)

    # Create mock data
    geo_ids = ["01001", "01003", "01005"]
    source_data = create_mock_source_data(geo_ids)

    # Create classes WITHOUT database session
    puller = DataPuller(geography="county")  # No db parameter
    calculator = IndicatorCalculator(geography="county")  # No db parameter
    aggregator = AggregateIndicator(geography="county", bins=5)  # No db parameter

    # Calculate indicators (should work without database)
    indicators = calculator.calculate_all_indicators(source_data=source_data)

    assert "Poverty" in indicators.columns
    assert len(indicators) == 3

    # Create aggregates (should work without database)
    reference_df = puller.reference
    results = aggregator.create_aggregate(
        indicators=indicators,
        reference=reference_df,
        bin_indicators=True
    )

    assert "agg" in results
    assert len(results["agg"]) == 3

    print("✓ Pipeline works without database")
    print("✓ Backward compatibility maintained")
    print("="*80)


def test_pipeline_multi_year_data(db_session):
    """Test pipeline with data from multiple years."""
    print("\n" + "="*80)
    print("MULTI-YEAR DATA TEST")
    print("="*80)

    # Setup
    setup_reference_data(db_session)
    geo_ids = setup_geographies(db_session)

    # Create data for multiple years
    for year in [2019, 2020, 2021]:
        print(f"\n  Processing year {year}...")

        # Mock data
        source_data = create_mock_source_data(geo_ids)

        # Pull → Calculate → Aggregate with database
        puller = DataPuller(geography="county", db=db_session)
        calculator = IndicatorCalculator(geography="county", db=db_session)
        aggregator = AggregateIndicator(geography="county", bins=5, db=db_session)

        # Save source data
        puller.save_to_database(source_data, year=year, db=db_session)

        # Calculate and save indicators
        indicators = calculator.calculate_all_indicators(source_data=source_data)
        calculator.save_to_database(indicators, year=year, db=db_session)

        # Create and save aggregates
        results = aggregator.create_aggregate(indicators, puller.reference)
        aggregator.save_to_database(results, year=year, db=db_session)

        print(f"    ✓ Year {year} complete")

    # Verify all years saved
    agg_repo = AggregateIndicatorRepository(db_session)
    for year in [2019, 2020, 2021]:
        year_aggregates = agg_repo.get_all_for_year(year)
        assert len(year_aggregates) == 3
        print(f"  ✓ Year {year}: {len(year_aggregates)} aggregates")

    print("\n✓ Multi-year data handling works correctly")
    print("="*80)
