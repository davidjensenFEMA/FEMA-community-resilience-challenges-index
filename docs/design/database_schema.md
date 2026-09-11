# FEMA CRIA Database Schema Design

**Date**: 2025-10-30
**Database**: PostgreSQL 16
**ORM**: SQLAlchemy 2.0
**Migration Tool**: Alembic

---

## Overview

This document defines the PostgreSQL database schema for the FEMA CRIA project. The database replaces Excel files as the primary data storage, enabling:

- **Queryable data** - SQL queries instead of Excel formulas
- **Versioning** - Track data changes over time
- **Scalability** - Handle tract-level data (80,000+ rows)
- **Relationships** - Enforce data integrity with foreign keys
- **Performance** - Indexed lookups, efficient aggregations

---

## Entity Relationship Diagram

```
┌─────────────────┐
│  data_years     │
│  (metadata)     │
└─────────────────┘
        │
        │
        ▼
┌─────────────────┐       ┌──────────────────────┐
│  geographies    │◄──────│  reference_indicators│
│  (counties,     │       │  (from Excel)        │
│   tracts, etc)  │       └──────────────────────┘
└─────────────────┘                │
        │                           │
        │                           │
        ▼                           ▼
┌─────────────────┐       ┌──────────────────────┐
│  source_data    │       │                      │
│  (API results)  │       │                      │
└─────────────────┘       │                      │
        │                 │                      │
        │                 │                      │
        ▼                 ▼                      │
┌─────────────────┐       ┌──────────────────────┤
│  indicators     │       │  indicator_metadata  │
│  (calculated)   │       │  (labels, notes)     │
└─────────────────┘       └──────────────────────┘
        │
        │
        ▼
┌─────────────────────┐
│  aggregate_indicators│
│  (final scores)      │
└─────────────────────┘
```

---

## Table Definitions

### 1. `geographies`

**Purpose**: Store geographic reference data (counties, tracts, states, tribes)

**Columns**:
```sql
CREATE TABLE geographies (
    id SERIAL PRIMARY KEY,
    geo_id VARCHAR(30) UNIQUE NOT NULL,          -- Census GEOID (e.g., "0500000US01001")
    name VARCHAR(255) NOT NULL,                   -- Full name
    geography_level VARCHAR(20) NOT NULL,         -- 'state', 'county', 'tract', 'tribal'

    -- Geographic hierarchy
    state_code VARCHAR(2),                        -- State FIPS (e.g., "01")
    state_name VARCHAR(100),
    state_abbr VARCHAR(2),                        -- State abbreviation (e.g., "AL")
    county_code VARCHAR(3),                       -- County FIPS
    county_name VARCHAR(100),
    tract_code VARCHAR(6),                        -- Tract code
    tract_name VARCHAR(100),

    -- Region information
    region VARCHAR(50),                           -- Census region

    -- Metadata
    population INTEGER,                           -- Latest population estimate
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    -- Constraints
    CONSTRAINT check_geography_level CHECK (
        geography_level IN ('state', 'county', 'tract', 'tribal')
    )
);

-- Indexes for performance
CREATE INDEX idx_geographies_geo_id ON geographies(geo_id);
CREATE INDEX idx_geographies_level ON geographies(geography_level);
CREATE INDEX idx_geographies_state ON geographies(state_code);
CREATE INDEX idx_geographies_county ON geographies(state_code, county_code);
```

**Sample Data**:
```
geo_id              | name                      | geography_level | state_code | county_code
--------------------|---------------------------|-----------------|------------|------------
0500000US01001      | Autauga County, Alabama   | county          | 01         | 001
0500000US01003      | Baldwin County, Alabama   | county          | 01         | 003
```

---

### 2. `reference_indicators`

**Purpose**: Store indicator definitions from `cria_data_reference.xlsx`

