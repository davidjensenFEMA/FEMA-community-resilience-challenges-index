# Pipelines

Every CLI flag, every geography, every common workflow. Read this when you want to do anything more advanced than "run county and look at the output."

If you're brand new, start with [getting_started.md](getting_started.md).

---

## Pipeline overview

`scripts/run_full_pipeline.py` orchestrates four steps:

1. **Pull source data** — `DataPuller` calls Census ACS, CBP, EAVS, ARDA, and POP APIs.
2. **Calculate indicators** — `IndicatorCalculator` applies the 22 indicator formulas (`config/indicators.yaml`).
3. **Aggregate** — `AggregateIndicator` reorients indicators so all 22 point the same way (positive = resilience), z-scores them, takes the **mean** to produce the resilience composite (`agg`), then computes the challenge composite as `cri = -agg` and percentile rank `cria_p`. Also computes pairwise correlations.
4. **Bin** — `BinningEngine` classifies each indicator and the composite into 5 bins (county/state/tribal) or 7 bins (tract).

Each step persists to the database (default) and optionally to Excel (`--export-excel`).

---

## Geographies

| `--geography` | Rows | Bins | Notes |
|---------------|------|------|-------|
| `state` | 51 (incl. DC) | 5 | Fastest. Good for development and testing changes. |
| `county` | ~3,200 | 5 | The canonical CRCI deliverable. ~5–15 min. |
| `tract` | ~85,000 | 7 | ~2 hours. Non-ACS indicators (CBP/EAVS/ARDA/POP) are imputed from the parent county. |
| `tribal` | ~700 | 5 | **Binning only** — no aggregation, no composite CRCI. Drops non-ACS indicators entirely. Matches the deprecated pipeline. |

---

## CLI flags

```
--geography {state,county,tract,tribal}   Geography level (default: county)
--year YEAR                                Data year (default: ACS_YEAR from .env)
--export-excel                             Write workbooks to data/output/
--no-db                                    Skip database writes (backwards-compat mode)
--skip-pull                                Reuse existing source data; skip API calls
--bins N                                   Override default bin count
--timeout N                                Wall-clock timeout in minutes
```

### Detailed flag notes

**`--export-excel`** — without this, the pipeline only writes to the database. If you want the Excel deliverables (and you almost always do), you must pass it.

**`--no-db`** — useful when re-running for a year that's already in the database (avoids `UniqueViolation` on duplicate keys). Also useful if you don't have PostgreSQL running and want a quick SQLite-only run with no persistence at all.

**`--skip-pull`** — reuses the source data from the most recent run. Big time-saver when you're iterating on the indicator/aggregation logic and don't need fresh API data. Note: it relies on cached state in `DataPuller`, so this is mostly useful when run inside the same session or after a successful pull.

**`--bins N`** — overrides the default. The defaults match the deprecated pipeline (county/state/tribal = 5, tract = 7). Don't change this unless you have a specific reason.

**`--timeout N`** — kills the run after N minutes. The default (60) is fine for state/county. For tract you need at least **240** (saving 88K source records to PostgreSQL takes ~63 minutes by itself).

---

## Year configuration

Every API has its own data calendar. The `--year` flag is the *target year* for the deliverable; the pipeline maps it to per-source years via `.env`:

| `.env` variable | What it controls | Typical 2024-target value |
|-----------------|------------------|---------------------------|
| `ACS_YEAR` | Census ACS 5-year endpoint | `2023` (released Dec 2024) |
| `CBP_YEAR` | County Business Patterns | `2023` (released early 2025) |
| `NAICS_YEAR` | NAICS code revision | `2017` (latest stable) |
| `POP_YEAR` | Population Estimates Program | `2024` |
| `ASARB_YEAR` | ARDA religion data | `2020` (decennial) |
| `ACS_LABELS_YEAR` | ACS variable labels | `2023` |

The naming is a little confusing — `ACS_YEAR=2023` produces a "2024" deliverable because ACS 5-year data lags by one year. The matrix above is the current state; for a year-by-year breakdown of the full mapping (including historical years), see `.env.example` comments and `config/project.yaml`.

When you upgrade to a new target year, edit `.env` first, then run the pipeline with `--year <new>`.

---

## Common workflows

### Fresh county run (most common)

```bash
poetry run python scripts/run_full_pipeline.py \
  --geography county \
  --year 2024 \
  --export-excel
```

