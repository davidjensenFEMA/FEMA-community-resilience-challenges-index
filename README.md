# FEMA CRCI - Community Resilience Challenges Index

[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](pyproject.toml)
[![Tests](https://img.shields.io/badge/tests-541%20passing-brightgreen)](tests/)
[![License](https://img.shields.io/badge/license-TBD-lightgrey)]

**CRCI quantifies community resilience challenges by calculating 22 validated indicators from authoritative government data sources.** The toolkit automates data collection, transformation, and aggregation to produce consistent, reproducible challenge scores at multiple geographic levels.

## Why CRCI

Emergency managers and planners need objective measures of community challenges to prioritize resources and identify vulnerable areas. CRCI addresses this by:

- **Standardizing measurement** - 22 indicators with documented methodologies
- **Ensuring reproducibility** - Automated pipelines eliminate manual data processing errors
- **Enabling comparison** - Consistent scoring across 3,200+ counties and 85,000+ census tracts
- **Supporting multiple scales** - County, tract, state, and tribal geographies

## Quick Start

```bash
# Clone and configure
git clone <repository-url>
cd <project-folder>
cp .env.example .env
# Add your CENSUS_API_KEY to .env

# Install
poetry install

# Bootstrap the database (one-time per clone, per geography level)
poetry run python scripts/import_reference_data.py
poetry run python scripts/sync_geographies.py --level county

# Run the pipeline
poetry run python scripts/run_full_pipeline.py --geography county --year 2024 --export-excel
```

The `--export-excel` flag writes the deliverable workbooks to `data/output/`. Without it, the pipeline only persists results to the database.

**Skip the bootstrap step and the pipeline halts at preflight** — `import_reference_data.py` populates the indicator definitions, `sync_geographies.py` populates the geography lookup table for the level you'll run. Both are idempotent. For tract runs you also need `--level county` (used for non-ACS imputation), and for state/tribal runs swap `--level county` above for the level you want.

If anything goes sideways, run `poetry run python scripts/doctor.py` for a paste-friendly install report covering env vars, data files, database state, and an optional Census API ping.

**Prerequisites**: Python 3.11+, [Poetry](https://python-poetry.org/), [Census API Key](https://api.census.gov/data/key_signup.html)

## Indicators

CRCI calculates 22 challenge indicators across domains:

| Domain | Examples |
|--------|----------|
| **Economic** | Unemployment, business scarcity, income instability |
| **Social** | Educational gaps, uninsured population, civic disengagement |
| **Infrastructure** | Housing vulnerability, communication gaps, transportation barriers |
| **Community** | Social isolation, population instability |

Higher scores indicate greater challenges to community resilience.

Full indicator definitions: [`config/indicators.yaml`](config/indicators.yaml)

## Data Sources

| Source | Data Provided | Update Frequency |
|--------|---------------|------------------|
| **Census ACS** | Demographics, housing, economics | Annual (5-year estimates) |
| **County Business Patterns** | Business establishments by sector | Annual |
| **EAVS** | Voter registration rates | Biennial |
| **ARDA** | Religious congregation counts | Decennial |
| **Population Estimates** | Migration and population change | Annual |

## Usage

### Command Line

#### One-time-per-clone setup

The pipeline refuses to start if either the indicator definitions or the geography lookup table is missing — these two scripts populate them.

```bash
# Populate indicator/year tables from data/cria_data_reference.xlsx (idempotent)
poetry run python scripts/import_reference_data.py

# Populate the geographies table for the level you plan to run (idempotent)
poetry run python scripts/sync_geographies.py --level county    # for county or tract runs
poetry run python scripts/sync_geographies.py --level state     # for state runs
poetry run python scripts/sync_geographies.py --level tribal    # for tribal runs
poetry run python scripts/sync_geographies.py                   # all four levels at once
```

Tract runs require **both** `--level tract` and `--level county` synced (county feeds the D1 imputation step for non-ACS indicators).

#### Pipeline runs

The pipeline supports four geographies. Always pass `--export-excel` when you want the deliverable workbooks; otherwise results are persisted only to the database.

```bash
# County-level analysis (all US counties, 5 bins)
poetry run python scripts/run_full_pipeline.py --geography county --year 2024 --export-excel

# State-level analysis (51 rows including DC)
poetry run python scripts/run_full_pipeline.py --geography state --year 2024 --export-excel

# Census tract analysis (~85,000 tracts, 7 bins, ~2 hours — see --timeout)
poetry run python scripts/run_full_pipeline.py --geography tract --year 2024 --export-excel --timeout 240

# Tribal areas (binning only, no aggregation — matches deprecated pipeline)
poetry run python scripts/run_full_pipeline.py --geography tribal --year 2024 --export-excel

# Reuse existing source data from the database (skip the API pulls)
poetry run python scripts/run_full_pipeline.py --geography county --year 2024 --skip-pull --export-excel
```

#### Diagnostics

```bash
# Paste-friendly install report — env vars, data files, DB state, optional API ping
poetry run python scripts/doctor.py

# Same, but also pings the Census API to verify the key works
poetry run python scripts/doctor.py --check-api

# Machine-readable
poetry run python scripts/doctor.py --json
```

Run `doctor.py` first if anything in the pipeline misbehaves — it short-circuits the back-and-forth of figuring out which prerequisite is missing.

### CLI Flags (`run_full_pipeline.py`)

| Flag | Default | Description |
|------|---------|-------------|
| `--geography` | `county` | One of `state`, `county`, `tract`, `tribal` |
| `--year` | `ACS_YEAR` from `.env` | Data year (typically 2024) |
| `--export-excel` | off | Write `cria_inputs_*.xlsx`, `cria_indicators_*.xlsx`, `cria_results_*.xlsx` to `data/output/` |
| `--skip-pull` | off | Reuse existing source data; skip the API calls |
| `--no-db` | DB on | Run without persisting to the database (backwards-compatibility mode) |
| `--bins` | 7 for tract, 5 for others | Override the default bin count |
| `--timeout` | `PIPELINE_TIMEOUT_MINUTES` from `.env` (60) | Wall-clock guardrail in minutes; tract runs need 240+ |

### Output Files

When `--export-excel` is set, three workbook families land in `data/output/`:

| File pattern | Contents |
|--------------|----------|
| `cria_inputs_<geo>.xlsx` | Raw source data pulled from each API (one tab per source) |
| `cria_indicators_<geo>_<year>.xlsx` | The 22 calculated indicators (one row per geography) |
| `cria_results_<geo>_<year>.xlsx` | Indicators + z-scores + bins + CRCI composite + correlation tabs (16 tabs total for county/tract/state; 6 for tribal) |

A formatted correlation report is also auto-generated to `data/output/reports/Correlation Matrix <GEO>.xlsx` for county and tract runs.

### Python API

```python
from src.core.data_puller import DataPuller
from src.core.indicators import IndicatorCalculator
from src.core.aggregator import AggregateIndicator

# Collect data from government APIs
puller = DataPuller(geography="county")
source_data = puller.pull_all_data()

# Calculate challenge indicators
calculator = IndicatorCalculator(geography="county")
indicators = calculator.calculate_all_indicators(source_data=source_data)

# Aggregate to composite challenge scores
aggregator = AggregateIndicator(geography="county", bins=5)
results = aggregator.create_aggregate(
    indicators=indicators,
    reference=calculator.reference,
    geo_reference=calculator.data_puller.geographies["county"],
    bin_indicators=True,
)
# results is a dict of DataFrames (indicators, pos, scores, agg, bin_labels, ...)
```

Full API including special-case handling for CT/PR/EAVS: see [`docs/guides/pipelines.md`](docs/guides/pipelines.md#programmatic-use-python-api).

## Architecture

```
src/
├── api/          # Government API clients (Census, CBP, EAVS, ARDA)
├── core/         # Pipeline logic (DataPuller, Calculator, Aggregator, BinningEngine)
├── db/           # Database layer (SQLAlchemy models, repositories)
└── config/       # Settings and path management
```

**Technology Stack**: Python 3.11, SQLAlchemy 2.0, PostgreSQL/SQLite, Poetry, Docker

## Database

CRCI supports both SQLite (development) and PostgreSQL (production):

```bash
# SQLite (default, zero configuration)
poetry run python scripts/run_full_pipeline.py --geography county --year 2024 --export-excel

# PostgreSQL (production)
docker compose -f docker/docker-compose.yml up -d postgres
poetry run alembic upgrade head
DATABASE_URL="postgresql://cria_user:cria_password@localhost:5433/cria_db" \
  poetry run python scripts/run_full_pipeline.py --geography county --year 2024 --export-excel
```

## Testing

```bash
poetry run pytest                    # All tests
poetry run pytest -m unit            # Unit tests only
poetry run pytest --cov=src          # With coverage report
```

## Validation

CRCI output is validated against the deprecated reference pipeline (the original Argonne implementation) to ensure that refactors preserve numerical results:

| Geography | Year | Indicators | Correlation vs. baseline | Status |
|-----------|------|------------|--------------------------|--------|
| County | 2022 | 22 | **0.94** | Validated |
| County | 2023 | 22 | — | Validated (3,222 counties) |
| Tract | 2021 | 17 | **1.00** | Perfect |

**What this validates**: that the current pipeline reproduces the deprecated pipeline's numbers. **What it does NOT validate**: construct validity, predictive validity, or that the indicators correctly measure community resilience challenges. See [`docs/guides/methodology.md`](docs/guides/methodology.md) for what calibration does and does not justify.

## Documentation

### User guides — generalist

| Guide | When to read |
|-------|--------------|
| [`docs/guides/getting_started.md`](docs/guides/getting_started.md) | First-time setup — fresh clone to first successful run |
| [`docs/guides/pipelines.md`](docs/guides/pipelines.md) | Every CLI flag, geography-by-geography recipes, year configuration |
| [`docs/guides/outputs.md`](docs/guides/outputs.md) | What's in every workbook tab; how bins and the composite CRCI work |
| [`docs/guides/troubleshooting.md`](docs/guides/troubleshooting.md) | Common errors and special cases that look like bugs but aren't |
| [`docs/guides/glossary.md`](docs/guides/glossary.md) | MAUT, ADCM, z-score, GEO_ID prefixes, and other terms — read this first if anything is jargon |

### Domain & methodology

| Guide | When to read |
|-------|--------------|
| [`docs/guides/methodology.md`](docs/guides/methodology.md) | Equal weights, z-scores, orientation, what the calibration targets validate (and don't) |
| [`docs/guides/limitations.md`](docs/guides/limitations.md) | What CRCI can't tell you, common misuses, how to cite responsibly |
| [`docs/guides/indicator_catalog.md`](docs/guides/indicator_catalog.md) | All 22 indicators with formula, source, function type, orientation, notes |
| [`docs/guides/special_cases.md`](docs/guides/special_cases.md) | The 15 domain quirks (CT planning regions, PR Limited English, EAVS -88, Population Change handling, etc.) |

### Engineering & operations

| Guide | When to read |
|-------|--------------|
| [`docs/guides/contributing.md`](docs/guides/contributing.md) | Branches, PRs, test markers, calibration check, the `.claude/` agent system |
| [`docs/guides/extending.md`](docs/guides/extending.md) | Adding a new indicator, API source, geography level, or schema column |
| [`docs/guides/api_clients.md`](docs/guides/api_clients.md) | Per-client docs (Census, CBP, EAVS, ARDA, POP) — quirks, rate limits, year configuration |
| [`docs/guides/operations.md`](docs/guides/operations.md) | Backups, migrations, multi-year DB queries, observability |

### Architecture & reference

The `docs/design/` directory holds the architectural references — read these when extending the system or onboarding a new contributor.

| Document | Description |
|----------|-------------|
| [`config/indicators.yaml`](config/indicators.yaml) | Indicator definitions and methodologies |
| [`config/project.yaml`](config/project.yaml) | Current project state and lessons learned |
| [`docs/design/database_schema.md`](docs/design/database_schema.md) | PostgreSQL schema design — ER diagram, table specs, column docs |
| [`docs/design/docker_guide.md`](docs/design/docker_guide.md) | Docker development environment setup and architecture |
| [`docs/design/production_deployment.md`](docs/design/production_deployment.md) | Production deployment architecture and procedures |
| [`docs/design/testing_guide.md`](docs/design/testing_guide.md) | Testing philosophy, structure, and conventions |
| [`docs/plans/`](docs/plans/) | Historical refactor plans and active CONOPs |

## License

License pending legal review.

## Acknowledgments

Developed by Argonne National Laboratory with sponsorship from the Federal Emergency Management Agency (FEMA).