**Columns**:
```sql
CREATE TABLE reference_indicators (
    id SERIAL PRIMARY KEY,
    indicator_name VARCHAR(100) UNIQUE NOT NULL,  -- "Poverty", "GINI", etc.

    -- Data source
    source VARCHAR(20) NOT NULL,                  -- "ACS", "CBP", "EAVS", "ARDA", "POP"

    -- Calculation definition
    function VARCHAR(50) NOT NULL,                -- "divide", "max", "mean", etc.
    numerator TEXT,                               -- Column names or NAICS codes
    denominator TEXT,                             -- Column name or scalar value
    rate FLOAT,                                   -- For "divide_scalar" function

    -- Metadata
    category VARCHAR(50),                         -- Resilience category
    description TEXT,                             -- Human-readable description
    order_2023 INTEGER,                           -- Display order

    -- Data year tracking
    year_source VARCHAR(20),                      -- Which year config to use

    -- Flags
    is_active BOOLEAN DEFAULT TRUE,               -- Include in calculations
    reverse_polarity BOOLEAN DEFAULT FALSE,       -- Higher value = lower resilience

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    -- Constraints
    CONSTRAINT check_source CHECK (
        source IN ('ACS', 'CBP', 'EAVS', 'ARDA', 'POP')
    ),
    CONSTRAINT check_function CHECK (
        function IN ('divide', 'max', 'mean', 'divide_scalar', 'reverse_divide')
    )
);

-- Indexes
CREATE INDEX idx_indicators_source ON reference_indicators(source);
CREATE INDEX idx_indicators_active ON reference_indicators(is_active);
```

**Sample Data**:
```
id | indicator_name | source | function | numerator        | denominator
---|----------------|--------|----------|------------------|------------
1  | Poverty        | ACS    | divide   | B17001_002E      | B17001_001E
2  | GINI           | ACS    | divide   | B19083_001E      | 1
3  | Churches       | CBP    | divide   | 8131             | B01001_001E
```

---

### 3. `data_years`

**Purpose**: Track which years of data are used

**Columns**:
```sql
CREATE TABLE data_years (
    id SERIAL PRIMARY KEY,
    source VARCHAR(20) NOT NULL,                  -- "acs", "cbp", "naics", "pop", "asarb"
    year INTEGER NOT NULL,                        -- Year value
    description TEXT,                             -- Description

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    -- Constraints
    UNIQUE(source, year)
);

-- Index
CREATE INDEX idx_data_years_source ON data_years(source);
```

**Sample Data**:
```
source | year | description
-------|------|---------------------------
acs    | 2021 | American Community Survey
cbp    | 2020 | County Business Patterns
naics  | 2017 | NAICS classification year
pop    | 2020 | Population estimates
asarb  | 2020 | Religion census
```

---

### 4. `source_data`

**Purpose**: Store raw data retrieved from APIs (before indicator calculation)

**Columns**:
```sql
CREATE TABLE source_data (
    id SERIAL PRIMARY KEY,

    -- Foreign keys
    geography_id INTEGER NOT NULL REFERENCES geographies(id) ON DELETE CASCADE,
    indicator_id INTEGER NOT NULL REFERENCES reference_indicators(id) ON DELETE CASCADE,

    -- Data
    column_name VARCHAR(50) NOT NULL,             -- ACS column or NAICS code
    value FLOAT,                                  -- Numeric value (NULL if missing)
    label TEXT,                                   -- Human-readable label

    -- Year tracking
    year INTEGER NOT NULL,                        -- Data year

    -- Metadata
    is_imputed BOOLEAN DEFAULT FALSE,             -- Was missing data imputed?
    source_url TEXT,                              -- API URL (for reproducibility)

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),

    -- Constraints
    UNIQUE(geography_id, indicator_id, column_name, year)
);

-- Indexes for performance
CREATE INDEX idx_source_data_geography ON source_data(geography_id);
CREATE INDEX idx_source_data_indicator ON source_data(indicator_id);
CREATE INDEX idx_source_data_year ON source_data(year);
CREATE INDEX idx_source_data_composite ON source_data(geography_id, indicator_id, year);
```

**Sample Data**:
```
geography_id | indicator_id | column_name  | value  | year | label
-------------|--------------|--------------|--------|------|------------------------
1            | 1            | B17001_002E  | 2450   | 2021 | Poverty universe count
1            | 1            | B17001_001E  | 54000  | 2021 | Total population
1            | 2            | B19083_001E  | 0.45   | 2021 | GINI coefficient
```

---

### 5. `indicators`

**Purpose**: Store calculated indicator values

