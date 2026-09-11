# FEMA CRIA Quickstart Guide

Get up and running with CRIA in 5 minutes.

## Prerequisites

- Python 3.11+
- Poetry (`pip install poetry`)
- Census API key ([get one here](https://api.census.gov/data/key_signup.html))

## Setup

```bash
# 1. Clone and install
git clone https://git-in.gss.anl.gov/jhutchison/fema_cria.git
cd fema_cria
poetry install

# 2. Configure environment
cp .env.example .env
# Edit .env and add your CENSUS_API_KEY
```

## Run the Pipeline

### Option A: Quick Test (Skip API Pull)

If you have cached data in `data/output/cria_inputs_county.xlsx`:

```bash
poetry run python scripts/run_full_pipeline.py \
    --geography county \
    --year 2022 \
    --export-excel \
    --skip-pull
```

### Option B: Full Pipeline (Pull Fresh Data)

```bash
poetry run python scripts/run_full_pipeline.py \
    --geography county \
    --year 2022 \
    --export-excel
```

### Output

Results are saved to `data/output/`:
- `cria_indicators_county_2022.xlsx` - Raw indicator values
- `cria_results_county_2022.xlsx` - Full results with bins and aggregates

## Run Tests

```bash
poetry run pytest                    # All tests
poetry run pytest tests/unit/ -v     # Unit tests only
poetry run pytest --cov=src          # With coverage
```

## Key Commands

| Command | Description |
|---------|-------------|
| `poetry install` | Install dependencies |
| `poetry run pytest` | Run tests |
| `poetry run python scripts/run_full_pipeline.py --help` | Pipeline options |
| `poetry run python scripts/import_reference_data.py` | Load reference data to DB |
| `poetry run python scripts/sync_geographies.py` | Sync geography data |

## Pipeline Options

```bash
poetry run python scripts/run_full_pipeline.py \
    --geography county|tract|state   # Geography level
    --year 2022                       # Data year
    --export-excel                    # Export to Excel
    --skip-pull                       # Use cached data
    --no-db                           # Skip database storage
    --bins 5                          # Number of bins (default: 5)
```

## Using Docker (PostgreSQL)

```bash
# Start PostgreSQL
cd docker && docker-compose up -d postgres

# Run pipeline with PostgreSQL
DATABASE_URL="postgresql://cria_user:cria_password@localhost:5433/cria_db" \
    poetry run python scripts/run_full_pipeline.py \
    --geography county --year 2022 --export-excel
```

## Project Structure

```
src/
├── api/          # Census, CBP, EAVS API clients
├── core/         # DataPuller, Calculator, Aggregator, BinningEngine
├── db/           # SQLAlchemy models and repositories
└── config/       # Settings and paths

scripts/          # Production scripts
tests/            # 135+ tests
docs/             # Documentation
```

## Common Issues

### Pipeline hangs at binning step
Fixed in Bug #8. Update to latest version.

### Census API errors
Check your `CENSUS_API_KEY` in `.env`.

### Missing data columns
Run with `--skip-pull` only if you have cached input data.

## Next Steps

- [Database Schema](20251030_DATABASE_SCHEMA.md) - Understand the data model
- [Bug Fixes](20251203_BUG_FIXES_SESSION.md) - Recent fixes and calibration results
- [Production Deployment](20251108_PRODUCTION_DEPLOYMENT.md) - Full deployment guide

---

**Questions?** Open an issue at https://git-in.gss.anl.gov/jhutchison/fema_cria/issues
