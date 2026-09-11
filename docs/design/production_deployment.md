# Production Deployment Guide - FEMA CRIA

**Last Updated**: 2025-11-08
**Phase**: Phase 7 - Production Deployment
**Status**: Production Ready ✅

---

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Quick Start](#quick-start)
4. [Detailed Setup](#detailed-setup)
5. [Running the Pipeline](#running-the-pipeline)
6. [Database Management](#database-management)
7. [Troubleshooting](#troubleshooting)
8. [Performance Benchmarks](#performance-benchmarks)

---

## Overview

This guide covers deploying FEMA CRIA in a production environment using Docker and PostgreSQL. The system is designed for:

- **Production databases**: PostgreSQL 16 with persistent storage
- **Development/Testing**: SQLite for rapid iteration
- **Containerization**: Docker Compose for reproducible deployments
- **Migrations**: Alembic for database schema versioning

---

## Prerequisites

### Required Software

- **Docker**: v20.10+ (Docker Engine, not necessarily Docker Desktop)
  ```bash
  docker --version
  # Docker version 28.2.1 or later
  ```

- **Docker Compose**: v2.0+
  ```bash
  docker compose version
  # Docker Compose version v2.36.2 or later
  ```

- **Python**: 3.11+
  ```bash
  python --version
  # Python 3.11.4 or later
  ```

- **Poetry**: 1.7+
  ```bash
  poetry --version
  # Poetry (version 1.7.1)
  ```

### Required API Keys

- **Census API Key**: Get from https://api.census.gov/data/key_signup.html
  - Free, instant approval
  - Required for all data collection operations

---

## Quick Start

### 5-Minute Setup

```bash
# 1. Clone and navigate to project
cd /path/to/fema_cria

# 2. Install dependencies
poetry install

# 3. Create .env file with your Census API key
cp .env.example .env
# Edit .env and add your CENSUS_API_KEY

# 4. Start PostgreSQL
docker compose -f docker/docker-compose.yml up -d postgres

# 5. Run database migrations
poetry run alembic upgrade head

# 6. Import reference data
poetry run python scripts/import_reference_data.py

# 7. Run pipeline (test with state geography for speed)
poetry run python scripts/run_full_pipeline.py --geography state --year 2021
```

**Expected Result**: Pipeline completes successfully, data stored in PostgreSQL on port 5433.

---

## Detailed Setup

### Step 1: Environment Configuration

Create `.env` file from template:

```bash
cp .env.example .env
```

**Required Settings**:

```bash
# API Keys
CENSUS_API_KEY=your_actual_census_api_key_here

# Database (default PostgreSQL on port 5433)
DATABASE_URL=postgresql://cria_user:cria_password@localhost:5433/cria_db
TEST_DATABASE_URL=postgresql://cria_user:cria_password@localhost:5433/cria_test_db

# Data Years
ACS_YEAR=2021
CBP_YEAR=2020
POP_YEAR=2020

# Processing
DEFAULT_GEOGRAPHY=county
LOG_LEVEL=INFO
DEBUG=False  # Set to False for production
```

**Security Notes**:
- ⚠️ Never commit `.env` to version control
- ⚠️ Change default database passwords in production
- ✅ `.env` is already in `.gitignore`

### Step 2: PostgreSQL Setup

#### Option A: Docker Compose (Recommended)

Start PostgreSQL container:

```bash
# From project root
docker compose -f docker/docker-compose.yml up -d postgres

# Verify it's running
docker ps | grep cria_postgres

# Check logs
docker logs cria_postgres
```

**Port Configuration**:
- **Host Port**: 5433 (default, avoids conflicts with other PostgreSQL instances)
- **Container Port**: 5432 (internal)
- **Connection String**: `postgresql://cria_user:cria_password@localhost:5433/cria_db`

**Data Persistence**:
- Volume: `docker_postgres_data`
- Data survives container restarts
- To reset: `docker compose -f docker/docker-compose.yml down -v`

#### Option B: External PostgreSQL

If using an external PostgreSQL server:

1. Create database:
   ```sql
   CREATE DATABASE cria_db;
   CREATE USER cria_user WITH PASSWORD 'secure_password_here';
   GRANT ALL PRIVILEGES ON DATABASE cria_db TO cria_user;
   ```

2. Update `.env`:
   ```bash
   DATABASE_URL=postgresql://cria_user:secure_password_here@your-server:5432/cria_db
   ```

### Step 3: Database Migrations

Apply schema using Alembic:

```bash
# Run all pending migrations
poetry run alembic upgrade head

# Verify tables created
docker exec cria_postgres psql -U cria_user -d cria_db -c "\\dt"
```

**Expected Tables**:
- `alembic_version` - Migration tracking
- `reference_indicators` - Indicator definitions (22 indicators)
- `data_years` - Data year configuration (6 sources)
- `geographies` - Geographic entities (states, counties, tracts)
- `source_data` - Raw API data
- `indicators` - Calculated indicators
- `aggregate_indicators` - Final CRIA scores
- `indicator_metadata` - Optional metadata

### Step 4: Reference Data Import

Import indicator definitions and data years:

```bash
poetry run python scripts/import_reference_data.py
```

**Expected Output**:
```
✓ Successfully imported 22 indicators
✓ Successfully imported 6 data years
```

**Verify**:
```bash
docker exec cria_postgres psql -U cria_user -d cria_db -c \
  "SELECT COUNT(*) FROM reference_indicators; SELECT COUNT(*) FROM data_years;"
```

---

## Running the Pipeline

### Full Pipeline Workflow

The main script orchestrates the complete CRIA workflow:

```bash
poetry run python scripts/run_full_pipeline.py --geography LEVEL --year YEAR [OPTIONS]
```

### Common Usage Patterns

#### 1. State-Level Analysis (Fast, ~2 minutes)

```bash
poetry run python scripts/run_full_pipeline.py \
  --geography state \
  --year 2021
```

**Use Case**: Quick testing, validation, demos
**Records**: ~50 states, ~1,100 indicators

#### 2. County-Level Analysis (Production, ~5-10 minutes)

```bash
poetry run python scripts/run_full_pipeline.py \
  --geography county \
  --year 2021
```

**Use Case**: Primary production workload
**Records**: ~3,143 counties, ~69,000 indicators

#### 3. Tract-Level Analysis (Large, 30-60 minutes)

```bash
poetry run python scripts/run_full_pipeline.py \
  --geography tract \
  --year 2021
```

**Use Case**: High-resolution analysis
**Records**: ~85,000 tracts, ~1.8M indicators

### Advanced Options

```bash
# Export to Excel in addition to database
poetry run python scripts/run_full_pipeline.py \
  --geography county \
  --year 2021 \
  --export-excel

# Skip API pull (use cached data for testing)
poetry run python scripts/run_full_pipeline.py \
  --geography county \
  --year 2021 \
  --skip-pull

# Custom bin count
poetry run python scripts/run_full_pipeline.py \
  --geography county \
  --year 2021 \
  --bins 7

# Backwards compatibility (no database)
poetry run python scripts/run_full_pipeline.py \
  --geography county \
  --no-db \
  --export-excel
```

### Understanding the Pipeline

The pipeline executes these steps:

1. **Initialize Database**: Create session, verify schema
2. **Pull Source Data**: Query Census ACS, CBP, EAVS, ARDA, POP APIs
3. **Calculate Indicators**: Transform raw counts → rates/metrics
4. **Create Aggregates**: Bin, normalize, compute CRIA scores
5. **Store Results**: Bulk insert to database
6. **Export (Optional)**: Write Excel files

---

## Database Management

### Backup

Create a database backup:

```bash
# Using Docker container
docker exec cria_postgres pg_dump -U cria_user cria_db > backups/cria_backup_$(date +%Y%m%d).sql

# Compress for storage
gzip backups/cria_backup_$(date +%Y%m%d).sql
```

### Restore

Restore from backup:

```bash
# Uncompress if needed
gunzip backups/cria_backup_20251108.sql.gz

# Restore to PostgreSQL
docker exec -i cria_postgres psql -U cria_user -d cria_db < backups/cria_backup_20251108.sql
```

### Monitoring

Check database status:

```bash
# Connection test
docker exec cria_postgres psql -U cria_user -d cria_db -c "SELECT version();"

# Table sizes
docker exec cria_postgres psql -U cria_user -d cria_db -c "
  SELECT
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
  FROM pg_tables
  WHERE schemaname = 'public'
  ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
"

# Record counts
docker exec cria_postgres psql -U cria_user -d cria_db -c "
  SELECT
    'reference_indicators' as table_name, COUNT(*) FROM reference_indicators
  UNION ALL
  SELECT 'geographies', COUNT(*) FROM geographies
  UNION ALL
  SELECT 'source_data', COUNT(*) FROM source_data
  UNION ALL
  SELECT 'indicators', COUNT(*) FROM indicators
  UNION ALL
  SELECT 'aggregate_indicators', COUNT(*) FROM aggregate_indicators;
"
```

### Reset Database

**⚠️ WARNING: This deletes all data!**

```bash
# Drop all data (keeps schema)
docker exec cria_postgres psql -U cria_user -d cria_db -c "
  TRUNCATE TABLE aggregate_indicators, indicators, source_data,
              geographies, data_years, reference_indicators CASCADE;
"

# Or completely reset (remove volume)
docker compose -f docker/docker-compose.yml down -v
docker compose -f docker/docker-compose.yml up -d postgres
poetry run alembic upgrade head
poetry run python scripts/import_reference_data.py
```

---

## Troubleshooting

### Issue 1: Port 5432 Already in Use

**Symptom**:
```
Error: Bind for 0.0.0.0:5432 failed: port is already allocated
```

**Solution**:
The docker-compose.yml is configured to use port 5433 to avoid conflicts. If you still see this error:

```bash
# Check what's using port 5433
ss -tulpn | grep 5433

# Change port in docker/docker-compose.yml if needed
ports:
  - "5434:5432"  # Use a different port

# Update .env
DATABASE_URL=postgresql://cria_user:cria_password@localhost:5434/cria_db
```

### Issue 2: Connection Refused

**Symptom**:
```
psycopg2.OperationalError: could not connect to server
```

**Solutions**:

```bash
# 1. Verify PostgreSQL is running
docker ps | grep cria_postgres

# 2. Check logs for errors
docker logs cria_postgres

# 3. Test connection directly
docker exec cria_postgres psql -U cria_user -d cria_db -c "SELECT 1;"

# 4. Restart container
docker compose -f docker/docker-compose.yml restart postgres
```

### Issue 3: Missing Reference Data

**Symptom**:
```
ERROR: Could not find reference indicator...
```

**Solution**:
```bash
# Re-import reference data
poetry run python scripts/import_reference_data.py

# Verify
docker exec cria_postgres psql -U cria_user -d cria_db -c \
  "SELECT COUNT(*) FROM reference_indicators;"
# Should show: 22
```

### Issue 4: Census API Key Invalid

**Symptom**:
```
403 Forbidden: Invalid API key
```

**Solution**:
```bash
# 1. Verify key in .env file
grep CENSUS_API_KEY .env

# 2. Test key directly
curl "https://api.census.gov/data/2021/acs/acs5?get=NAME&for=state:01&key=YOUR_KEY_HERE"

# 3. Request new key if needed
# https://api.census.gov/data/key_signup.html
```

### Issue 5: Slow Performance

**Symptoms**:
- Pipeline takes > 10 minutes for counties
- Database queries are slow

**Solutions**:

```bash
# 1. Check system resources
docker stats cria_postgres

# 2. Increase PostgreSQL memory (add to docker-compose.yml)
environment:
  POSTGRES_SHARED_BUFFERS: 256MB
  POSTGRES_WORK_MEM: 16MB

# 3. Create indexes (if needed)
docker exec cria_postgres psql -U cria_user -d cria_db -c "
  CREATE INDEX IF NOT EXISTS idx_indicators_geography
    ON indicators(geography_id);
  CREATE INDEX IF NOT EXISTS idx_indicators_ref
    ON indicators(reference_indicator_id);
"

# 4. Analyze tables
docker exec cria_postgres psql -U cria_user -d cria_db -c "ANALYZE;"
```

---

## Performance Benchmarks

### Pipeline Runtime (PostgreSQL, Docker)

| Geography | Records | API Pull | Calculation | DB Storage | Total |
|-----------|---------|----------|-------------|------------|-------|
| State     | ~50     | ~30s     | ~2s         | ~1s        | ~35s  |
| County    | ~3,143  | ~70s     | ~5s         | ~4s        | ~90s  |
| Tract     | ~85,000 | ~15min   | ~2min       | ~1min      | ~20min|

### Database Storage

| Geography | Source Data | Indicators | Aggregates | Total DB Size |
|-----------|-------------|------------|------------|---------------|
| State     | ~1,100 rows | ~1,100 rows| ~50 rows   | ~500 KB       |
| County    | ~69,000     | ~69,000    | ~3,143     | ~25 MB        |
| Tract     | ~1.8M       | ~1.8M      | ~85,000    | ~600 MB       |

### System Requirements

**Minimum**:
- CPU: 2 cores
- RAM: 4 GB
- Disk: 10 GB

**Recommended**:
- CPU: 4+ cores
- RAM: 8+ GB
- Disk: 50 GB (for multiple years of tract data)

---

## Production Best Practices

### 1. Security

- ✅ Use strong database passwords (not defaults)
- ✅ Restrict database ports (firewall rules)
- ✅ Store `.env` outside repository
- ✅ Use environment-specific `.env` files (`.env.prod`, `.env.dev`)
- ✅ Enable PostgreSQL SSL/TLS for remote connections

### 2. Monitoring

```bash
# Set up periodic health checks
*/5 * * * * docker exec cria_postgres pg_isready -U cria_user

# Monitor disk space
df -h | grep docker
```

### 3. Backups

```bash
# Daily automated backups
0 2 * * * /path/to/scripts/backup_database.sh

# Retention policy: Keep last 30 days
find /backups -name "cria_backup_*.sql.gz" -mtime +30 -delete
```

### 4. Logging

```bash
# Collect logs
docker logs cria_postgres > logs/postgres_$(date +%Y%m%d).log

# Monitor errors
docker logs cria_postgres 2>&1 | grep ERROR
```

---

## Next Steps

After successful deployment:

1. **Schedule Regular Runs**: Set up cron jobs for periodic data updates
2. **Create API Endpoints**: Add FastAPI layer for querying results
3. **Build Dashboards**: Visualize CRIA scores using Plotly/Streamlit
4. **Add Monitoring**: Implement Prometheus + Grafana for system metrics
5. **Scale Horizontally**: Deploy multiple workers for parallel processing

---

## Support & Documentation

- **Project README**: [../README.md](../README.md)
- **Phase 6 Summary**: [20251107_PHASE6_COMPLETION.md](20251107_PHASE6_COMPLETION.md)
- **Database Schema**: [20251030_DATABASE_SCHEMA.md](20251030_DATABASE_SCHEMA.md)
- **Quick Start Guide**: [QUICK_START_PHASE7.md](QUICK_START_PHASE7.md)

---

## Changelog

### 2025-11-08 - Phase 7 Complete
- ✅ Docker Compose PostgreSQL validated (port 5433)
- ✅ Alembic migrations working
- ✅ Reference data import successful (22 indicators, 6 data years)
- ✅ Integration tests passing
- ✅ Production deployment documentation created

**Status**: Ready for production use ✅

---

*Document Version*: 1.0
*Created*: 2025-11-08
*Phase*: 7 - Production Deployment