**Columns**:
```sql
CREATE TABLE indicators (
    id SERIAL PRIMARY KEY,

    -- Foreign keys
    geography_id INTEGER NOT NULL REFERENCES geographies(id) ON DELETE CASCADE,
    indicator_id INTEGER NOT NULL REFERENCES reference_indicators(id) ON DELETE CASCADE,

    -- Calculated value
    value FLOAT,                                  -- Indicator value

    -- Quality metrics
    is_clean BOOLEAN DEFAULT TRUE,                -- Passed data cleaning
    is_imputed BOOLEAN DEFAULT FALSE,             -- Used imputed source data

    -- Year tracking
    year INTEGER NOT NULL,

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),

    -- Constraints
    UNIQUE(geography_id, indicator_id, year)
);

-- Indexes
CREATE INDEX idx_indicators_geography ON indicators(geography_id);
CREATE INDEX idx_indicators_indicator ON indicators(indicator_id);
CREATE INDEX idx_indicators_year ON indicators(year);
CREATE INDEX idx_indicators_composite ON indicators(geography_id, indicator_id, year);
```

**Sample Data**:
```
geography_id | indicator_id | value  | year | is_clean | is_imputed
-------------|--------------|--------|------|----------|------------
1            | 1            | 0.0454 | 2021 | true     | false
1            | 2            | 0.4500 | 2021 | true     | false
```

---

### 6. `indicator_metadata`

**Purpose**: Store additional metadata about indicators (labels, notes, warnings)

**Columns**:
```sql
CREATE TABLE indicator_metadata (
    id SERIAL PRIMARY KEY,

    -- Foreign key
    indicator_id INTEGER NOT NULL REFERENCES reference_indicators(id) ON DELETE CASCADE,

    -- Metadata
    label TEXT,                                   -- Human-readable label
    notes TEXT,                                   -- Calculation notes
    warnings TEXT,                                -- Data quality warnings

    -- Source information
    source_citation TEXT,                         -- Data source citation
    last_verified TIMESTAMP,                      -- When definition was verified

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_indicator_metadata_indicator ON indicator_metadata(indicator_id);
```

---

### 7. `aggregate_indicators`

**Purpose**: Store final aggregated resilience scores

**Columns**:
```sql
CREATE TABLE aggregate_indicators (
    id SERIAL PRIMARY KEY,

    -- Foreign key
    geography_id INTEGER NOT NULL REFERENCES geographies(id) ON DELETE CASCADE,

    -- Aggregated scores
    aggregate_score FLOAT,                        -- Final CRIA score
    z_score FLOAT,                                -- Z-score of aggregate
    bin_class INTEGER,                            -- Binned classification (1-5)
    percentile FLOAT,                             -- Percentile rank

    -- Component scores (optional - for analysis)
    economic_score FLOAT,
    social_score FLOAT,
    infrastructure_score FLOAT,

    -- Processing metadata
    num_indicators_used INTEGER,                  -- How many indicators contributed
    num_indicators_missing INTEGER,               -- How many were missing
    imputation_rate FLOAT,                        -- % of imputed values

    -- Year tracking
    year INTEGER NOT NULL,

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),

    -- Constraints
    UNIQUE(geography_id, year),
    CONSTRAINT check_bin_class CHECK (bin_class BETWEEN 1 AND 5)
);

-- Indexes
CREATE INDEX idx_aggregate_geography ON aggregate_indicators(geography_id);
CREATE INDEX idx_aggregate_year ON aggregate_indicators(year);
CREATE INDEX idx_aggregate_score ON aggregate_indicators(aggregate_score);
CREATE INDEX idx_aggregate_bin ON aggregate_indicators(bin_class);
```

**Sample Data**:
```
geography_id | aggregate_score | z_score | bin_class | percentile | year
-------------|-----------------|---------|-----------|------------|-----
1            | 0.65            | 0.45    | 3         | 62.5       | 2021
2            | 0.78            | 1.20    | 4         | 85.2       | 2021
```

---

### 8. `processing_runs`

**Purpose**: Track when data processing was run (for auditing)

