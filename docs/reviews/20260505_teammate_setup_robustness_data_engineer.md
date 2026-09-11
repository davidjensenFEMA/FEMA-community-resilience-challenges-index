# Teammate Setup Robustness — Data Engineer Review

**Date:** 2026-05-05
**Author:** data-engineer agent
**Subject:** Diagnosis of two confusing log messages and proposals to harden the pipeline against teammate-setup failures.
**Scope:** Proposal phase only. No production code changes.

---

## 1. Diagnosis — Confirm or Correct

### Symptom A — "Indicator not found in database" (per indicator)

**Confirmed.** The teammate's `reference_indicators` table is empty because they skipped `scripts/import_reference_data.py`. The repeated warning comes from two locations, both in the database-save paths:

- `src/core/data_puller.py:491` — inside `DataPuller.save_to_database()`, in the loop over `self.reference` that builds `indicator_map` from DB IDs.
- `src/core/indicators.py:440` — the parallel loop inside `IndicatorCalculator.save_to_database()`.

Both warn per indicator and proceed. Downstream, `indicator_map` is empty, so `_find_indicator_for_column()` returns `None` for every column, every row is silently skipped, and the bulk insert at `data_puller.py:543-549` falls through to the `"No source data records to save"` warning. The pipeline reports `PIPELINE COMPLETE` with non-zero `source_data_shape` but zero rows persisted. **The actual silent-failure point is the conditional at `data_puller.py:488` (`if db_indicator:`) and `indicators.py:437` — they treat "not found" as a soft skip.** The warning at line 491/440 is the symptom; the silent-skip at lines 488 and 521-523 (the `_find_indicator_for_column` returning `None` path at line 523) is the failure mechanism.

**Reproduction:** Fresh clone → `init_db()` creates empty tables → run pipeline without `import_reference_data.py` → 22 warnings + zero DB rows + green "complete" message.

### Symptom B — "Dropping 3496 rows with invalid index"

**Confirmed.** `src/core/data_puller.py:393-397` drops NaN-indexed rows produced by the outer joins inside `pull_all_data`. The number 3496 is the artifact count for a county pull; final 3284 rows is the correct US county count. The log message is technically accurate but does not say:
1. that this is expected merge cleanup,
2. what fraction of rows is being dropped,
3. what the final row count should look like.

A user reading this in isolation cannot distinguish "the filter is doing its job" from "the filter just ate 50% of my data."

### Additional silent-failure modes you didn't list

While reading I found two more symptoms in the same family that a teammate skipping setup will hit:

1. **Empty `geographies` table** (skipped `scripts/sync_geographies.py`). At `data_puller.py:496` `geo_id_map = geo_repo.get_geo_id_map(level=...)` returns `{}`. Every row falls through `if db_geo_id is None: skipped_geos += 1; continue` (line 507-509) and emits one terminal warning at line 552: `"Skipped N geographies not found in database"`. Same pattern in `indicators.py:497`. Pipeline reports success, DB is empty. **This is structurally identical to Symptom A and deserves the same fix.**

2. **Reference-data Excel file present but `Order_2023` column empty/renamed.** `_load_reference()` at `data_puller.py:85` does `dropna(subset=["Order_2023"])` — if a future reference file uses `Order_2024`, you silently get `len(self.reference) == 0` and the pipeline pulls zero indicators with the cheerful `"Pulling 0 indicators"` log. Out of scope for the immediate fix but worth flagging.

---

## 2. Proposals — Symptom A (empty reference table)

Three interventions, ranked by recommendation.

### Recommendation 1 (preferred): Pre-flight check at pipeline start

**What:** Add a `_preflight_database_check()` function called from `run_pipeline()` immediately after `init_db()` / `get_db_session()` (around `scripts/run_full_pipeline.py:338`) and **before** Step 1. Function counts `reference_indicators` and `geographies` rows for the requested geography level. If either is zero, abort with an action-oriented error message.

**Files/lines changed:**
- `src/db/repositories.py` — add `count()` to `ReferenceIndicatorRepository` (~line 144) and `count_by_level(level)` to `GeographyRepository` (~line 86). Both one-liners using `func.count()`.
- `scripts/run_full_pipeline.py` — add `_preflight_database_check(db, geography)` near top of `run_pipeline()` (~line 338, immediately after `db_session = get_db_session()`).

**What the user sees:**
```
--- Initializing Database ---
Database initialized successfully

--- Preflight: Database Setup ---
ERROR: reference_indicators table is empty (0 rows).
       This pipeline cannot persist results without indicator definitions.

       Run this once before the pipeline:
         poetry run python scripts/import_reference_data.py

       For PostgreSQL, prefix with:
         DATABASE_URL="postgresql://..."
```

Same shape for missing geographies, naming the correct `sync_geographies.py --level <geography>` invocation.

**Failure modes introduced:** Users who legitimately want to test an empty DB (e.g., bootstrap testing) need an `--allow-empty-db` escape hatch. Cheap to add. Also, the check adds two cheap `SELECT count(*)` queries per run — negligible.

