# Docker Development Guide - FEMA CRIA

**Date**: 2025-10-30
**Purpose**: Reproducible development environment using Docker
**Target Users**: Developers, researchers, future collaborators

---

## Overview

This guide explains how to use Docker for the FEMA CRIA project. Docker provides:

✅ **Consistent environment** - Same setup on all machines (Windows, Mac, Linux)
✅ **No conda conflicts** - Isolated from your system Python
✅ **Easy collaboration** - Share exact environment with colleagues
✅ **Quick setup** - From zero to running in minutes
✅ **Database included** - PostgreSQL containerized with the app

---

## Prerequisites

### Install Docker

**Windows / Mac**:
- Download [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- Install and start Docker Desktop
- Verify installation: `docker --version`

**Linux**:
```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install docker.io docker-compose
sudo systemctl start docker
sudo usermod -aG docker $USER  # Add yourself to docker group
# Log out and back in

# Verify
docker --version
docker-compose --version
```

---

## Quick Start

### 1. Clone and Setup

```bash
# Clone repository
cd /path/to/fema_cria

# Create .env file from example
cp .env.example .env

# Edit .env file (add your Census API key)
nano .env
```

### 2. Start Services

```bash
# Start all services (database + app)
cd docker
docker-compose up -d

# Check status
docker-compose ps

# Expected output:
# NAME              STATE     PORTS
# cria_postgres     Up        0.0.0.0:5432->5432/tcp
# cria_app          Up        0.0.0.0:8000->8000/tcp
```

### 3. Run Database Migrations

```bash
# Create initial database schema
docker-compose exec app poetry run alembic upgrade head
```

### 4. Import Reference Data

```bash
# Import Excel reference data to database
docker-compose exec app poetry run python scripts/import_reference_data.py
```

### 5. Run Workflow

```bash
# Run county-level workflow
docker-compose exec app poetry run python scripts/run_county_workflow.py
```

---

## Docker Architecture

### Services Overview

```
┌─────────────────────────────────────┐
│         Docker Host                 │
│                                     │
│  ┌──────────────┐  ┌─────────────┐ │
│  │              │  │             │ │
│  │  cria_app    │──│  postgres   │ │
│  │  (Python)    │  │  (DB)       │ │
│  │              │  │             │ │
│  └──────────────┘  └─────────────┘ │
│         │                  │        │
└─────────┼──────────────────┼────────┘
          │                  │
          ▼                  ▼
     localhost:8000    localhost:5432
```

### Service Definitions

**`postgres`** (Database):
- Image: `postgres:16`
- Port: `5432` (accessible from host)
- Data: Persisted in Docker volume `postgres_data`
- Credentials: Defined in `.env`

**`app`** (Python Application):
- Built from: `docker/Dockerfile.dev`
- Mounts: Your code directory (`..:/app`)
- Dependencies: Installed via Poetry
- Depends on: `postgres` service (waits for DB to be ready)

---

## Common Commands

### Service Management

```bash
# Start all services
docker-compose up -d

# Stop all services
docker-compose down

# Restart a service
docker-compose restart app

# View logs
docker-compose logs -f app         # App logs (follow)
docker-compose logs -f postgres    # Database logs

# View service status
docker-compose ps
```

### Running Commands in Containers

```bash
# Enter app container (interactive shell)
docker-compose exec app /bin/bash

# Run Python script
docker-compose exec app poetry run python scripts/run_county_workflow.py

# Run tests
docker-compose exec app poetry run pytest

# Run specific test
docker-compose exec app poetry run pytest tests/unit/test_indicators.py -v

# Run Python REPL
docker-compose exec app poetry run python
```

### Database Operations

```bash
# Access PostgreSQL CLI
docker-compose exec postgres psql -U cria_user -d cria_db

# Common psql commands:
\dt                    # List tables
\d geographies        # Describe table
SELECT * FROM geographies LIMIT 5;
\q                    # Quit

# Backup database
docker-compose exec postgres pg_dump -U cria_user cria_db > backup.sql

# Restore database
cat backup.sql | docker-compose exec -T postgres psql -U cria_user -d cria_db

# Reset database (WARNING: deletes all data)
docker-compose down -v              # -v removes volumes
docker-compose up -d
docker-compose exec app poetry run alembic upgrade head
```

### Code Changes (Live Reload)

Your code is mounted into the container, so changes are immediately available:

```bash
# Edit a file locally
nano src/core/indicators.py

# Run updated code (no rebuild needed)
docker-compose exec app poetry run python scripts/run_county_workflow.py
```

### Rebuilding (When Dependencies Change)

```bash
# If you change pyproject.toml, rebuild:
docker-compose build app

# Then restart:
docker-compose up -d
```

---

## Environment Configuration

### `.env` File

**Location**: Project root (`/path/to/fema_cria/.env`)

**Example**:
```bash
# API Keys
CENSUS_API_KEY=d665833afd3f36d12b9a0e2832c3d6b92830a29a

# Data Years
ACS_YEAR=2021
CBP_YEAR=2020
NAICS_YEAR=2017
POP_YEAR=2020
ASARB_YEAR=2020
ACS_LABELS_YEAR=2020

# Database (Docker)
DATABASE_URL=postgresql://cria_user:cria_password@postgres:5432/cria_db

# Paths (relative to project root)
DATA_DIR=data
OUTPUT_DIR=output
LOGS_DIR=logs

# Processing
DEFAULT_GEOGRAPHY=county
DEBUG=True
LOG_LEVEL=INFO

# Testing
TEST_DATABASE_URL=postgresql://cria_user:cria_password@postgres:5432/cria_test_db
```

**Important Notes**:
- Database host is `postgres` (Docker service name), NOT `localhost`
- Changes to `.env` require container restart: `docker-compose restart app`

---

## Development Workflows

### Workflow 1: Interactive Development

```bash
# Enter container
docker-compose exec app /bin/bash

# Now you're inside the container
poetry run python
>>> from src.core.data_puller import DataPuller
>>> puller = DataPuller(geography='county')
>>> data = puller.pull_all_data()
```

### Workflow 2: Run Scripts

```bash
# Run county workflow
docker-compose exec app poetry run python scripts/run_county_workflow.py

# Run tract workflow
docker-compose exec app poetry run python scripts/run_tract_workflow.py

# Export results to Excel
docker-compose exec app poetry run python scripts/export_to_excel.py
```

### Workflow 3: Testing

```bash
# Run all tests
docker-compose exec app poetry run pytest

# Run with coverage
docker-compose exec app poetry run pytest --cov=src --cov-report=html

# Open coverage report (from your local machine)
open htmlcov/index.html  # Mac
xdg-open htmlcov/index.html  # Linux
start htmlcov/index.html  # Windows
```

### Workflow 4: Database Exploration

```bash
# Access database
docker-compose exec postgres psql -U cria_user -d cria_db

# Query geographies
SELECT geo_id, name, geography_level FROM geographies LIMIT 10;

# Count indicators by geography
SELECT g.name, COUNT(i.id) as num_indicators
FROM geographies g
LEFT JOIN indicators i ON g.id = i.geography_id
WHERE i.year = 2021
GROUP BY g.name
ORDER BY num_indicators DESC
LIMIT 10;

# Check aggregate scores
SELECT g.name, a.aggregate_score, a.bin_class
FROM aggregate_indicators a
JOIN geographies g ON a.geography_id = g.id
WHERE a.year = 2021
ORDER BY a.aggregate_score DESC
LIMIT 10;
```

---

## Troubleshooting

### Problem: Containers won't start

**Symptoms**: `docker-compose up` fails

**Solutions**:
```bash
# Check Docker is running
docker --version

# Check logs
docker-compose logs

# Remove old containers
docker-compose down
docker-compose up -d

# Nuclear option (removes all data)
docker-compose down -v
docker-compose up -d
```

### Problem: Database connection refused

**Symptoms**: `psycopg2.OperationalError: could not connect to server`

**Solutions**:
```bash
# Check database is healthy
docker-compose ps
# postgres should show "healthy"

# If not healthy, check logs
docker-compose logs postgres

# Restart database
docker-compose restart postgres

# Wait for health check
docker-compose ps
```

### Problem: Permission denied on mounted files

**Symptoms**: Can't write to `output/` or `logs/`

**Solutions**:
```bash
# On Linux, fix permissions
sudo chown -R $USER:$USER output/ logs/

# Or run container as your user (add to docker-compose.yml):
# user: "${UID}:${GID}"
```

### Problem: Poetry dependencies out of sync

**Symptoms**: `ModuleNotFoundError` for installed packages

**Solutions**:
```bash
# Rebuild container
docker-compose build app

# If that doesn't work, clear Poetry cache
docker-compose exec app rm -rf /root/.cache/pypoetry
docker-compose restart app
```

### Problem: Database migrations fail

**Symptoms**: `alembic upgrade head` fails

**Solutions**:
```bash
# Check current migration status
docker-compose exec app poetry run alembic current

# View migration history
docker-compose exec app poetry run alembic history

# If stuck, reset database (WARNING: loses data)
docker-compose down -v
docker-compose up -d
docker-compose exec app poetry run alembic upgrade head
```

---

## Production Deployment

### Building Production Image

**File**: `docker/Dockerfile` (non-dev)

```bash
# Build production image
docker build -f docker/Dockerfile -t fema-cria:latest .

# Run production container
docker run -d \
  --name cria_production \
  --env-file .env.production \
  -v ./data:/app/data \
  -v ./output:/app/output \
  fema-cria:latest
```

### Production `docker-compose.yml`

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:16
    container_name: cria_postgres
    environment:
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_DB: ${DB_NAME}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: unless-stopped

  app:
    image: fema-cria:latest
    container_name: cria_app
    depends_on:
      - postgres
    environment:
      DATABASE_URL: postgresql://${DB_USER}:${DB_PASSWORD}@postgres:5432/${DB_NAME}
    volumes:
      - ./data:/app/data:ro  # Read-only data
      - ./output:/app/output
      - ./logs:/app/logs
    restart: unless-stopped

volumes:
  postgres_data:
```

---

## Performance Tips

### Optimize Docker Build

**Use `.dockerignore`**:
```
# .dockerignore
__pycache__/
*.pyc
.git/
.venv/
output/
logs/
deprecated/
tests/
docs/
*.md
```

### Speed Up Poetry Install

**In Dockerfile**:
```dockerfile
# Cache dependencies separately
COPY pyproject.toml poetry.lock ./
RUN poetry install --no-root --no-dev

# Then copy code
COPY . .
RUN poetry install --no-dev
```

### Reduce Image Size

```bash
# Use multi-stage build (advanced)
FROM python:3.11-slim AS builder
# ... install dependencies

FROM python:3.11-slim
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
# ... copy app
```

---

## Docker Compose Reference

### Full `docker-compose.yml` (Development)

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
    env_file:
      - ../.env
    volumes:
      - ..:/app
      - /app/.venv  # Don't mount venv
    ports:
      - "8000:8000"
    stdin_open: true
    tty: true
    command: /bin/bash

volumes:
  postgres_data:
```

### Full `Dockerfile.dev`

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

---

## CI/CD Integration (Future)

### GitHub Actions Example

```yaml
# .github/workflows/test.yml
name: Test CRIA

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: cria_user
          POSTGRES_PASSWORD: cria_password
          POSTGRES_DB: cria_test_db
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install Poetry
        run: pip install poetry

      - name: Install dependencies
        run: poetry install

      - name: Run tests
        env:
          DATABASE_URL: postgresql://cria_user:cria_password@localhost:5432/cria_test_db
        run: poetry run pytest --cov=src
```

---

## Comparison: Conda vs Docker

| Feature | Conda | Docker |
|---------|-------|--------|
| **Environment** | Python only | Full system (Python + Postgres + OS) |
| **Isolation** | Partial (shares OS) | Complete (containerized) |
| **Reproducibility** | Medium (environment.yml) | High (exact image) |
| **Collaboration** | Requires conda install | Just needs Docker |
| **Database** | Manual PostgreSQL setup | Included in compose |
| **Performance** | Native speed | ~5% overhead |
| **Disk Space** | ~500MB | ~2GB (includes OS) |
| **Learning Curve** | Low | Medium |

**Recommendation**: Use **Docker** for this project (database integration is critical)

---

## Next Steps

After getting Docker running:

1. ✅ Verify database connection
2. ✅ Run initial data import
3. ✅ Run county workflow
4. ✅ Run tests
5. ✅ Explore database with psql
6. ✅ Make code changes and test live reload

---

## Resources

- [Docker Documentation](https://docs.docker.com/)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [Poetry Documentation](https://python-poetry.org/docs/)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)

---

**Document Version**: 1.0
**Last Updated**: 2025-10-30
**Status**: Ready for use ✅