**Columns**:
```sql
CREATE TABLE processing_runs (
    id SERIAL PRIMARY KEY,

    -- Run information
    run_type VARCHAR(50) NOT NULL,                -- "data_pull", "indicators", "aggregate"
    geography_level VARCHAR(20) NOT NULL,         -- "county", "tract", "tribal"
    year INTEGER NOT NULL,

    -- Status
    status VARCHAR(20) NOT NULL,                  -- "running", "completed", "failed"
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,

    -- Metrics
    num_records_processed INTEGER,
    num_errors INTEGER,
    error_log TEXT,

    -- Configuration snapshot
    config_snapshot JSONB,                        -- Store .env values used

    -- Constraints
    CONSTRAINT check_status CHECK (
        status IN ('running', 'completed', 'failed')
    )
);

CREATE INDEX idx_processing_runs_type ON processing_runs(run_type);
CREATE INDEX idx_processing_runs_status ON processing_runs(status);
CREATE INDEX idx_processing_runs_started ON processing_runs(started_at);
```

---

## SQLAlchemy Models

**File**: `src/db/models.py`

```python
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Integer, String, Float, Boolean, Text, DateTime,
    ForeignKey, CheckConstraint, UniqueConstraint
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    """Base class for all models"""
    pass

class Geography(Base):
    __tablename__ = "geographies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    geo_id: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    geography_level: Mapped[str] = mapped_column(String(20), nullable=False)

    # Geographic hierarchy
    state_code: Mapped[Optional[str]] = mapped_column(String(2))
    state_name: Mapped[Optional[str]] = mapped_column(String(100))
    state_abbr: Mapped[Optional[str]] = mapped_column(String(2))
    county_code: Mapped[Optional[str]] = mapped_column(String(3))
    county_name: Mapped[Optional[str]] = mapped_column(String(100))
    tract_code: Mapped[Optional[str]] = mapped_column(String(6))
    tract_name: Mapped[Optional[str]] = mapped_column(String(100))

    region: Mapped[Optional[str]] = mapped_column(String(50))
    population: Mapped[Optional[int]] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    source_data = relationship("SourceData", back_populates="geography", cascade="all, delete-orphan")
    indicators = relationship("Indicator", back_populates="geography", cascade="all, delete-orphan")
    aggregates = relationship("AggregateIndicator", back_populates="geography", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint(
            "geography_level IN ('state', 'county', 'tract', 'tribal')",
            name="check_geography_level"
        ),
    )

class ReferenceIndicator(Base):
    __tablename__ = "reference_indicators"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    indicator_name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    source: Mapped[str] = mapped_column(String(20), nullable=False)
    function: Mapped[str] = mapped_column(String(50), nullable=False)
    numerator: Mapped[Optional[str]] = mapped_column(Text)
    denominator: Mapped[Optional[str]] = mapped_column(Text)
    rate: Mapped[Optional[float]] = mapped_column(Float)

    category: Mapped[Optional[str]] = mapped_column(String(50))
    description: Mapped[Optional[str]] = mapped_column(Text)
    order_2023: Mapped[Optional[int]] = mapped_column(Integer)
    year_source: Mapped[Optional[str]] = mapped_column(String(20))

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    reverse_polarity: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    source_data = relationship("SourceData", back_populates="indicator")
    indicators = relationship("Indicator", back_populates="indicator")
    metadata = relationship("IndicatorMetadata", back_populates="indicator", uselist=False)

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

class SourceData(Base):
    __tablename__ = "source_data"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    geography_id: Mapped[int] = mapped_column(Integer, ForeignKey("geographies.id", ondelete="CASCADE"), nullable=False)
    indicator_id: Mapped[int] = mapped_column(Integer, ForeignKey("reference_indicators.id", ondelete="CASCADE"), nullable=False)

    column_name: Mapped[str] = mapped_column(String(50), nullable=False)
    value: Mapped[Optional[float]] = mapped_column(Float)
    label: Mapped[Optional[str]] = mapped_column(Text)

    year: Mapped[int] = mapped_column(Integer, nullable=False)

    is_imputed: Mapped[bool] = mapped_column(Boolean, default=False)
    source_url: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    geography = relationship("Geography", back_populates="source_data")
    indicator = relationship("ReferenceIndicator", back_populates="source_data")

    __table_args__ = (
        UniqueConstraint("geography_id", "indicator_id", "column_name", "year", name="uq_source_data"),
    )

class Indicator(Base):
    __tablename__ = "indicators"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    geography_id: Mapped[int] = mapped_column(Integer, ForeignKey("geographies.id", ondelete="CASCADE"), nullable=False)
    indicator_id: Mapped[int] = mapped_column(Integer, ForeignKey("reference_indicators.id", ondelete="CASCADE"), nullable=False)

    value: Mapped[Optional[float]] = mapped_column(Float)

    is_clean: Mapped[bool] = mapped_column(Boolean, default=True)
    is_imputed: Mapped[bool] = mapped_column(Boolean, default=False)

    year: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    geography = relationship("Geography", back_populates="indicators")
    indicator = relationship("ReferenceIndicator", back_populates="indicators")

    __table_args__ = (
        UniqueConstraint("geography_id", "indicator_id", "year", name="uq_indicator"),
    )

class AggregateIndicator(Base):
    __tablename__ = "aggregate_indicators"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    geography_id: Mapped[int] = mapped_column(Integer, ForeignKey("geographies.id", ondelete="CASCADE"), nullable=False)

    aggregate_score: Mapped[Optional[float]] = mapped_column(Float)
    z_score: Mapped[Optional[float]] = mapped_column(Float)
    bin_class: Mapped[Optional[int]] = mapped_column(Integer)
    percentile: Mapped[Optional[float]] = mapped_column(Float)

    economic_score: Mapped[Optional[float]] = mapped_column(Float)
    social_score: Mapped[Optional[float]] = mapped_column(Float)
    infrastructure_score: Mapped[Optional[float]] = mapped_column(Float)

    num_indicators_used: Mapped[Optional[int]] = mapped_column(Integer)
    num_indicators_missing: Mapped[Optional[int]] = mapped_column(Integer)
    imputation_rate: Mapped[Optional[float]] = mapped_column(Float)

    year: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    geography = relationship("Geography", back_populates="aggregates")

    __table_args__ = (
        UniqueConstraint("geography_id", "year", name="uq_aggregate"),
        CheckConstraint("bin_class BETWEEN 1 AND 5", name="check_bin_class"),
    )
```

