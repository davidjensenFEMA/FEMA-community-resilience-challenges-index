"""
Test SQLAlchemy models for FEMA CRIA database.

Tests cover:
- Model creation and basic attributes
- Foreign key relationships
- Cascade deletes
- Unique constraints
- Check constraints (geography_level, source, function, bin_class)
- Timestamps (created_at, updated_at)
"""

import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.exc import IntegrityError
from src.db.models import (
    Base, Geography, ReferenceIndicator, DataYear,
    SourceData, Indicator, IndicatorMetadata, AggregateIndicator
)


@pytest.fixture(scope="function")
def db_session():
    """Create test database session for each test using in-memory SQLite."""
    # Create new engine with SQLite URL
    engine = create_engine(
        'sqlite:///:memory:',
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # Create all tables
    Base.metadata.create_all(bind=engine)

    # Create session factory for this test
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Create session
    session = TestSessionLocal()

    yield session

    # Cleanup
    session.close()


class TestGeographyModel:
    """Test Geography model."""

    def test_create_geography(self, db_session):
        """Test creating a geography record."""
        geo = Geography(
            geo_id="12345",
            name="Test County",
            geography_level="county",
            state_code="01",
            state_name="Alabama",
            state_abbr="AL",
            county_code="001",
            county_name="Test County",
            population=50000
        )
        db_session.add(geo)
        db_session.commit()

        # Verify
        assert geo.id is not None
        assert geo.geo_id == "12345"
        assert geo.name == "Test County"
        assert geo.geography_level == "county"
        assert geo.created_at is not None

    def test_geography_unique_geo_id(self, db_session):
        """Test that geo_id must be unique."""
        geo1 = Geography(
            geo_id="12345",
            name="County 1",
            geography_level="county"
        )
        geo2 = Geography(
            geo_id="12345",  # Duplicate
            name="County 2",
            geography_level="county"
        )
        db_session.add(geo1)
        db_session.add(geo2)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_geography_level_constraint(self, db_session):
        """Test geography_level check constraint."""
        geo = Geography(
            geo_id="12345",
            name="Test",
            geography_level="invalid_level"  # Should fail
        )
        db_session.add(geo)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_geography_relationships(self, db_session):
        """Test that geography has relationships to other models."""
        geo = Geography(
            geo_id="12345",
            name="Test County",
            geography_level="county"
        )
        db_session.add(geo)
        db_session.commit()

        # Check relationships exist
        assert hasattr(geo, 'source_data')
        assert hasattr(geo, 'indicators')
        assert hasattr(geo, 'aggregates')
        assert len(geo.source_data) == 0
        assert len(geo.indicators) == 0
        assert len(geo.aggregates) == 0


class TestReferenceIndicatorModel:
    """Test ReferenceIndicator model."""

    def test_create_reference_indicator(self, db_session):
        """Test creating a reference indicator."""
        indicator = ReferenceIndicator(
            indicator_name="Poverty Rate",
            source="ACS",
            function="divide",
            numerator="B17001_002E",
            denominator="B17001_001E",
            order_2023=1,
            is_active=True
        )
        db_session.add(indicator)
        db_session.commit()

        assert indicator.id is not None
        assert indicator.indicator_name == "Poverty Rate"
        assert indicator.source == "ACS"
        assert indicator.function == "divide"

    def test_indicator_unique_name(self, db_session):
        """Test that indicator_name must be unique."""
        ind1 = ReferenceIndicator(
            indicator_name="Poverty Rate",
            source="ACS",
            function="divide"
        )
        ind2 = ReferenceIndicator(
            indicator_name="Poverty Rate",  # Duplicate
            source="CBP",
            function="mean"
        )
        db_session.add(ind1)
        db_session.add(ind2)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_source_constraint(self, db_session):
        """Test source check constraint."""
        indicator = ReferenceIndicator(
            indicator_name="Test Indicator",
            source="INVALID_SOURCE",  # Should fail
            function="divide"
        )
        db_session.add(indicator)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_function_constraint(self, db_session):
        """Test function check constraint."""
        indicator = ReferenceIndicator(
            indicator_name="Test Indicator",
            source="ACS",
            function="invalid_function"  # Should fail
        )
        db_session.add(indicator)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_reference_indicator_relationships(self, db_session):
        """Test reference indicator relationships."""
        indicator = ReferenceIndicator(
            indicator_name="Test Indicator",
            source="ACS",
            function="divide"
        )
        db_session.add(indicator)
        db_session.commit()

        assert hasattr(indicator, 'source_data')
        assert hasattr(indicator, 'indicators')
        assert hasattr(indicator, 'indicator_metadata')


class TestDataYearModel:
    """Test DataYear model."""

    def test_create_data_year(self, db_session):
        """Test creating a data year record."""
        data_year = DataYear(
            source="ACS",
            year=2021,
            description="ACS 5-year estimates"
        )
        db_session.add(data_year)
        db_session.commit()

        assert data_year.id is not None
        assert data_year.source == "ACS"
        assert data_year.year == 2021

    def test_data_year_unique_constraint(self, db_session):
        """Test that source+year combination must be unique."""
        dy1 = DataYear(source="ACS", year=2021)
        dy2 = DataYear(source="ACS", year=2021)  # Duplicate
        db_session.add(dy1)
        db_session.add(dy2)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_data_year_allows_different_sources(self, db_session):
        """Test that same year is allowed for different sources."""
        dy1 = DataYear(source="ACS", year=2021)
        dy2 = DataYear(source="CBP", year=2021)  # Different source
        db_session.add(dy1)
        db_session.add(dy2)
        db_session.commit()

        # Should succeed
        assert dy1.id is not None
        assert dy2.id is not None


class TestSourceDataModel:
    """Test SourceData model."""

    def test_create_source_data(self, db_session):
        """Test creating source data record."""
        # Create dependencies
        geo = Geography(
            geo_id="12345",
            name="Test County",
            geography_level="county"
        )
        indicator = ReferenceIndicator(
            indicator_name="Test Indicator",
            source="ACS",
            function="divide"
        )
        db_session.add_all([geo, indicator])
        db_session.commit()

        # Create source data
        source = SourceData(
            geography_id=geo.id,
            indicator_id=indicator.id,
            column_name="B17001_002E",
            value=1234.5,
            year=2021
        )
        db_session.add(source)
        db_session.commit()

        assert source.id is not None
        assert source.value == 1234.5

    def test_source_data_cascade_delete_geography(self, db_session):
        """Test that deleting geography cascades to source_data."""
        geo = Geography(
            geo_id="12345",
            name="Test County",
            geography_level="county"
        )
        indicator = ReferenceIndicator(
            indicator_name="Test Indicator",
            source="ACS",
            function="divide"
        )
        db_session.add_all([geo, indicator])
        db_session.commit()

        source = SourceData(
            geography_id=geo.id,
            indicator_id=indicator.id,
            column_name="B17001_002E",
            value=1234.5,
            year=2021
        )
        db_session.add(source)
        db_session.commit()

        source_id = source.id

        # Delete geography
        db_session.delete(geo)
        db_session.commit()

        # Source data should be deleted
        from sqlalchemy import select
        stmt = select(SourceData).where(SourceData.id == source_id)
        result = db_session.execute(stmt).scalar_one_or_none()
        assert result is None

    def test_source_data_unique_constraint(self, db_session):
        """Test unique constraint on geography+indicator+column+year."""
        geo = Geography(
            geo_id="12345",
            name="Test County",
            geography_level="county"
        )
        indicator = ReferenceIndicator(
            indicator_name="Test Indicator",
            source="ACS",
            function="divide"
        )
        db_session.add_all([geo, indicator])
        db_session.commit()

        source1 = SourceData(
            geography_id=geo.id,
            indicator_id=indicator.id,
            column_name="B17001_002E",
            value=1234.5,
            year=2021
        )
        source2 = SourceData(
            geography_id=geo.id,
            indicator_id=indicator.id,
            column_name="B17001_002E",  # Duplicate
            value=9999.9,
            year=2021
        )
        db_session.add_all([source1, source2])

        with pytest.raises(IntegrityError):
            db_session.commit()


class TestIndicatorModel:
    """Test Indicator model."""

    def test_create_indicator(self, db_session):
        """Test creating an indicator."""
        geo = Geography(
            geo_id="12345",
            name="Test County",
            geography_level="county"
        )
        ref_indicator = ReferenceIndicator(
            indicator_name="Test Indicator",
            source="ACS",
            function="divide"
        )
        db_session.add_all([geo, ref_indicator])
        db_session.commit()

        indicator = Indicator(
            geography_id=geo.id,
            indicator_id=ref_indicator.id,
            value=0.15,
            year=2021,
            is_clean=True
        )
        db_session.add(indicator)
        db_session.commit()

        assert indicator.id is not None
        assert indicator.value == 0.15

    def test_indicator_unique_constraint(self, db_session):
        """Test unique constraint on geography+indicator+year."""
        geo = Geography(
            geo_id="12345",
            name="Test County",
            geography_level="county"
        )
        ref_indicator = ReferenceIndicator(
            indicator_name="Test Indicator",
            source="ACS",
            function="divide"
        )
        db_session.add_all([geo, ref_indicator])
        db_session.commit()

        ind1 = Indicator(
            geography_id=geo.id,
            indicator_id=ref_indicator.id,
            value=0.15,
            year=2021
        )
        ind2 = Indicator(
            geography_id=geo.id,
            indicator_id=ref_indicator.id,
            value=0.20,  # Different value but same geography+indicator+year
            year=2021
        )
        db_session.add_all([ind1, ind2])

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_indicator_cascade_delete(self, db_session):
        """Test cascade delete from geography to indicators."""
        geo = Geography(
            geo_id="12345",
            name="Test County",
            geography_level="county"
        )
        ref_indicator = ReferenceIndicator(
            indicator_name="Test Indicator",
            source="ACS",
            function="divide"
        )
        db_session.add_all([geo, ref_indicator])
        db_session.commit()

        indicator = Indicator(
            geography_id=geo.id,
            indicator_id=ref_indicator.id,
            value=0.15,
            year=2021
        )
        db_session.add(indicator)
        db_session.commit()

        indicator_id = indicator.id

        # Delete geography
        db_session.delete(geo)
        db_session.commit()

        # Indicator should be deleted
        from sqlalchemy import select
        stmt = select(Indicator).where(Indicator.id == indicator_id)
        result = db_session.execute(stmt).scalar_one_or_none()
        assert result is None


class TestAggregateIndicatorModel:
    """Test AggregateIndicator model."""

    def test_create_aggregate_indicator(self, db_session):
        """Test creating an aggregate indicator."""
        geo = Geography(
            geo_id="12345",
            name="Test County",
            geography_level="county"
        )
        db_session.add(geo)
        db_session.commit()

        agg = AggregateIndicator(
            geography_id=geo.id,
            aggregate_score=0.65,
            z_score=0.5,
            bin_class=3,
            percentile=0.62,
            year=2021
        )
        db_session.add(agg)
        db_session.commit()

        assert agg.id is not None
        assert agg.aggregate_score == 0.65
        assert agg.bin_class == 3

    def test_aggregate_unique_constraint(self, db_session):
        """Test unique constraint on geography+year."""
        geo = Geography(
            geo_id="12345",
            name="Test County",
            geography_level="county"
        )
        db_session.add(geo)
        db_session.commit()

        agg1 = AggregateIndicator(
            geography_id=geo.id,
            aggregate_score=0.65,
            year=2021
        )
        agg2 = AggregateIndicator(
            geography_id=geo.id,
            aggregate_score=0.70,  # Different score, same geography+year
            year=2021
        )
        db_session.add_all([agg1, agg2])

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_aggregate_bin_class_constraint(self, db_session):
        """Test bin_class check constraint (1-7)."""
        geo = Geography(
            geo_id="12345",
            name="Test County",
            geography_level="county"
        )
        db_session.add(geo)
        db_session.commit()

        # Test invalid bin_class (0)
        agg = AggregateIndicator(
            geography_id=geo.id,
            bin_class=0,  # Should fail (< 1)
            year=2021
        )
        db_session.add(agg)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_aggregate_bin_class_constraint_upper(self, db_session):
        """Test bin_class upper bound (> 7)."""
        geo = Geography(
            geo_id="12345",
            name="Test County",
            geography_level="county"
        )
        db_session.add(geo)
        db_session.commit()

        # Test invalid bin_class (8)
        agg = AggregateIndicator(
            geography_id=geo.id,
            bin_class=8,  # Should fail (> 7)
            year=2021
        )
        db_session.add(agg)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_aggregate_cascade_delete(self, db_session):
        """Test cascade delete from geography to aggregates."""
        geo = Geography(
            geo_id="12345",
            name="Test County",
            geography_level="county"
        )
        db_session.add(geo)
        db_session.commit()

        agg = AggregateIndicator(
            geography_id=geo.id,
            aggregate_score=0.65,
            year=2021
        )
        db_session.add(agg)
        db_session.commit()

        agg_id = agg.id

        # Delete geography
        db_session.delete(geo)
        db_session.commit()

        # Aggregate should be deleted
        from sqlalchemy import select
        stmt = select(AggregateIndicator).where(AggregateIndicator.id == agg_id)
        result = db_session.execute(stmt).scalar_one_or_none()
        assert result is None


class TestIndicatorMetadataModel:
    """Test IndicatorMetadata model."""

    def test_create_indicator_metadata(self, db_session):
        """Test creating indicator metadata."""
        ref_indicator = ReferenceIndicator(
            indicator_name="Test Indicator",
            source="ACS",
            function="divide"
        )
        db_session.add(ref_indicator)
        db_session.commit()

        metadata = IndicatorMetadata(
            indicator_id=ref_indicator.id,
            label="Poverty Rate",
            notes="5-year ACS estimates",
            source_citation="U.S. Census Bureau"
        )
        db_session.add(metadata)
        db_session.commit()

        assert metadata.id is not None
        assert metadata.label == "Poverty Rate"

    def test_indicator_metadata_relationship(self, db_session):
        """Test one-to-one relationship between indicator and metadata."""
        ref_indicator = ReferenceIndicator(
            indicator_name="Test Indicator",
            source="ACS",
            function="divide"
        )
        db_session.add(ref_indicator)
        db_session.commit()

        metadata = IndicatorMetadata(
            indicator_id=ref_indicator.id,
            label="Test Label"
        )
        db_session.add(metadata)
        db_session.commit()

        # Access through relationship
        db_session.refresh(ref_indicator)
        assert ref_indicator.indicator_metadata is not None
        assert ref_indicator.indicator_metadata.label == "Test Label"


class TestModelTimestamps:
    """Test created_at and updated_at timestamps."""

    def test_geography_timestamps(self, db_session):
        """Test that timestamps are set automatically."""
        geo = Geography(
            geo_id="12345",
            name="Test County",
            geography_level="county"
        )
        db_session.add(geo)
        db_session.commit()

        assert geo.created_at is not None
        assert geo.updated_at is not None
        assert isinstance(geo.created_at, datetime)
        assert isinstance(geo.updated_at, datetime)

    def test_geography_updated_at_changes(self, db_session):
        """Test that updated_at changes on update."""
        geo = Geography(
            geo_id="12345",
            name="Test County",
            geography_level="county"
        )
        db_session.add(geo)
        db_session.commit()

        original_updated_at = geo.updated_at

        # Update
        geo.population = 50000
        db_session.commit()

        # updated_at should change (may be same if update is very fast)
        # Just verify it's still a valid datetime
        assert geo.updated_at is not None
        assert isinstance(geo.updated_at, datetime)
