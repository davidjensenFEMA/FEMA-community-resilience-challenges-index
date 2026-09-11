"""
Test repository pattern classes for FEMA CRIA database.

Tests cover:
- CRUD operations (Create, Read, Update, Delete)
- Query methods (get_by_state, get_by_level, etc.)
- Bulk operations (bulk_create)
- Upsert behavior (create or update)
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
    IndicatorRepository, AggregateIndicatorRepository, SourceDataRepository
)


@pytest.fixture(scope="function")
def db_session():
    """Create test database session for each test using in-memory SQLite."""
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


class TestGeographyRepository:
    """Test GeographyRepository CRUD and query methods."""

    def test_create(self, db_session):
        """Test creating a geography."""
        repo = GeographyRepository(db_session)
        geo = repo.create(
            geo_id="12345",
            name="Test County",
            geography_level="county",
            state_code="01"
        )
        db_session.commit()

        assert geo.id is not None
        assert geo.geo_id == "12345"
        assert geo.name == "Test County"

    def test_get_by_id(self, db_session):
        """Test getting geography by ID."""
        repo = GeographyRepository(db_session)
        geo = repo.create(
            geo_id="12345",
            name="Test County",
            geography_level="county"
        )
        db_session.commit()

        found = repo.get_by_id(geo.id)
        assert found is not None
        assert found.geo_id == "12345"

    def test_get_by_geo_id(self, db_session):
        """Test getting geography by GEOID."""
        repo = GeographyRepository(db_session)
        geo = repo.create(
            geo_id="12345",
            name="Test County",
            geography_level="county"
        )
        db_session.commit()

        found = repo.get_by_geo_id("12345")
        assert found is not None
        assert found.name == "Test County"

    def test_get_by_level(self, db_session):
        """Test getting all geographies at a level."""
        repo = GeographyRepository(db_session)
        repo.create(geo_id="01", name="State 1", geography_level="state")
        repo.create(geo_id="01001", name="County 1", geography_level="county")
        repo.create(geo_id="01002", name="County 2", geography_level="county")
        repo.create(geo_id="01001001", name="Tract 1", geography_level="tract")
        db_session.commit()

        counties = repo.get_by_level("county")
        assert len(counties) == 2

    def test_get_by_state(self, db_session):
        """Test getting all geographies in a state."""
        repo = GeographyRepository(db_session)
        repo.create(geo_id="01001", name="County 1", geography_level="county", state_code="01")
        repo.create(geo_id="01002", name="County 2", geography_level="county", state_code="01")
        repo.create(geo_id="02001", name="County 3", geography_level="county", state_code="02")
        db_session.commit()

        state_01 = repo.get_by_state("01")
        assert len(state_01) == 2

    def test_get_counties_in_state(self, db_session):
        """Test getting counties in a specific state."""
        repo = GeographyRepository(db_session)
        repo.create(geo_id="01", name="State 1", geography_level="state", state_code="01")
        repo.create(geo_id="01001", name="County 1", geography_level="county", state_code="01")
        repo.create(geo_id="01002", name="County 2", geography_level="county", state_code="01")
        repo.create(geo_id="02001", name="County 3", geography_level="county", state_code="02")
        db_session.commit()

        counties = repo.get_counties_in_state("01")
        assert len(counties) == 2
        assert all(g.geography_level == "county" for g in counties)

    def test_bulk_create(self, db_session):
        """Test bulk creating geographies."""
        repo = GeographyRepository(db_session)
        geographies = [
            {"geo_id": "01001", "name": "County 1", "geography_level": "county"},
            {"geo_id": "01002", "name": "County 2", "geography_level": "county"},
            {"geo_id": "01003", "name": "County 3", "geography_level": "county"},
        ]
        created = repo.bulk_create(geographies)
        db_session.commit()

        assert len(created) == 3
        assert all(g.id is not None for g in created)

    def test_update(self, db_session):
        """Test updating a geography."""
        repo = GeographyRepository(db_session)
        geo = repo.create(geo_id="12345", name="Test County", geography_level="county")
        db_session.commit()

        repo.update(geo, population=50000)
        db_session.commit()

        assert geo.population == 50000

    def test_delete(self, db_session):
        """Test deleting a geography."""
        repo = GeographyRepository(db_session)
        geo = repo.create(geo_id="12345", name="Test County", geography_level="county")
        db_session.commit()

        repo.delete(geo)
        db_session.commit()

        found = repo.get_by_geo_id("12345")
        assert found is None


class TestReferenceIndicatorRepository:
    """Test ReferenceIndicatorRepository CRUD and query methods."""

    def test_create(self, db_session):
        """Test creating a reference indicator."""
        repo = ReferenceIndicatorRepository(db_session)
        indicator = repo.create(
            indicator_name="Poverty Rate",
            source="ACS",
            function="divide",
            numerator="B17001_002E",
            denominator="B17001_001E"
        )
        db_session.commit()

        assert indicator.id is not None
        assert indicator.indicator_name == "Poverty Rate"

    def test_get_by_id(self, db_session):
        """Test getting indicator by ID."""
        repo = ReferenceIndicatorRepository(db_session)
        indicator = repo.create(
            indicator_name="Poverty Rate",
            source="ACS",
            function="divide"
        )
        db_session.commit()

        found = repo.get_by_id(indicator.id)
        assert found is not None
        assert found.indicator_name == "Poverty Rate"

    def test_get_by_name(self, db_session):
        """Test getting indicator by name."""
        repo = ReferenceIndicatorRepository(db_session)
        indicator = repo.create(
            indicator_name="Poverty Rate",
            source="ACS",
            function="divide"
        )
        db_session.commit()

        found = repo.get_by_name("Poverty Rate")
        assert found is not None
        assert found.source == "ACS"

    def test_get_all(self, db_session):
        """Test getting all indicators."""
        repo = ReferenceIndicatorRepository(db_session)
        repo.create(indicator_name="Indicator 1", source="ACS", function="divide", order_2023=1)
        repo.create(indicator_name="Indicator 2", source="CBP", function="mean", order_2023=2)
        repo.create(indicator_name="Indicator 3", source="ACS", function="divide", order_2023=3, is_active=False)
        db_session.commit()

        # Active only (default)
        active = repo.get_all(active_only=True)
        assert len(active) == 2

        # All indicators
        all_indicators = repo.get_all(active_only=False)
        assert len(all_indicators) == 3

    def test_get_by_source(self, db_session):
        """Test getting indicators by source."""
        repo = ReferenceIndicatorRepository(db_session)
        repo.create(indicator_name="Indicator 1", source="ACS", function="divide")
        repo.create(indicator_name="Indicator 2", source="ACS", function="divide")
        repo.create(indicator_name="Indicator 3", source="CBP", function="mean")
        db_session.commit()

        acs_indicators = repo.get_by_source("ACS")
        assert len(acs_indicators) == 2

    def test_bulk_create(self, db_session):
        """Test bulk creating indicators."""
        repo = ReferenceIndicatorRepository(db_session)
        indicators = [
            {"indicator_name": "Indicator 1", "source": "ACS", "function": "divide"},
            {"indicator_name": "Indicator 2", "source": "CBP", "function": "mean"},
            {"indicator_name": "Indicator 3", "source": "ACS", "function": "divide"},
        ]
        created = repo.bulk_create(indicators)
        db_session.commit()

        assert len(created) == 3
        assert all(i.id is not None for i in created)


class TestIndicatorRepository:
    """Test IndicatorRepository CRUD and query methods."""

    def test_create(self, db_session):
        """Test creating an indicator."""
        # Setup dependencies
        geo_repo = GeographyRepository(db_session)
        ref_repo = ReferenceIndicatorRepository(db_session)
        geo = geo_repo.create(geo_id="12345", name="Test County", geography_level="county")
        ref_indicator = ref_repo.create(indicator_name="Test", source="ACS", function="divide")
        db_session.commit()

        # Create indicator
        repo = IndicatorRepository(db_session)
        indicator = repo.create(
            geography_id=geo.id,
            indicator_id=ref_indicator.id,
            value=0.15,
            year=2021
        )
        db_session.commit()

        assert indicator.id is not None
        assert indicator.value == 0.15

    def test_get_for_geography(self, db_session):
        """Test getting indicators for a geography and year."""
        # Setup
        geo_repo = GeographyRepository(db_session)
        ref_repo = ReferenceIndicatorRepository(db_session)
        geo = geo_repo.create(geo_id="12345", name="Test County", geography_level="county")
        ref1 = ref_repo.create(indicator_name="Indicator 1", source="ACS", function="divide")
        ref2 = ref_repo.create(indicator_name="Indicator 2", source="CBP", function="mean")
        db_session.commit()

        # Create indicators
        repo = IndicatorRepository(db_session)
        repo.create(geography_id=geo.id, indicator_id=ref1.id, value=0.15, year=2021)
        repo.create(geography_id=geo.id, indicator_id=ref2.id, value=0.25, year=2021)
        repo.create(geography_id=geo.id, indicator_id=ref1.id, value=0.18, year=2020)
        db_session.commit()

        # Query
        indicators_2021 = repo.get_for_geography(geo.id, 2021)
        assert len(indicators_2021) == 2

    def test_get_by_indicator_name(self, db_session):
        """Test getting indicator values across geographies."""
        # Setup
        geo_repo = GeographyRepository(db_session)
        ref_repo = ReferenceIndicatorRepository(db_session)
        geo1 = geo_repo.create(geo_id="01001", name="County 1", geography_level="county")
        geo2 = geo_repo.create(geo_id="01002", name="County 2", geography_level="county")
        ref = ref_repo.create(indicator_name="Poverty Rate", source="ACS", function="divide")
        db_session.commit()

        # Create indicators
        repo = IndicatorRepository(db_session)
        repo.create(geography_id=geo1.id, indicator_id=ref.id, value=0.15, year=2021)
        repo.create(geography_id=geo2.id, indicator_id=ref.id, value=0.20, year=2021)
        db_session.commit()

        # Query
        results = repo.get_by_indicator_name("Poverty Rate", 2021)
        assert len(results) == 2

    def test_bulk_create(self, db_session):
        """Test bulk creating indicators."""
        # Setup
        geo_repo = GeographyRepository(db_session)
        ref_repo = ReferenceIndicatorRepository(db_session)
        geo = geo_repo.create(geo_id="12345", name="Test County", geography_level="county")
        ref = ref_repo.create(indicator_name="Test", source="ACS", function="divide")
        db_session.commit()

        # Bulk create
        repo = IndicatorRepository(db_session)
        indicators = [
            {"geography_id": geo.id, "indicator_id": ref.id, "value": 0.15, "year": 2021},
            {"geography_id": geo.id, "indicator_id": ref.id, "value": 0.18, "year": 2020},
            {"geography_id": geo.id, "indicator_id": ref.id, "value": 0.12, "year": 2019},
        ]
        num_created = repo.bulk_create(indicators)
        db_session.commit()

        assert num_created == 3

    def test_upsert_create(self, db_session):
        """Test upsert when record doesn't exist (should create)."""
        # Setup
        geo_repo = GeographyRepository(db_session)
        ref_repo = ReferenceIndicatorRepository(db_session)
        geo = geo_repo.create(geo_id="12345", name="Test County", geography_level="county")
        ref = ref_repo.create(indicator_name="Test", source="ACS", function="divide")
        db_session.commit()

        # Upsert (create)
        repo = IndicatorRepository(db_session)
        indicator = repo.upsert(
            geography_id=geo.id,
            indicator_id=ref.id,
            value=0.15,
            year=2021
        )
        db_session.commit()

        assert indicator.id is not None
        assert indicator.value == 0.15

    def test_upsert_update(self, db_session):
        """Test upsert when record exists (should update)."""
        # Setup
        geo_repo = GeographyRepository(db_session)
        ref_repo = ReferenceIndicatorRepository(db_session)
        geo = geo_repo.create(geo_id="12345", name="Test County", geography_level="county")
        ref = ref_repo.create(indicator_name="Test", source="ACS", function="divide")
        db_session.commit()

        # Create initial
        repo = IndicatorRepository(db_session)
        indicator = repo.create(geography_id=geo.id, indicator_id=ref.id, value=0.15, year=2021)
        db_session.commit()
        original_id = indicator.id

        # Upsert (update)
        updated = repo.upsert(geography_id=geo.id, indicator_id=ref.id, value=0.25, year=2021)
        db_session.commit()

        assert updated.id == original_id  # Same ID
        assert updated.value == 0.25  # Updated value


