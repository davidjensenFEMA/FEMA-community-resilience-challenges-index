"""
Integration test for complete database workflow.

Tests the full workflow:
1. Import reference data
2. Create geographies
3. Store source data
4. Calculate and store indicators
5. Create aggregate indicators
6. Query results

This test demonstrates a complete end-to-end flow through the database layer.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from src.db.models import (
    Base, Geography, ReferenceIndicator, DataYear,
    SourceData, Indicator, AggregateIndicator
)
from src.db.repositories import (
    GeographyRepository, ReferenceIndicatorRepository,
    SourceDataRepository, IndicatorRepository, AggregateIndicatorRepository
)


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


def test_complete_workflow(db_session):
    """Test complete database workflow from reference data to aggregates."""

    # ===========================================================================
    # STEP 1: Import reference data
    # ===========================================================================
    ref_repo = ReferenceIndicatorRepository(db_session)

    # Create reference indicators
    poverty_indicator = ref_repo.create(
        indicator_name="Poverty Rate",
        source="ACS",
        function="divide",
        numerator="B17001_002E",
        denominator="B17001_001E",
        order_2023=1,
        is_active=True
    )

    unemployment_indicator = ref_repo.create(
        indicator_name="Unemployment Rate",
        source="ACS",
        function="divide",
        numerator="DP03_0005E",
        denominator="DP03_0003E",
        order_2023=2,
        is_active=True
    )

    education_indicator = ref_repo.create(
        indicator_name="Education",
        source="ACS",
        function="divide",
        numerator="S1501_C01_007E",
        denominator="S1501_C01_006E",
        order_2023=3,
        is_active=True
    )

    db_session.commit()

    # Verify reference indicators created
    all_indicators = ref_repo.get_all()
    assert len(all_indicators) == 3

    # ===========================================================================
    # STEP 2: Create geographies
    # ===========================================================================
    geo_repo = GeographyRepository(db_session)

    # Create multiple geographies
    counties = [
        {
            "geo_id": "01001",
            "name": "Autauga County",
            "geography_level": "county",
            "state_code": "01",
            "state_name": "Alabama",
            "population": 58805
        },
        {
            "geo_id": "01003",
            "name": "Baldwin County",
            "geography_level": "county",
            "state_code": "01",
            "state_name": "Alabama",
            "population": 231767
        },
        {
            "geo_id": "01005",
            "name": "Barbour County",
            "geography_level": "county",
            "state_code": "01",
            "state_name": "Alabama",
            "population": 25223
        }
    ]

    created_geos = geo_repo.bulk_create(counties)
    db_session.commit()

    assert len(created_geos) == 3

    # ===========================================================================
    # STEP 3: Store source data (raw API data)
    # ===========================================================================
    source_repo = SourceDataRepository(db_session)

    # Simulate raw data from Census API for poverty indicator
    source_data = []
    for geo in created_geos:
        # Numerator (people in poverty)
        source_data.append({
            "geography_id": geo.id,
            "indicator_id": poverty_indicator.id,
            "column_name": "B17001_002E",
            "value": geo.population * 0.15,  # Simulate 15% poverty
            "year": 2021,
            "is_imputed": False
        })
        # Denominator (total population)
        source_data.append({
            "geography_id": geo.id,
            "indicator_id": poverty_indicator.id,
            "column_name": "B17001_001E",
            "value": float(geo.population),
            "year": 2021,
            "is_imputed": False
        })

    num_sources = source_repo.bulk_create(source_data)
    db_session.commit()

    assert num_sources == 6  # 3 counties * 2 columns

    # ===========================================================================
    # STEP 4: Calculate and store indicators
    # ===========================================================================
    ind_repo = IndicatorRepository(db_session)

    # Calculate indicators from source data
    indicators = []
    for geo in created_geos:
        # Poverty rate (0.15 for all in this test)
        indicators.append({
            "geography_id": geo.id,
            "indicator_id": poverty_indicator.id,
            "value": 0.15,
            "year": 2021,
            "is_clean": True
        })
        # Unemployment rate (varying)
        indicators.append({
            "geography_id": geo.id,
            "indicator_id": unemployment_indicator.id,
            "value": 0.05 + (geo.id % 3) * 0.02,  # Varies: 0.05, 0.07, 0.09
            "year": 2021,
            "is_clean": True
        })
        # Education (varying)
        indicators.append({
            "geography_id": geo.id,
            "indicator_id": education_indicator.id,
            "value": 0.25 + (geo.id % 3) * 0.05,  # Varies: 0.25, 0.30, 0.35
            "year": 2021,
            "is_clean": True
        })

    num_indicators = ind_repo.bulk_create(indicators)
    db_session.commit()

    assert num_indicators == 9  # 3 counties * 3 indicators

    # Verify we can query indicators for a geography
    autauga_indicators = ind_repo.get_for_geography(created_geos[0].id, 2021)
    assert len(autauga_indicators) == 3

    # ===========================================================================
    # STEP 5: Create aggregate indicators (CRIA scores)
    # ===========================================================================
    agg_repo = AggregateIndicatorRepository(db_session)

    # Calculate aggregate scores
    aggregates = []
    for i, geo in enumerate(created_geos):
        # Simulate aggregate CRIA score calculation
        # (in reality, this would use AggregateIndicator.create_aggregate)
        aggregate_score = 0.6 + i * 0.05  # Scores: 0.60, 0.65, 0.70
        percentile = 0.5 + i * 0.15  # Percentiles: 0.50, 0.65, 0.80
        bin_class = i + 3  # Bins: 3, 4, 5

        aggregates.append({
            "geography_id": geo.id,
            "year": 2021,
            "aggregate_score": aggregate_score,
            "z_score": (aggregate_score - 0.65) / 0.05,
            "percentile": percentile,
            "bin_class": bin_class,
            "num_indicators_used": 3,
            "num_indicators_missing": 0,
            "imputation_rate": 0.0
        })

    num_aggregates = agg_repo.bulk_create(aggregates)
    db_session.commit()

    assert num_aggregates == 3

    # ===========================================================================
    # STEP 6: Query results
    # ===========================================================================

    # Query all aggregates for 2021
    all_aggregates = agg_repo.get_all_for_year(2021)
    assert len(all_aggregates) == 3

    # Query top resilient
    top_resilient = agg_repo.get_top_resilient(2021, limit=2)
    assert len(top_resilient) == 2
    assert top_resilient[0].aggregate_score >= top_resilient[1].aggregate_score

    # Query bottom resilient
    bottom_resilient = agg_repo.get_bottom_resilient(2021, limit=1)
    assert len(bottom_resilient) == 1
    assert bottom_resilient[0].aggregate_score == 0.60  # Lowest score

    # Query aggregates for specific geography level
    county_aggregates = agg_repo.get_all_for_year(2021, geography_level="county")
    assert len(county_aggregates) == 3

    # Verify relationships work
    autauga_agg = agg_repo.get_for_geography(created_geos[0].id, 2021)
    assert autauga_agg is not None
    assert autauga_agg.geography.name == "Autauga County"

    # ===========================================================================
    # SUCCESS
    # ===========================================================================
    print("\n" + "="*80)
    print("COMPLETE DATABASE WORKFLOW TEST PASSED")
    print("="*80)
    print(f"✓ Created {len(all_indicators)} reference indicators")
    print(f"✓ Created {len(created_geos)} geographies")
    print(f"✓ Stored {num_sources} source data records")
    print(f"✓ Calculated {num_indicators} indicators")
    print(f"✓ Generated {num_aggregates} aggregate scores")
    print(f"✓ Successfully queried and verified all results")
    print("="*80)


def test_upsert_workflow(db_session):
    """Test upsert behavior for updating existing records."""

    # Create geography and indicator
    geo_repo = GeographyRepository(db_session)
    ref_repo = ReferenceIndicatorRepository(db_session)

    geo = geo_repo.create(geo_id="12345", name="Test County", geography_level="county")
    ref = ref_repo.create(indicator_name="Test", source="ACS", function="divide")
    db_session.commit()

    # Create initial indicator
    ind_repo = IndicatorRepository(db_session)
    indicator = ind_repo.create(
        geography_id=geo.id,
        indicator_id=ref.id,
        value=0.15,
        year=2021
    )
    db_session.commit()
    original_id = indicator.id

    # Upsert with new value (should update)
    updated = ind_repo.upsert(
        geography_id=geo.id,
        indicator_id=ref.id,
        value=0.25,
        year=2021
    )
    db_session.commit()

    assert updated.id == original_id  # Same record
    assert updated.value == 0.25  # Updated value

    # Verify only one record exists
    all_indicators = ind_repo.get_for_geography(geo.id, 2021)
    assert len(all_indicators) == 1


def test_cascade_delete_workflow(db_session):
    """Test that deleting geography cascades to related records."""

    # Setup
    geo_repo = GeographyRepository(db_session)
    ref_repo = ReferenceIndicatorRepository(db_session)
    ind_repo = IndicatorRepository(db_session)
    agg_repo = AggregateIndicatorRepository(db_session)

    geo = geo_repo.create(geo_id="12345", name="Test County", geography_level="county")
    ref = ref_repo.create(indicator_name="Test", source="ACS", function="divide")
    db_session.commit()

    # Create indicator and aggregate
    indicator = ind_repo.create(
        geography_id=geo.id,
        indicator_id=ref.id,
        value=0.15,
        year=2021
    )
    aggregate = agg_repo.create(
        geography_id=geo.id,
        year=2021,
        aggregate_score=0.65
    )
    db_session.commit()

    indicator_id = indicator.id
    aggregate_id = aggregate.id

    # Delete geography (should cascade)
    geo_repo.delete(geo)
    db_session.commit()

    # Verify related records deleted
    from sqlalchemy import select
    deleted_indicator = db_session.execute(
        select(Indicator).where(Indicator.id == indicator_id)
    ).scalar_one_or_none()

    deleted_aggregate = db_session.execute(
        select(AggregateIndicator).where(AggregateIndicator.id == aggregate_id)
    ).scalar_one_or_none()

    assert deleted_indicator is None
    assert deleted_aggregate is None


def test_multi_year_workflow(db_session):
    """Test workflow with data from multiple years."""

    # Setup
    geo_repo = GeographyRepository(db_session)
    ref_repo = ReferenceIndicatorRepository(db_session)
    ind_repo = IndicatorRepository(db_session)
    agg_repo = AggregateIndicatorRepository(db_session)

    geo = geo_repo.create(geo_id="12345", name="Test County", geography_level="county")
    ref = ref_repo.create(indicator_name="Test", source="ACS", function="divide")
    db_session.commit()

    # Create indicators for multiple years
    for year in [2019, 2020, 2021, 2022]:
        ind_repo.create(
            geography_id=geo.id,
            indicator_id=ref.id,
            value=0.15 + (year - 2019) * 0.02,  # Increasing trend
            year=year
        )
        agg_repo.create(
            geography_id=geo.id,
            year=year,
            aggregate_score=0.60 + (year - 2019) * 0.03  # Improving trend
        )

    db_session.commit()

    # Query each year
    for year in [2019, 2020, 2021, 2022]:
        indicators = ind_repo.get_for_geography(geo.id, year)
        assert len(indicators) == 1

        agg = agg_repo.get_for_geography(geo.id, year)
        assert agg is not None
        assert agg.year == year

    # Verify trend
    agg_2019 = agg_repo.get_for_geography(geo.id, 2019)
    agg_2022 = agg_repo.get_for_geography(geo.id, 2022)
    assert agg_2022.aggregate_score > agg_2019.aggregate_score