---

## Database Session Management

**File**: `src/db/session.py`

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
from typing import Generator
from src.config.settings import settings

# Create engine
engine = create_engine(
    settings.database_url,
    echo=settings.debug,  # Log SQL queries in debug mode
    pool_pre_ping=True,   # Verify connections before using
    pool_size=5,
    max_overflow=10
)

# Create session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

@contextmanager
def get_db() -> Generator[Session, None, None]:
    """Context manager for database sessions"""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

def get_db_session() -> Session:
    """Get a database session (for dependency injection)"""
    return SessionLocal()
```

---

## Repository Pattern

**File**: `src/db/repositories.py`

```python
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select, and_
from src.db.models import Geography, ReferenceIndicator, Indicator, AggregateIndicator

class GeographyRepository:
    """Data access layer for geographies"""

    def __init__(self, db: Session):
        self.db = db

    def get_by_geo_id(self, geo_id: str) -> Optional[Geography]:
        """Get geography by GEOID"""
        stmt = select(Geography).where(Geography.geo_id == geo_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_level(self, level: str) -> List[Geography]:
        """Get all geographies at a specific level"""
        stmt = select(Geography).where(Geography.geography_level == level)
        return list(self.db.execute(stmt).scalars())

    def create(self, geo_id: str, name: str, level: str, **kwargs) -> Geography:
        """Create new geography"""
        geography = Geography(
            geo_id=geo_id,
            name=name,
            geography_level=level,
            **kwargs
        )
        self.db.add(geography)
        self.db.flush()
        return geography

class IndicatorRepository:
    """Data access layer for indicators"""

    def __init__(self, db: Session):
        self.db = db

    def get_for_geography(
        self,
        geography_id: int,
        year: int
    ) -> List[Indicator]:
        """Get all indicators for a geography and year"""
        stmt = select(Indicator).where(
            and_(
                Indicator.geography_id == geography_id,
                Indicator.year == year
            )
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
        """Create new indicator"""
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
```

---

## Alembic Migration

**Initialize Alembic**:
```bash
poetry run alembic init alembic
```

**Configure** `alembic.ini`:
```ini
sqlalchemy.url = postgresql://cria_user:cria_password@localhost:5432/cria_db
```

**Create initial migration**:
```bash
poetry run alembic revision --autogenerate -m "Initial schema"
poetry run alembic upgrade head
```

---

## Query Examples

### Get all counties in a state
```python
from src.db.session import get_db
from src.db.repositories import GeographyRepository

with get_db() as db:
    repo = GeographyRepository(db)
    counties = repo.get_by_level("county")
    alabama_counties = [c for c in counties if c.state_abbr == "AL"]
```

### Get indicators for a geography
```python
from src.db.repositories import IndicatorRepository

with get_db() as db:
    repo = IndicatorRepository(db)
    indicators = repo.get_for_geography(geography_id=1, year=2021)

    for indicator in indicators:
        print(f"{indicator.indicator.indicator_name}: {indicator.value}")
```

### Get aggregated scores sorted by rank
```python
from sqlalchemy import select
from src.db.models import AggregateIndicator, Geography

with get_db() as db:
    stmt = (
        select(AggregateIndicator, Geography)
        .join(Geography)
        .where(AggregateIndicator.year == 2021)
        .order_by(AggregateIndicator.aggregate_score.desc())
    )

    results = db.execute(stmt).all()

    for agg, geo in results:
        print(f"{geo.name}: {agg.aggregate_score:.3f} (Bin {agg.bin_class})")
```

---

## Performance Considerations

### Indexes
All foreign keys are indexed automatically. Additional indexes:
- Composite indexes on (geography_id, year)
- Index on aggregate_score for ranking queries

### Batch Inserts
Use `bulk_insert_mappings()` for large datasets:

```python
from src.db.models import Indicator

indicators_data = [
    {"geography_id": 1, "indicator_id": 1, "value": 0.045, "year": 2021},
    {"geography_id": 1, "indicator_id": 2, "value": 0.450, "year": 2021},
    # ... thousands more
]

with get_db() as db:
    db.bulk_insert_mappings(Indicator, indicators_data)
```

### Query Optimization
Use `joinedload()` for eager loading:

```python
from sqlalchemy.orm import joinedload

stmt = (
    select(Indicator)
    .options(joinedload(Indicator.geography))
    .options(joinedload(Indicator.indicator))
)
```

---

## Backup & Recovery

### Backup Database
```bash
docker-compose exec postgres pg_dump -U cria_user cria_db > backup_$(date +%Y%m%d).sql
```

### Restore Database
```bash
docker-compose exec -T postgres psql -U cria_user cria_db < backup_20251030.sql
```

### Export to CSV
```python
import pandas as pd
from src.db.session import engine

df = pd.read_sql("SELECT * FROM aggregate_indicators", engine)
df.to_csv("aggregate_indicators_export.csv", index=False)
```

---

## Migration from Excel

**Script**: `scripts/import_reference_data.py`

```python
import pandas as pd
from src.config.paths import paths
from src.db.session import get_db
from src.db.models import ReferenceIndicator, DataYear

def import_reference_excel():
    """Import reference data from Excel to database"""

    xl = pd.ExcelFile(paths.reference_file)

    # Import indicators
    ref_df = xl.parse("Status")
    ref_df = ref_df.dropna(subset=["Order_2023"])

    with get_db() as db:
        for idx, row in ref_df.iterrows():
            indicator = ReferenceIndicator(
                indicator_name=row["Indicator"],
                source=row["Source"],
                function=row["Function"],
                numerator=str(row["numerator"]) if pd.notna(row["numerator"]) else None,
                denominator=str(row["denominator"]) if pd.notna(row["denominator"]) else None,
                order_2023=int(row["Order_2023"]),
                is_active=True
            )
            db.add(indicator)

    # Import years
    years_df = xl.parse("Years")

    with get_db() as db:
        for idx, row in years_df.iterrows():
            year = DataYear(
                source=row["label"],
                year=int(row["year_ref"]),
                description=f"{row['label']} data year"
            )
            db.add(year)

    print("Reference data imported successfully!")

if __name__ == "__main__":
    import_reference_excel()
```

---

## Future Enhancements

1. **Partitioning** - Partition large tables by year for better performance
2. **Materialized Views** - Pre-compute common aggregations
3. **Time-series tracking** - Track how indicators change over multiple years
4. **Spatial queries** - Add PostGIS extension for geographic queries
5. **Audit logging** - Track all changes to indicators

---

**Document Version**: 1.0
**Last Updated**: 2025-10-30
**Status**: Ready for implementation ✅