**Why this first:** It's the smallest possible intervention that converts a 22-warning silent failure into a single fatal error with the exact remediation command. It is non-destructive (does no work on the user's behalf), discoverable, and matches the pattern already in use for `confirm_suspect_api_key` at `run_full_pipeline.py:688` — preflight + actionable abort.

### Recommendation 2: Fail-fast inside `save_to_database()` after first miss

**What:** In `DataPuller.save_to_database()` and `IndicatorCalculator.save_to_database()`, when `indicator_map` is empty after the loop (i.e., the DB returned `None` for *every* indicator name), raise instead of warn-and-continue.

**Files/lines changed:**
- `src/core/data_puller.py:484-491` — after the loop, add `if not indicator_map: raise RuntimeError("reference_indicators is empty; run scripts/import_reference_data.py first")`.
- `src/core/indicators.py:433-440` — identical change.
- The per-indicator warning at line 491/440 stays (catches partial misses where the Excel has 22 indicators but the DB has 21), but the empty-map case becomes fatal.

**What the user sees:** First save attempt fails with the same actionable message as Rec. 1, but the pipeline has already pulled data. So they pay the cost of a full data pull (~minutes for county, hours for tract) before the abort.

**Failure modes introduced:** None new. Genuine improvement over the status quo. **But:** it fires *after* expensive work (data pull + post-processing), which is exactly what Rec. 1 prevents.

**Why this second:** It's a defense-in-depth complement to Rec. 1, not a replacement. Should ship together — Rec. 1 catches the common case fast, Rec. 2 catches partial-state databases (e.g., a teammate ran `import_reference_data.py` against the wrong DATABASE_URL and the current connection still has a half-empty table).

### Recommendation 3: `scripts/doctor.py` — environment + DB health check

**What:** Standalone diagnostic script — see Section 4 for full design. Documentation-only would be cheaper but ineffective: the README already says "run `import_reference_data.py`" and the teammate still hit this. The current pipeline must be loud, not the docs.

**Why this third:** It complements Rec. 1+2 by giving teammates a "tell me what's wrong" command they can run *before* attempting the pipeline. Higher leverage long-term, but Rec. 1 alone resolves the reported incident.

### Explicitly NOT recommended: Auto-bootstrap

I considered making `run_full_pipeline.py` detect an empty `reference_indicators` and silently call `import_reference_data.py`. **Do not do this.** Reasons:

- **Hides setup state from the user.** The teammate already cannot distinguish "complete" from "no data persisted" — adding more silent steps makes their mental model worse, not better.
- **Bootstraps against the wrong DATABASE_URL.** If the teammate has two DB envs configured (sqlite dev + postgres prod), auto-bootstrap will silently populate the dev DB on a prod run, or vice versa.
- **Couples the pipeline script to the import script.** They are intentionally separate so the import can be re-run safely without reprocessing.
- **`sync_geographies.py` is expensive** (Census API roundtrips, can take minutes). Auto-bootstrapping that on every run is unacceptable.

The right division: pipeline detects and explains; setup scripts execute. Never blur the line.

---

## 3. Proposal — Symptom B (alarming drop log)

The log line at `src/core/data_puller.py:396` is:

```python
logger.warning(f"  Dropping {idx_issues.sum()} rows with invalid index")
```

**Issues:**
- Message says nothing about *why* these rows exist (outer-merge artifact) or whether this is normal.
- Reports drop count without final row count, so user has no scale of reference.
- Severity is `WARNING` — but for the expected case (county pull producing ~3500 NaN rows from outer-merge), this is informational, not anomalous.

**Proposed replacement** (drop-in for `data_puller.py:393-397`):

```python
# Remove invalid indices (NaN). These are outer-merge artifacts: when a
# source has data for geographies the others don't, pandas pads with NaN
# index. Expected for any multi-source pull; final shape is what matters.
idx_issues = pd.isna(data.index)
n_dropped = int(idx_issues.sum())
if n_dropped > 0:
    n_kept = len(data) - n_dropped
    pct_dropped = (n_dropped / len(data)) * 100
    # Promote to WARNING only if we'd lose >50% of rows (genuinely anomalous).
    log_fn = logger.warning if pct_dropped > 50 else logger.info
    log_fn(
        f"  Cleaning merge artifacts: dropped {n_dropped} NaN-indexed rows "
        f"({pct_dropped:.1f}%), keeping {n_kept} valid rows. "
        f"This is expected from outer joins across data sources."
    )
    data = data.loc[~idx_issues, :].copy()
```

**What the user sees (county pull):**
```
INFO   Cleaning merge artifacts: dropped 3496 NaN-indexed rows (51.6%), keeping 3284 valid rows. This is expected from outer joins across data sources.
```