Produces `cria_inputs_county.xlsx`, `cria_indicators_county_2024.xlsx`, `cria_results_county_2024.xlsx`, and `data/output/reports/Correlation Matrix COUNTY.xlsx`.

### Tract run (long, needs timeout bump)

```bash
poetry run python scripts/run_full_pipeline.py \
  --geography tract \
  --year 2024 \
  --export-excel \
  --timeout 240
```

Allow ~2 hours. Watch the logs — the slowest phase is saving source data to PostgreSQL.

### Re-export Excel for a year already in the database

The DB will reject duplicate keys, so skip persistence:

```bash
poetry run python scripts/run_full_pipeline.py \
  --geography county \
  --year 2024 \
  --export-excel \
  --no-db
```

### All four geographies for a release

Run them in this order. Tract is by far the longest, so kick it off last (or in a separate shell):

```bash
for geo in state county tribal; do
  poetry run python scripts/run_full_pipeline.py \
    --geography "$geo" --year 2024 --export-excel
done

poetry run python scripts/run_full_pipeline.py \
  --geography tract --year 2024 --export-excel --timeout 240
```

### Switch to PostgreSQL for a single run

```bash
DATABASE_URL="postgresql://cria_user:cria_password@localhost:5433/cria_db" \
  poetry run python scripts/run_full_pipeline.py \
  --geography county --year 2024 --export-excel
```

The `docker compose up -d postgres` and `alembic upgrade head` setup is documented in [getting_started.md](getting_started.md#7-optional-switch-to-postgresql).

---

## Helper scripts

These are not the pipeline, but you'll touch them occasionally.

| Script | Purpose | When to run |
|--------|---------|-------------|
| `scripts/import_reference_data.py` | Loads `data/cria_data_reference.xlsx` into the DB | Once per database. Idempotent. |
| `scripts/sync_geographies.py --level <geo>` | Pulls geography reference from the Census `/geo` API | Only if you need to refresh; the repo ships with parquet fixtures. |
| `scripts/database_backup.sh` | Dumps the PostgreSQL database to `data/backups/` | Before risky operations |
| `scripts/database_restore.sh` | Restores from a backup file | After accidental data loss |
| `scripts/run_tests.sh` | Convenience wrapper around `pytest` | CI and local |

---

## Pipeline timeouts

Set `PIPELINE_TIMEOUT_MINUTES` in `.env` to change the global default, or use `--timeout` for a one-off override. Recommended values:

| Geography | Minimum | Recommended |
|-----------|---------|-------------|
| `state` | 30 | 60 |
| `county` | 30 | 60 |
| `tribal` | 30 | 60 |
| `tract` | 180 | 240 |

The timeout is a hard kill (SIGALRM on Unix). If you hit it, the partial run is discarded.

---

## What you can change without breaking calibration

The pipeline is calibrated against a baseline (county 0.94 correlation, tract 1.0). Safe changes:

- Year selections in `.env`
- `--bins` (overrides default; bin counts don't affect z-scores)
- Output formatting tweaks in `aggregator.save_to_excel`

Unsafe changes (will break calibration — run the `decision-scientist` agent first):

- Indicator formulas or orientation in `config/indicators.yaml`
- Z-score normalization in `IndicatorCalculator`
- Special-case handling (CT CBP, PR Limited English, EAVS -88/-99, Pop Change subset stats)
- Manual bin boundaries in `BinningEngine.MANUAL_BINS`

See [troubleshooting.md](troubleshooting.md) for the special cases.

---

## Programmatic use (Python API)

For embedding CRCI in another script or notebook:

```python
from src.core.data_puller import DataPuller
from src.core.indicators import IndicatorCalculator
from src.core.aggregator import AggregateIndicator

puller = DataPuller(geography="county")
source_data = puller.pull_all_data()

calc = IndicatorCalculator(geography="county")
indicators = calc.calculate_all_indicators(source_data=source_data)

agg = AggregateIndicator(geography="county", bins=5)
results = agg.create_aggregate(
    indicators=indicators,
    reference=calc.reference,
    geo_reference=calc.data_puller.geographies["county"],
    bin_indicators=True,
)

# results is a dict with keys: indicators, pos, scores, scores_percentiles,
# lowest_ind, agg, bin_labels, bin_meta, agg_labels, agg_meta, corr, p, zero, n
```

For the full set of special-case parameters (`exceptions`, `skip_aggregation`), see how `scripts/run_full_pipeline.py` calls `create_aggregate`.
