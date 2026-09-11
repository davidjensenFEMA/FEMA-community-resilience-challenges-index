"""
SQLAlchemy models for FEMA CRIA database.

Models represent the 7 core tables for storing CRIA data:
- geographies: Geographic reference data
- reference_indicators: Indicator definitions
- data_years: Data year tracking
- source_data: Raw API data
- indicators: Calculated indicators
- indicator_metadata: Additional metadata
- aggregate_indicators: Final CRIA scores
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Integer, String, Float, Boolean, Text, DateTime,
    ForeignKey, CheckConstraint, UniqueConstraint, Index
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


class Geography(Base):
    """
    Geographic reference data (counties, tracts, states, tribes).

    Stores hierarchical geographic information with state/county/tract relationships.
    """
    __tablename__ = "geographies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    geo_id: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    geography_level: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    # Geographic hierarchy
    state_code: Mapped[Optional[str]] = mapped_column(String(2), index=True)
    state_name: Mapped[Optional[str]] = mapped_column(String(100))
    state_abbr: Mapped[Optional[str]] = mapped_column(String(2))
    county_code: Mapped[Optional[str]] = mapped_column(String(3))
    county_name: Mapped[Optional[str]] = mapped_column(String(100))
    tract_code: Mapped[Optional[str]] = mapped_column(String(6))
    tract_name: Mapped[Optional[str]] = mapped_column(String(100))

    # Region information
    region: Mapped[Optional[str]] = mapped_column(String(50))

    # Metadata
    population: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    # Relationships
    source_data = relationship("SourceData", back_populates="geography", cascade="all, delete-orphan")
    indicators = relationship("Indicator", back_populates="geography", cascade="all, delete-orphan")
    aggregates = relationship("AggregateIndicator", back_populates="geography", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint(
            "geography_level IN ('state', 'county', 'tract', 'tribal')",
            name="check_geography_level"
        ),
        Index("idx_geographies_state_county", "state_code", "county_code"),
    )

    def __repr__(self):
        return f"<Geography(id={self.id}, geo_id={self.geo_id}, name={self.name})>"


class ReferenceIndicator(Base):
    """
    Indicator definitions from reference Excel file.

    Defines how to calculate each indicator (source, function, numerator, denominator).
    """
    __tablename__ = "reference_indicators"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    indicator_name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    # Data source
    source: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    # Calculation definition
    function: Mapped[str] = mapped_column(String(50), nullable=False)
    numerator: Mapped[Optional[str]] = mapped_column(Text)
    denominator: Mapped[Optional[str]] = mapped_column(Text)
    rate: Mapped[Optional[float]] = mapped_column(Float)

    # Metadata
    category: Mapped[Optional[str]] = mapped_column(String(50))
    description: Mapped[Optional[str]] = mapped_column(Text)
    order_2023: Mapped[Optional[int]] = mapped_column(Integer)
    year_source: Mapped[Optional[str]] = mapped_column(String(20))

    # Flags
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    reverse_polarity: Mapped[bool] = mapped_column(Boolean, default=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    # Relationships
    source_data = relationship("SourceData", back_populates="indicator")
    indicators = relationship("Indicator", back_populates="indicator")
    indicator_metadata = relationship("IndicatorMetadata", back_populates="indicator", uselist=False)

    __table_args__ = (
        CheckConstraint(
            "source IN ('ACS', 'CBP', 'EAVS', 'ARDA', 'POP')",
            name="check_source"
        ),
        CheckConstraint(
            "function IN ('divide', 'max', 'mean', 'divide_scalar', 'reverse_divide')",
            name="check_function"
        ),
    )

    def __repr__(self):
        return f"<ReferenceIndicator(id={self.id}, name={self.indicator_name})>"


class DataYear(Base):
    """
    Track which years of data are used for each source.
    """
    __tablename__ = "data_years"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    __table_args__ = (
        UniqueConstraint("source", "year", name="uq_data_year"),
    )

    def __repr__(self):
        return f"<DataYear(source={self.source}, year={self.year})>"


class SourceData(Base):
    """
    Raw data retrieved from APIs (before indicator calculation).

    Stores the raw column values from Census API, CBP, etc.
    """
    __tablename__ = "source_data"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Foreign keys
    geography_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("geographies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    indicator_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("reference_indicators.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Data
    column_name: Mapped[str] = mapped_column(String(50), nullable=False)
    value: Mapped[Optional[float]] = mapped_column(Float)
    label: Mapped[Optional[str]] = mapped_column(Text)

    # Year tracking
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    # Metadata
    is_imputed: Mapped[bool] = mapped_column(Boolean, default=False)
    source_url: Mapped[Optional[str]] = mapped_column(Text)

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    geography = relationship("Geography", back_populates="source_data")
    indicator = relationship("ReferenceIndicator", back_populates="source_data")

    __table_args__ = (
        UniqueConstraint(
            "geography_id", "indicator_id", "column_name", "year",
            name="uq_source_data"
        ),
        Index("idx_source_data_composite", "geography_id", "indicator_id", "year"),
    )

    def __repr__(self):
        return f"<SourceData(id={self.id}, geo_id={self.geography_id}, indicator_id={self.indicator_id})>"


class Indicator(Base):
    """
    Calculated indicator values.

    Stores the final calculated values after applying the indicator function.
    """
    __tablename__ = "indicators"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Foreign keys
    geography_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("geographies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    indicator_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("reference_indicators.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Calculated value
    value: Mapped[Optional[float]] = mapped_column(Float)

    # Quality metrics
    is_clean: Mapped[bool] = mapped_column(Boolean, default=True)
    is_imputed: Mapped[bool] = mapped_column(Boolean, default=False)

    # Year tracking
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    geography = relationship("Geography", back_populates="indicators")
    indicator = relationship("ReferenceIndicator", back_populates="indicators")

    __table_args__ = (
        UniqueConstraint(
            "geography_id", "indicator_id", "year",
            name="uq_indicator"
        ),
        Index("idx_indicators_composite", "geography_id", "indicator_id", "year"),
    )

    def __repr__(self):
        return f"<Indicator(id={self.id}, geo_id={self.geography_id}, value={self.value})>"


class IndicatorMetadata(Base):
    """
    Additional metadata about indicators (labels, notes, warnings).
    """
    __tablename__ = "indicator_metadata"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Foreign key
    indicator_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("reference_indicators.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Metadata
    label: Mapped[Optional[str]] = mapped_column(Text)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    warnings: Mapped[Optional[str]] = mapped_column(Text)

    # Source information
    source_citation: Mapped[Optional[str]] = mapped_column(Text)
    last_verified: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    # Relationship
    indicator = relationship("ReferenceIndicator", back_populates="indicator_metadata")

    def __repr__(self):
        return f"<IndicatorMetadata(id={self.id}, indicator_id={self.indicator_id})>"


class AggregateIndicator(Base):
    """
    Final aggregated CRIA resilience scores.

    Stores the computed aggregate scores, z-scores, percentiles, and bin classifications.
    """
    __tablename__ = "aggregate_indicators"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Foreign key
    geography_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("geographies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Aggregated scores
    aggregate_score: Mapped[Optional[float]] = mapped_column(Float)
    z_score: Mapped[Optional[float]] = mapped_column(Float)
    bin_class: Mapped[Optional[int]] = mapped_column(Integer, index=True)
    percentile: Mapped[Optional[float]] = mapped_column(Float, index=True)

    # Component scores (optional - for analysis)
    economic_score: Mapped[Optional[float]] = mapped_column(Float)
    social_score: Mapped[Optional[float]] = mapped_column(Float)
    infrastructure_score: Mapped[Optional[float]] = mapped_column(Float)

    # Processing metadata
    num_indicators_used: Mapped[Optional[int]] = mapped_column(Integer)
    num_indicators_missing: Mapped[Optional[int]] = mapped_column(Integer)
    imputation_rate: Mapped[Optional[float]] = mapped_column(Float)

    # Year tracking
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationship
    geography = relationship("Geography", back_populates="aggregates")

    __table_args__ = (
        UniqueConstraint("geography_id", "year", name="uq_aggregate"),
        CheckConstraint("bin_class BETWEEN 1 AND 7", name="check_bin_class"),
    )

    def __repr__(self):
        return f"<AggregateIndicator(id={self.id}, geo_id={self.geography_id}, cri={self.aggregate_score})>"