(Edge note: 51.6% would tip into WARNING under the 50% threshold above. Threshold of 60% is probably more honest for the typical county pull. I'd tune empirically — pick whichever value puts a normal county/tract/state run firmly in INFO and only escalates on real regressions.)

**Why this works:** the message tells the user (a) *what* (cleaning merge artifacts), (b) *why* (outer joins), (c) *the answer they actually care about* (3284 valid rows kept), and (d) the percentage so they can sanity-check. The severity de-escalation removes the visual alarm for the normal case while preserving WARNING for genuine anomalies.

---

## 4. Cross-cutting — `scripts/doctor.py` (or `--check`)

**Recommendation:** Build a standalone `scripts/doctor.py`. Reasons over `--check` flag:
- Users run it *before* attempting the pipeline, when they don't yet know which `--geography` or `--year` to pass.
- Composable in CI: a hermetic check that doesn't try to start the pipeline.
- Single discoverable command in `scripts/` next to the other setup scripts.

**Minimum useful version (v1):**

| Check | Method | Failure message |
|------|--------|-----------------|
| `.env` exists | `Path(".env").exists()` | `"Missing .env — copy from .env.example"` |
| `CENSUS_API_KEY` set and well-formed | reuse `validate_census_api_key_format()` from `census_client.py:72` | `"CENSUS_API_KEY missing/malformed: <reason>"` |
| `DATABASE_URL` parseable | `sqlalchemy.engine.url.make_url()` | `"DATABASE_URL invalid: <error>"` |
| DB reachable | `engine.connect()` with 2-second timeout | `"Cannot connect to <redacted url>: <error>"` |
| Schema migrated | `select(Geography).limit(1)` doesn't raise `NoSuchTableError` | `"Schema not migrated. Run: poetry run alembic upgrade head"` |
| `reference_indicators` populated | `ReferenceIndicatorRepository(db).count() > 0` | `"Empty. Run: poetry run python scripts/import_reference_data.py"` |
| Geographies populated for each level | new `GeographyRepository.count_by_level("county")` etc. | `"Empty. Run: poetry run python scripts/sync_geographies.py --level county"` |
| `data/cria_data_reference.xlsx` exists | `paths.reference_file.exists()` | `"Reference Excel missing at <path>"` |
| Census API reachable | one cheap variable lookup against ACS endpoint with a 5s timeout | `"Census API unreachable: <error>. Network or key issue."` |

**Output format:** one line per check, prefixed with `[OK]` / `[FAIL]` / `[WARN]`. Exit `0` on all OK, `1` on any FAIL. Print a summary at the end with the exact remediation commands for each failure, in order.

**Where it lives:** `scripts/doctor.py`. Add a one-liner to the README Quick Start: `poetry run python scripts/doctor.py` between `cp .env.example .env` and `poetry run python scripts/run_full_pipeline.py`.

**Future v2 additions** (not for first ship):
- Check pip/poetry environment matches `pyproject.toml`.
- Check `data/geographies/*.parquet` parquet files exist (the parquet-cache fast path at `data_puller.py:127-138`).
- Check `PIPELINE_TIMEOUT_MINUTES` is reasonable for the requested geography (tract needs 240+).

---

## 5. What I would NOT do

1. **No auto-bootstrap.** See section 2 above. The right division of labor: pipeline detects, setup scripts execute.
2. **No silencing the per-indicator warning at `data_puller.py:491` / `indicators.py:440`.** Once Rec. 1 lands, the *empty-table* case never reaches this code. The warning still has value for *partial* mismatches (e.g., teammate added a 23rd indicator to the Excel but didn't re-import) — those are real and we want loud feedback.
3. **No README-only fix.** The teammate already had a README. They still skipped the import step. Documentation is necessary but not sufficient — the runtime must enforce.
4. **No retroactive "auto-skip if not in DB" mode.** Tempting to add `--no-db-validation` for users who want to run the calculator without DB persistence. The `--no-db` flag at `run_full_pipeline.py:651-655` already exists for that exact case. We don't need a second knob.
5. **No combining the preflight check with the existing `confirm_suspect_api_key` prompt.** They have different audiences — the API-key check is interactive (TTY-gated y/N), the DB check should be a hard fail with an exit code. Mixing them muddies behavior in CI.
6. **No "soft mode" where the pipeline continues writing to Excel but skips DB.** A user who passed `use_database=True` expects DB persistence. Silently switching to Excel-only is the same failure mode as today, just more polite. Fail loudly, recover deliberately.

---

## Summary of file-level changes proposed (not yet implemented)

| File | Lines | Change |
|------|-------|--------|
| `src/db/repositories.py` | ~144, ~86 | Add `ReferenceIndicatorRepository.count()` and `GeographyRepository.count_by_level()` |
| `scripts/run_full_pipeline.py` | ~338 | Insert `_preflight_database_check(db, geography)` between session init and Step 1 |
| `src/core/data_puller.py` | 484-491 | After loop, raise if `indicator_map` empty |
| `src/core/indicators.py` | 433-440 | Mirror change |
| `src/core/data_puller.py` | 393-397 | Replace alarming drop log with informational, contextual variant |
| `scripts/doctor.py` | new | Health-check entry point — env, DB, ref data, geographies, Census API |
| `README.md` | Quick Start | Add `poetry run python scripts/doctor.py` between `.env` setup and pipeline |

All changes are additive or replace warning messages with clearer text. None alter pipeline outputs.
