# Getting Started with CRCI

This guide walks you from a fresh clone to a successful state-level pipeline run that produces deliverable Excel workbooks.

If you already have CRCI running and just need a reference, jump to:
- [Pipelines guide](pipelines.md) — running the pipeline at scale, all CLI flags
- [Outputs guide](outputs.md) — what's in the workbooks
- [Troubleshooting guide](troubleshooting.md) — common errors and special cases

---

## Prerequisites

| Tool | Why | Notes |
|------|-----|-------|
| **Python 3.11+** | Required by Poetry/SQLAlchemy 2.0 | Check: `python3 --version` |
| **Poetry** | Dependency manager | Install: `pipx install poetry` (preferred) or `curl -sSL https://install.python-poetry.org \| python3 -` |
| **Census API key** | Required for ACS, CBP pulls | Free, takes 1–2 minutes: [api.census.gov/data/key_signup.html](https://api.census.gov/data/key_signup.html) |
| **Docker** | Optional, for PostgreSQL | Only needed if you want production-grade storage. SQLite works for everything else. |

The project ships geography reference parquet files in the repo, so a fresh clone does not need to call the Census `/geo` API just to start.

---

## 1. Clone and install

```bash
git clone <repository-url>
cd fema_cria
poetry install
```

Poetry creates an isolated virtualenv and installs every dependency declared in `pyproject.toml`. Expect the install to take 1–3 minutes.

Verify the install worked:

```bash
poetry run python -c "from src.core.aggregator import AggregateIndicator; print('ok')"
```

---

## 2. Configure the environment

```bash
cp .env.example .env
```

Open `.env` and set your Census API key:

```
CENSUS_API_KEY=your_actual_key_here
```

The default `.env.example` ships with sensible defaults for everything else:
- `DATABASE_URL=sqlite:///./cria.db` — SQLite, no server needed
- `ACS_YEAR=2023` (and other per-source years) — produces a 2024-deliverable. See [years.md](years.md) before changing.
- `PIPELINE_TIMEOUT_MINUTES=60` — fine for state/county; tract runs need 240+

You can leave the rest at their defaults until you have a reason to change them.

> **Important**: `--year` on the CLI sets the *deliverable year* (filename and `years` tab). It does **not** override the per-source years in `.env`. If you want a 2023-deliverable, change both `--year 2023` and the per-source variables in `.env`. Otherwise you may get a 2024-vintage indicator labeled 2023.

---

## 3. Bootstrap the database (one time per clone)

Two scripts populate the tables the pipeline reads from. Both are idempotent — safe to re-run, fast, and required: the pipeline runs a preflight check at startup and refuses to begin a multi-minute data pull if either is missing.

**3a. Import reference data** — populates the indicator definitions, year configurations, and labels from `data/cria_data_reference.xlsx`:

```bash
poetry run python scripts/import_reference_data.py
```

**3b. Sync geographies** — populates the geography lookup table for the level you'll run. Since the next step uses `--geography state`, sync the state level now (county/tract/tribal each need their own sync before you run them):

```bash
poetry run python scripts/sync_geographies.py --level state
```

Or sync all four levels at once if you want to skip the per-level step later:

```bash
poetry run python scripts/sync_geographies.py
```

> **If you skip either step**, the pipeline halts immediately at preflight with a `PipelinePreflightError` naming the script you missed. No silent failures, no partial output.

> **Diagnostic anytime**: `poetry run python scripts/doctor.py` prints a paste-friendly install report covering env vars, data files, database state, and (with `--check-api`) a Census API ping. Use this whenever the pipeline misbehaves before reaching for chat.

---

## 4. Your first pipeline run

Start with **state** — it's the fastest geography (51 rows including DC, finishes in a few minutes) and confirms every step of the pipeline works end-to-end:

```bash
poetry run python scripts/run_full_pipeline.py \
  --geography state \
  --year 2024 \
  --export-excel
```

You should see logs like:

```
================================================================================
FEMA CRIA PIPELINE
================================================================================
Geography: state
Year: 2024
...
--- Step 1: Pulling Source Data ---
✓ Pulled data: (51, N)
--- Step 2: Calculating Indicators ---
✓ Calculated indicators: (51, 22)
--- Step 3: Creating Aggregate Scores ---
✓ Created aggregates: 51 geographies
================================================================================
PIPELINE COMPLETE
================================================================================
```

---

## 5. Inspect the output

Three workbooks land in `data/output/`:

| File | What's in it |
|------|--------------|
| `cria_inputs_state.xlsx` | Raw source data pulled from each API |
| `cria_indicators_state_2024.xlsx` | The 22 calculated indicator values, one row per state |
| `cria_results_state_2024.xlsx` | Indicators + z-scores + bins + composite CRCI score (16 tabs) |

Open `cria_results_state_2024.xlsx` and look at:
- The **`indicators`** tab — true values (NaN for missing data, e.g. EAVS non-reporters)
- The **`agg`** tab — composite columns per state. Note: `agg` itself is the **mean of z-scores** (high = high resilience); the headline challenge column is `cri = −agg` (high = high challenge). See [outputs.md](outputs.md#composite-columns-the-agg-tab).
- The **`bin_labels`** tab — each indicator binned 1–5 (1 = least challenge, 5 = most)
- The **`agg_labels`** tab — composite CRCI bin per state

Open `data/output/reports/Correlation Matrix STATE.xlsx` for the auto-generated, human-labeled correlation report.

For a tab-by-tab walkthrough see [outputs.md](outputs.md).

---

## 6. Try a county run

Once state works, run county. It takes longer (~5–15 minutes depending on network) but produces the canonical CRCI deliverable.

First sync the county geographies (skip this if you ran the all-levels sync in step 3b):

```bash
poetry run python scripts/sync_geographies.py --level county
```

Then run the pipeline:

```bash
poetry run python scripts/run_full_pipeline.py \
  --geography county \
  --year 2024 \
  --export-excel
```

For tract runs (~2 hours, 85,000 rows) read [pipelines.md](pipelines.md) first — you'll need to bump the timeout, and tract pulls require **both** `--level tract` and `--level county` synced (county feeds the D1 imputation step for non-ACS indicators).

---

## 7. Optional: switch to PostgreSQL

SQLite is fine for development. For production-scale persistence:

```bash
cd docker && docker compose up -d postgres
poetry run alembic upgrade head
```

Then point `DATABASE_URL` at the container (port `5433` from the host):

```
DATABASE_URL=postgresql://cria_user:cria_password@localhost:5433/cria_db
```

PostgreSQL is required if you want to keep multiple years of source data side-by-side and query across them.

---

## What's next

- [pipelines.md](pipelines.md) — every CLI flag, geography-by-geography recipes, year configuration
- [outputs.md](outputs.md) — every tab in every workbook, what indicators mean, how bins work
- [troubleshooting.md](troubleshooting.md) — when things go wrong (and the special cases that look like bugs but aren't)
- [`config/indicators.yaml`](../../config/indicators.yaml) — the 22 indicators, their formulas and sources
- [`config/project.yaml`](../../config/project.yaml) — current project state and lessons learned
