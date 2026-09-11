# Claude Assistant Context - FEMA CRIA

## Start Here

**Before working on any task, read these files for current state:**
1. `config/project.yaml` - Project status, focus, lessons learned, known issues
2. `CHANGELOG.md` - Recent changes and version history

These are the single sources of truth. This file (CLAUDE.md) contains stable reference information that rarely changes.

## Project Overview

**FEMA CRIA** (Community Resilience Indicator Analysis) is a data analysis toolkit that collects, calculates, and aggregates community resilience indicators from various government data sources.

**Indicator definitions**: `config/indicators.yaml` - 22 indicators with sources, functions, notes

## Architecture

- **API Layer**: `src/api/` - Clients for Census, CBP, EAVS, ARDA, POP
- **Core Logic**: `src/core/` - DataPuller, Calculator, Aggregator, BinningEngine
- **Database**: `src/db/` - SQLAlchemy models, repositories, session management
- **Config**: `src/config/` - Pydantic settings, path management

## Key Files

### Core Workflow
1. **DataPuller** (`src/core/data_puller.py`) - Orchestrates API calls
2. **IndicatorCalculator** (`src/core/calculator.py`) - Calculates indicators
3. **AggregateIndicator** (`src/core/aggregator.py`) - Aggregation pipeline
4. **BinningEngine** (`src/core/binning.py`) - Statistical binning

### Database
- **Models** (`src/db/models.py`) - 7 core tables
- **Repositories** (`src/db/repositories.py`) - Data access layer
- **Migrations** (`alembic/versions/`) - Schema versioning

### Configuration
- **Project Config** (`config/project.yaml`) - Project state & metadata (READ THIS)
- **Indicators** (`config/indicators.yaml`) - 22 indicator definitions
- **Settings** (`src/config/settings.py`) - Environment variables via Pydantic
- **Paths** (`src/config/paths.py`) - Centralized path management

## Documentation Structure

```
config/
├── project.yaml      # Central state (READ FIRST)
└── indicators.yaml   # 22 indicator definitions

docs/
├── tasks.md          # Active task tracker (managed via /task)
├── guides/           # User-facing tasks and tutorials (13 guides)
│   ├── getting_started.md, pipelines.md, outputs.md, troubleshooting.md, glossary.md
│   ├── methodology.md, limitations.md, indicator_catalog.md, special_cases.md
│   └── contributing.md, extending.md, api_clients.md, operations.md
├── design/           # Architectural references (major design docs only)
│   ├── database_schema.md
│   ├── docker_guide.md
│   ├── production_deployment.md
│   └── testing_guide.md
├── plans/            # Implementation plans (active CONOPs + historical refactor plans)
│   ├── refactor_plan.md, workplan.md   (historical, completed Phases 1-8)
│   └── CONOP_*, *_review.md             (per-feature plans)
├── reviews/          # Agent audit/review reports (YYYYMMDD_<subject>.md)
└── sessions/         # Chronological session logs (with tags)

CHANGELOG.md          # Version history (READ FOR RECENT CHANGES)
```

## Slash Commands

| Command | Purpose | When to Use |
|---------|---------|-------------|
| `/session-start` | Load context for new session | Start of every session |
| `/session-end` | Close session (PCC, commit, docs) | End of every session |
| `/task` | Manage task tracker (`docs/tasks.md`) | Add, complete, block, promote tasks |
| `/sitrep` | Generate team-facing status report | Outbrief for teammates and leadership |
| `/pcc` | Pre-Code Check (quick safety) | Before every commit |
| `/pci` | Pre-Code Inspection (deep review) | Before merge to main |
| `/implement-feature` | Guided feature workflow | Adding new functionality |

## Agent Teams

6 agents and 6 team templates support structured collaboration:

- **Agents**: `cria-analyst`, `data-engineer`, `decision-scientist`, `quality-auditor`, `statistical-tester`, `proposer` (see `.claude/agents/`)
- **Teams**: `bug-fix`, `code-review`, `data-pipeline`, `indicator-development`, `test-validation`, `full-pipeline-validation` (see `.claude/teams/`)
- **Escalation**: Task → TCS → CONOP → OPORD (see `/task` command)

## Data Flow

```
External APIs → DataPuller → SourceData (DB)
                               ↓
                      IndicatorCalculator → Indicators (DB)
                               ↓
                      AggregateIndicator → AggregateIndicators (DB)
```

## Special Cases (Critical Knowledge)

These are hard-won lessons - check `config/project.yaml` lessons_learned for more:

1. **Connecticut CBP 2022**: Zeros in CBP data → NaN (special handling)
2. **Puerto Rico Limited English**: Spanish speakers → NaN (not limited English)
3. **Binning**: County uses 5 bins, Tract uses 7 bins
4. **Population Change**: Uses subset mean/std for z-scores (not full dataset)
5. **JenksCaspall**: Can infinite loop on degenerate data - use FisherJenks instead
6. **Database bulk inserts**: Use `bulk_create()` not ORM `add_all()` - 2000x faster
7. **Census tract queries**: Cannot use state wildcard - iterate per state

## Reference Data

Master reference: `data/cria_data_reference.xlsx`
- **Status** sheet: Indicator definitions, sources, functions
- **Years** sheet: Data year configuration
- Import to DB via: `scripts/import_reference_data.py`

## Common Commands

```bash
# Testing
poetry run pytest                          # All tests
poetry run pytest -m unit                  # Unit tests only
poetry run pytest --cov=src               # With coverage

# Database (SQLite for development)
DATABASE_URL="sqlite:///./cria.db" poetry run python scripts/import_reference_data.py
DATABASE_URL="sqlite:///./cria.db" poetry run python scripts/run_full_pipeline.py --geography state --year 2021

# Database (PostgreSQL for production - port 5433)
DATABASE_URL="postgresql://cria_user:cria_password@localhost:5433/cria_db" poetry run alembic upgrade head

# Docker
cd docker && docker-compose up -d postgres        # Start PostgreSQL
docker-compose down -v                            # Stop + remove volumes
```

## Production Scripts

1. **Import Reference Data**: `scripts/import_reference_data.py`
2. **Sync Geographies**: `scripts/sync_geographies.py --level county`
3. **Run Full Pipeline**: `scripts/run_full_pipeline.py --geography county --year 2021`

## Geography Levels

- **County**: Primary analysis level (5 bins)
- **Tract**: Census tract level (7 bins)
- **State**: State-level aggregation
- **Tribal**: Tribal areas (special handling)

## Quick Checklist for New Tasks

1. **Read `config/project.yaml`** - Current state, lessons learned, known issues
2. **Read `CHANGELOG.md`** - What changed recently
3. **Check `config/indicators.yaml`** - For indicator-related work
4. **Use existing patterns** - OOP structure, repository pattern, type hints
5. **Write tests first** - TDD approach
6. **Test with SQLite first** - Faster, PostgreSQL for production
7. **Check special cases above** - Avoid known pitfalls