class TestAggregateIndicatorRepository:
    """Test AggregateIndicatorRepository CRUD and query methods."""

    def test_create(self, db_session):
        """Test creating an aggregate indicator."""
        # Setup
        geo_repo = GeographyRepository(db_session)
        geo = geo_repo.create(geo_id="12345", name="Test County", geography_level="county")
        db_session.commit()

        # Create aggregate
        repo = AggregateIndicatorRepository(db_session)
        agg = repo.create(
            geography_id=geo.id,
            year=2021,
            aggregate_score=0.65,
            percentile=0.62,
            bin_class=3
        )
        db_session.commit()

        assert agg.id is not None
        assert agg.aggregate_score == 0.65

    def test_get_for_geography(self, db_session):
        """Test getting aggregate for geography and year."""
        # Setup
        geo_repo = GeographyRepository(db_session)
        geo = geo_repo.create(geo_id="12345", name="Test County", geography_level="county")
        db_session.commit()

        # Create aggregate
        repo = AggregateIndicatorRepository(db_session)
        agg = repo.create(geography_id=geo.id, year=2021, aggregate_score=0.65)
        db_session.commit()

        # Query
        found = repo.get_for_geography(geo.id, 2021)
        assert found is not None
        assert found.aggregate_score == 0.65

    def test_get_all_for_year(self, db_session):
        """Test getting all aggregates for a year."""
        # Setup
        geo_repo = GeographyRepository(db_session)
        geo1 = geo_repo.create(geo_id="01001", name="County 1", geography_level="county")
        geo2 = geo_repo.create(geo_id="01002", name="County 2", geography_level="county")
        db_session.commit()

        # Create aggregates
        repo = AggregateIndicatorRepository(db_session)
        repo.create(geography_id=geo1.id, year=2021, aggregate_score=0.65, percentile=0.62)
        repo.create(geography_id=geo2.id, year=2021, aggregate_score=0.75, percentile=0.82)
        repo.create(geography_id=geo1.id, year=2020, aggregate_score=0.60, percentile=0.55)
        db_session.commit()

        # Query
        results_2021 = repo.get_all_for_year(2021)
        assert len(results_2021) == 2

    def test_get_all_for_year_filtered_by_level(self, db_session):
        """Test getting aggregates filtered by geography level."""
        # Setup
        geo_repo = GeographyRepository(db_session)
        county = geo_repo.create(geo_id="01001", name="County 1", geography_level="county")
        tract = geo_repo.create(geo_id="01001001", name="Tract 1", geography_level="tract")
        db_session.commit()

        # Create aggregates
        repo = AggregateIndicatorRepository(db_session)
        repo.create(geography_id=county.id, year=2021, aggregate_score=0.65)
        repo.create(geography_id=tract.id, year=2021, aggregate_score=0.70)
        db_session.commit()

        # Query for counties only
        counties = repo.get_all_for_year(2021, geography_level="county")
        assert len(counties) == 1

    def test_get_top_resilient(self, db_session):
        """Test getting top resilient geographies."""
        # Setup
        geo_repo = GeographyRepository(db_session)
        geos = [
            geo_repo.create(geo_id=f"0100{i}", name=f"County {i}", geography_level="county")
            for i in range(5)
        ]
        db_session.commit()

        # Create aggregates with different scores
        repo = AggregateIndicatorRepository(db_session)
        for i, geo in enumerate(geos):
            repo.create(geography_id=geo.id, year=2021, aggregate_score=0.5 + i * 0.1)
        db_session.commit()

        # Query top 3
        top_3 = repo.get_top_resilient(2021, limit=3)
        assert len(top_3) == 3
        # Should be in descending order
        assert top_3[0].aggregate_score >= top_3[1].aggregate_score >= top_3[2].aggregate_score

    def test_get_bottom_resilient(self, db_session):
        """Test getting bottom resilient geographies."""
        # Setup
        geo_repo = GeographyRepository(db_session)
        geos = [
            geo_repo.create(geo_id=f"0100{i}", name=f"County {i}", geography_level="county")
            for i in range(5)
        ]
        db_session.commit()

        # Create aggregates with different scores
        repo = AggregateIndicatorRepository(db_session)
        for i, geo in enumerate(geos):
            repo.create(geography_id=geo.id, year=2021, aggregate_score=0.5 + i * 0.1)
        db_session.commit()

        # Query bottom 3
        bottom_3 = repo.get_bottom_resilient(2021, limit=3)
        assert len(bottom_3) == 3
        # Should be in ascending order
        assert bottom_3[0].aggregate_score <= bottom_3[1].aggregate_score <= bottom_3[2].aggregate_score

    def test_bulk_create(self, db_session):
        """Test bulk creating aggregate indicators."""
        # Setup
        geo_repo = GeographyRepository(db_session)
        geos = [
            geo_repo.create(geo_id=f"0100{i}", name=f"County {i}", geography_level="county")
            for i in range(3)
        ]
        db_session.commit()

        # Bulk create
        repo = AggregateIndicatorRepository(db_session)
        aggregates = [
            {"geography_id": geo.id, "year": 2021, "aggregate_score": 0.6 + i * 0.1}
            for i, geo in enumerate(geos)
        ]
        num_created = repo.bulk_create(aggregates)
        db_session.commit()

        assert num_created == 3

    def test_upsert(self, db_session):
        """Test upsert for aggregate indicators."""
        # Setup
        geo_repo = GeographyRepository(db_session)
        geo = geo_repo.create(geo_id="12345", name="Test County", geography_level="county")
        db_session.commit()

        # Create initial
        repo = AggregateIndicatorRepository(db_session)
        agg = repo.create(geography_id=geo.id, year=2021, aggregate_score=0.65)
        db_session.commit()
        original_id = agg.id

        # Upsert (should update)
        updated = repo.upsert(geography_id=geo.id, year=2021, aggregate_score=0.75, percentile=0.85)
        db_session.commit()

        assert updated.id == original_id
        assert updated.aggregate_score == 0.75
        assert updated.percentile == 0.85


