"""
Repository pattern for database access.

Provides clean abstraction layer for CRUD operations on each model.
"""

from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, or_, func, insert
from src.db.models import (
    Geography, ReferenceIndicator, DataYear,
    SourceData, Indicator, IndicatorMetadata, AggregateIndicator
)


class GeographyRepository:
    """Data access layer for geographies."""

    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, geography_id: int) -> Optional[Geography]:
        """Get geography by ID."""
        return self.db.get(Geography, geography_id)

    def get_by_geo_id(self, geo_id: str) -> Optional[Geography]:
        """Get geography by GEOID string."""
        stmt = select(Geography).where(Geography.geo_id == geo_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_level(self, level: str) -> List[Geography]:
        """Get all geographies at a specific level (state, county, tract, tribal)."""
        stmt = select(Geography).where(Geography.geography_level == level)
        return list(self.db.execute(stmt).scalars())

    def get_by_state(self, state_code: str) -> List[Geography]:
        """Get all geographies in a specific state."""
        stmt = select(Geography).where(Geography.state_code == state_code)
        return list(self.db.execute(stmt).scalars())

    def get_counties_in_state(self, state_code: str) -> List[Geography]:
        """Get all counties in a specific state."""
        stmt = select(Geography).where(
            and_(
                Geography.geography_level == "county",
                Geography.state_code == state_code
            )
        )
        return list(self.db.execute(stmt).scalars())

    def create(self, **kwargs) -> Geography:
        """Create new geography."""
        geography = Geography(**kwargs)
        self.db.add(geography)
        self.db.flush()
        return geography

    def bulk_create(self, geographies: List[Dict[str, Any]]) -> List[Geography]:
        """Bulk create geographies."""
        geo_objects = [Geography(**geo_data) for geo_data in geographies]
        self.db.add_all(geo_objects)
        self.db.flush()
        return geo_objects

    def get_geo_id_map(self, level: Optional[str] = None) -> Dict[str, int]:
        """
        Get a mapping of geo_id -> database id for fast lookups.

        This is much faster than individual get_by_geo_id() calls for large datasets.

        Args:
            level: Optional geography level filter (state, county, tract, tribal)

        Returns:
            Dict mapping geo_id strings to database IDs
        """
        if level:
            stmt = select(Geography.geo_id, Geography.id).where(
                Geography.geography_level == level
            )
        else:
            stmt = select(Geography.geo_id, Geography.id)

        results = self.db.execute(stmt).fetchall()
        return {row[0]: row[1] for row in results}

    def update(self, geography: Geography, **kwargs) -> Geography:
        """Update geography."""
        for key, value in kwargs.items():
            setattr(geography, key, value)
        self.db.flush()
        return geography

    def delete(self, geography: Geography):
        """Delete geography (cascades to related data)."""
        self.db.delete(geography)
        self.db.flush()

    def count(self, level: Optional[str] = None) -> int:
        """Count geographies, optionally filtered by level (state/county/tract/tribal)."""
        stmt = select(func.count()).select_from(Geography)
        if level is not None:
            stmt = stmt.where(Geography.geography_level == level)
        return self.db.execute(stmt).scalar() or 0


class ReferenceIndicatorRepository:
    """Data access layer for reference indicators."""

    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, indicator_id: int) -> Optional[ReferenceIndicator]:
        """Get indicator by ID."""
        return self.db.get(ReferenceIndicator, indicator_id)

    def get_by_name(self, indicator_name: str) -> Optional[ReferenceIndicator]:
        """Get indicator by name."""
        stmt = select(ReferenceIndicator).where(
            ReferenceIndicator.indicator_name == indicator_name
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_all(self, active_only: bool = True) -> List[ReferenceIndicator]:
        """Get all indicators."""
        stmt = select(ReferenceIndicator)
        if active_only:
            stmt = stmt.where(ReferenceIndicator.is_active == True)
        stmt = stmt.order_by(ReferenceIndicator.order_2023)
        return list(self.db.execute(stmt).scalars())

    def get_by_source(self, source: str) -> List[ReferenceIndicator]:
        """Get all indicators from a specific source (ACS, CBP, etc.)."""
        stmt = select(ReferenceIndicator).where(
            ReferenceIndicator.source == source
        )
        return list(self.db.execute(stmt).scalars())

    def create(self, **kwargs) -> ReferenceIndicator:
        """Create new reference indicator."""
        indicator = ReferenceIndicator(**kwargs)
        self.db.add(indicator)
        self.db.flush()
        return indicator

    def bulk_create(self, indicators: List[Dict[str, Any]]) -> List[ReferenceIndicator]:
        """Bulk create indicators."""
        indicator_objects = [ReferenceIndicator(**ind_data) for ind_data in indicators]
        self.db.add_all(indicator_objects)
        self.db.flush()
        return indicator_objects

    def count(self, active_only: bool = False) -> int:
        """Count reference indicators, optionally restricted to active rows."""
        stmt = select(func.count()).select_from(ReferenceIndicator)
        if active_only:
            stmt = stmt.where(ReferenceIndicator.is_active == True)
        return self.db.execute(stmt).scalar() or 0


class IndicatorRepository:
    """Data access layer for calculated indicators."""

    def __init__(self, db: Session):
        self.db = db

    def get_for_geography(
        self,
        geography_id: int,
        year: int
    ) -> List[Indicator]:
        """Get all indicators for a geography and year."""
        stmt = select(Indicator).where(
            and_(
                Indicator.geography_id == geography_id,
                Indicator.year == year
            )
        )
        return list(self.db.execute(stmt).scalars())

    def get_by_indicator_name(
        self,
        indicator_name: str,
        year: int,
        geography_level: Optional[str] = None
    ) -> List[Indicator]:
        """Get indicator values across geographies."""
        stmt = (
            select(Indicator)
            .join(ReferenceIndicator)
            .where(
                and_(
                    ReferenceIndicator.indicator_name == indicator_name,
                    Indicator.year == year
                )
            )
        )

        if geography_level:
            stmt = stmt.join(Geography).where(
                Geography.geography_level == geography_level
            )

        return list(self.db.execute(stmt).scalars())

    def create(
        self,
        geography_id: int,
        indicator_id: int,
        value: float,
        year: int,
        **kwargs
    ) -> Indicator:
        """Create new indicator."""
        indicator = Indicator(
            geography_id=geography_id,
            indicator_id=indicator_id,
            value=value,
            year=year,
            **kwargs
        )
        self.db.add(indicator)
        self.db.flush()
        return indicator

    def bulk_create(self, indicators: List[Dict[str, Any]]) -> int:
        """
        Bulk create indicators using SQLAlchemy Core insert.

        This is significantly faster than ORM-based inserts for large datasets.

        Args:
            indicators: List of dictionaries with indicator fields

        Returns:
            Number of records inserted
        """
        if not indicators:
            return 0

        # Use SQLAlchemy Core insert for maximum performance
        BATCH_SIZE = 10000

        total_inserted = 0
        for i in range(0, len(indicators), BATCH_SIZE):
            batch = indicators[i:i + BATCH_SIZE]
            self.db.execute(insert(Indicator), batch)
            total_inserted += len(batch)

        self.db.flush()
        return total_inserted

    def upsert(
        self,
        geography_id: int,
        indicator_id: int,
        value: float,
        year: int,
        **kwargs
    ) -> Indicator:
        """Create or update indicator."""
        # Try to find existing
        stmt = select(Indicator).where(
            and_(
                Indicator.geography_id == geography_id,
                Indicator.indicator_id == indicator_id,
                Indicator.year == year
            )
        )
        existing = self.db.execute(stmt).scalar_one_or_none()

        if existing:
            # Update
            existing.value = value
            for key, val in kwargs.items():
                setattr(existing, key, val)
            self.db.flush()
            return existing
        else:
            # Create
            return self.create(geography_id, indicator_id, value, year, **kwargs)


class AggregateIndicatorRepository:
    """Data access layer for aggregate indicators."""

    def __init__(self, db: Session):
        self.db = db

    def get_for_geography(
        self,
        geography_id: int,
        year: int
    ) -> Optional[AggregateIndicator]:
        """Get aggregate indicator for a geography and year."""
        stmt = select(AggregateIndicator).where(
            and_(
                AggregateIndicator.geography_id == geography_id,
                AggregateIndicator.year == year
            )
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_all_for_year(
        self,
        year: int,
        geography_level: Optional[str] = None
    ) -> List[AggregateIndicator]:
        """Get all aggregate indicators for a year."""
        stmt = select(AggregateIndicator).where(
            AggregateIndicator.year == year
        )

        if geography_level:
            stmt = stmt.join(Geography).where(
                Geography.geography_level == geography_level
            )

        stmt = stmt.order_by(AggregateIndicator.percentile.desc())

        return list(self.db.execute(stmt).scalars())

    def get_top_resilient(
        self,
        year: int,
        limit: int = 10,
        geography_level: Optional[str] = None
    ) -> List[AggregateIndicator]:
        """Get top N most resilient geographies."""
        stmt = (
            select(AggregateIndicator)
            .where(AggregateIndicator.year == year)
            .order_by(AggregateIndicator.aggregate_score.desc())
            .limit(limit)
        )

        if geography_level:
            stmt = stmt.join(Geography).where(
                Geography.geography_level == geography_level
            )

        return list(self.db.execute(stmt).scalars())

    def get_bottom_resilient(
        self,
        year: int,
        limit: int = 10,
        geography_level: Optional[str] = None
    ) -> List[AggregateIndicator]:
        """Get bottom N least resilient geographies."""
        stmt = (
            select(AggregateIndicator)
            .where(AggregateIndicator.year == year)
            .order_by(AggregateIndicator.aggregate_score.asc())
            .limit(limit)
        )

        if geography_level:
            stmt = stmt.join(Geography).where(
                Geography.geography_level == geography_level
            )

        return list(self.db.execute(stmt).scalars())

    def create(
        self,
        geography_id: int,
        year: int,
        **kwargs
    ) -> AggregateIndicator:
        """Create new aggregate indicator."""
        aggregate = AggregateIndicator(
            geography_id=geography_id,
            year=year,
            **kwargs
        )
        self.db.add(aggregate)
        self.db.flush()
        return aggregate

    def bulk_create(self, aggregates: List[Dict[str, Any]]) -> int:
        """
        Bulk create aggregate indicators using SQLAlchemy Core insert.

        This is significantly faster than ORM-based inserts for large datasets.

        Args:
            aggregates: List of dictionaries with aggregate fields

        Returns:
            Number of records inserted
        """
        if not aggregates:
            return 0

        # Use SQLAlchemy Core insert for maximum performance
        BATCH_SIZE = 10000

        total_inserted = 0
        for i in range(0, len(aggregates), BATCH_SIZE):
            batch = aggregates[i:i + BATCH_SIZE]
            self.db.execute(insert(AggregateIndicator), batch)
            total_inserted += len(batch)

        self.db.flush()
        return total_inserted

    def upsert(
        self,
        geography_id: int,
        year: int,
        **kwargs
    ) -> AggregateIndicator:
        """Create or update aggregate indicator."""
        # Try to find existing
        existing = self.get_for_geography(geography_id, year)

        if existing:
            # Update
            for key, val in kwargs.items():
                setattr(existing, key, val)
            self.db.flush()
            return existing
        else:
            # Create
            return self.create(geography_id, year, **kwargs)


class SourceDataRepository:
    """Data access layer for source data."""

    def __init__(self, db: Session):
        self.db = db

    def get_for_geography(
        self,
        geography_id: int,
        year: int
    ) -> List[SourceData]:
        """Get all source data for a geography and year."""
        stmt = select(SourceData).where(
            and_(
                SourceData.geography_id == geography_id,
                SourceData.year == year
            )
        )
        return list(self.db.execute(stmt).scalars())

    def bulk_create(self, source_data_list: List[Dict[str, Any]]) -> int:
        """
        Bulk create source data records using SQLAlchemy Core insert.

        This is significantly faster than ORM-based inserts for large datasets.
        For 88k tract records, this reduces insert time from hours to seconds.

        Args:
            source_data_list: List of dictionaries with source data fields

        Returns:
            Number of records inserted
        """
        if not source_data_list:
            return 0

        # Use SQLAlchemy Core insert for maximum performance
        # This bypasses ORM overhead and uses executemany optimization
        BATCH_SIZE = 10000

        total_inserted = 0
        for i in range(0, len(source_data_list), BATCH_SIZE):
            batch = source_data_list[i:i + BATCH_SIZE]
            self.db.execute(insert(SourceData), batch)
            total_inserted += len(batch)

        self.db.flush()
        return total_inserted