class TestSourceDataRepository:
    """Test SourceDataRepository CRUD and query methods."""

    def test_bulk_create(self, db_session):
        """Test bulk creating source data records."""
        # Setup
        geo_repo = GeographyRepository(db_session)
        ref_repo = ReferenceIndicatorRepository(db_session)
        geo = geo_repo.create(geo_id="12345", name="Test County", geography_level="county")
        ref = ref_repo.create(indicator_name="Test", source="ACS", function="divide")
        db_session.commit()

        # Bulk create
        repo = SourceDataRepository(db_session)
        source_data = [
            {
                "geography_id": geo.id,
                "indicator_id": ref.id,
                "column_name": "B17001_002E",
                "value": 1234.5,
                "year": 2021
            },
            {
                "geography_id": geo.id,
                "indicator_id": ref.id,
                "column_name": "B17001_001E",
                "value": 5000.0,
                "year": 2021
            }
        ]
        num_created = repo.bulk_create(source_data)
        db_session.commit()

        assert num_created == 2

    def test_get_for_geography(self, db_session):
        """Test getting source data for a geography and year."""
        # Setup
        geo_repo = GeographyRepository(db_session)
        ref_repo = ReferenceIndicatorRepository(db_session)
        geo = geo_repo.create(geo_id="12345", name="Test County", geography_level="county")
        ref = ref_repo.create(indicator_name="Test", source="ACS", function="divide")
        db_session.commit()

        # Create source data
        repo = SourceDataRepository(db_session)
        source_data = [
            {
                "geography_id": geo.id,
                "indicator_id": ref.id,
                "column_name": "B17001_002E",
                "value": 1234.5,
                "year": 2021
            },
            {
                "geography_id": geo.id,
                "indicator_id": ref.id,
                "column_name": "B17001_001E",
                "value": 5000.0,
                "year": 2021
            },
            {
                "geography_id": geo.id,
                "indicator_id": ref.id,
                "column_name": "B17001_002E",
                "value": 1100.0,
                "year": 2020
            }
        ]
        repo.bulk_create(source_data)
        db_session.commit()

        # Query
        results_2021 = repo.get_for_geography(geo.id, 2021)
        assert len(results_2021) == 2
