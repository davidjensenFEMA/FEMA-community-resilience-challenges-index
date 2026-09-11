---
date: 2026-05-06
tags: [#bugfix, #docs, #database, #config, #county]
status: complete
---

# Teammate Setup Robustness — Defense-in-Depth Fail-Fast + Doctor Script

**Date**: 2026-05-06
**Branch**: `main`
**Companion to**: [20260504_CENSUS_API_ROBUSTNESS.md](20260504_CENSUS_API_ROBUSTNESS.md), [20260504_DIAGNOSTICS_AND_GIT_REFERENCE.md](20260504_DIAGNOSTICS_AND_GIT_REFERENCE.md)
**Audit reports**: [docs/reviews/20260505_teammate_setup_robustness_proposer.md](../reviews/20260505_teammate_setup_robustness_proposer.md), [docs/reviews/20260505_teammate_setup_robustness_data_engineer.md](../reviews/20260505_teammate_setup_robustness_data_engineer.md), [docs/reviews/20260505_teammate_setup_robustness_audit.md](../reviews/20260505_teammate_setup_robustness_audit.md), [docs/reviews/20260505_defense_in_depth_audit.md](../reviews/20260505_defense_in_depth_audit.md)

---

## Summary

Closed the silent-success failure mode where a fresh-clone teammate runs `scripts/run_full_pipeline.py` without first running the bootstrap scripts (`import_reference_data.py`, `sync_geographies.py`). Previously: the pipeline pulled all data, calculated indicators in memory, logged 22 `Indicator not found in database: <name>` warnings (one per indicator), and persisted nothing — reporting success while the DB stayed empty. Now: a startup preflight refuses to pull, three in-method `save_to_database` guards catch any bypass path, the parquet engine missing case raises with a remediation message, and `scripts/doctor.py` gives the teammate a single-command install report.

The 2026-05-05 sponsor escalation that triggered this — `Indicator not found in database: Mobile Homes` followed by 21 more — was diagnosed today (2026-05-06) as exactly this failure mode. Sponsor's `reference_indicators` table was empty because he had not run `import_reference_data.py`. The work landing here would have raised a `RuntimeError` naming the fix on his first run.

**Test suite**: 583 → 607 (+24). All passing in 57s.

---

## Triggering Incident

**2026-05-05** — sponsor (FEMA RAPT contact) reported the pipeline appearing to run successfully but producing no data:

```
--- Step 1: Pulling Source Data ---
  Dropping 3496 rows with invalid index
2026-05-05 08:43:42 - cria - INFO - ✓ Pulled data: (3284, 57)
2026-05-05 08:43:42 - cria - INFO - Saving source data to database...
...
Indicator not found in database: Mobile Homes
... (×22, once per indicator)
```

Two distinct sources of confusion in his console:
1. `Dropping 3496 rows with invalid index` — looked like a data error but is the documented county/tract outer-merge artifact (NaN-indexed rows that get dropped). The `(3284, 57)` shape that follows is correct.
2. `Indicator not found in database: Mobile Homes` — the actual setup failure, but presented as a per-row warning rather than a halt. The pipeline kept going and silently persisted nothing.

Sponsor also asked whether his locally-activated `python venv` could be conflicting with Poetry. Diagnosis (today): no — `poetry run python ...` always uses Poetry's managed venv regardless of an active venv in the shell. The pipeline got far enough to make API calls and return a 3,284-row dataframe; if venvs were in conflict he'd see `ModuleNotFoundError`, not application-level warnings.

---

## Root Cause

`reference_indicators` table was empty. `import_reference_data.py` (one-time-per-clone setup) had never been run. The script reads `data/cria_data_reference.xlsx` (in git) and populates the indicator definitions. Without it, every name lookup in [src/core/data_puller.py:521](../../src/core/data_puller.py#L521) returns `None` and falls through to a warning log.

Confirmed not a regression from the 2026-04-29 parquet commit (`64b469e`):
- `data/cria_data_reference.xlsx` — **indicator** reference, in git, populates DB via `import_reference_data.py` (required since the original 2025-10-30 refactor `0fc45f3`).
- `data/geographies/*.parquet` — **geography** boundary lookups, in git, loaded into memory by `_load_geographies()`. The parquet commit added these to git so fresh clones don't need a Census API round-trip.

Two independent reference datasets, both shipped, only one needs a separate import step. Pre-existing UX cliff: README at [README.md:83-87](../../README.md#L83-L87) lists the setup scripts *after* the pipeline-run examples in the quickstart block. A copy-paster scanning top-down hits the run command first and skips the setup.

---

## Design

Three layers of defense, ordered from most informative to most defensive:

### Layer 1: Preflight at pipeline startup ([scripts/run_full_pipeline.py:284-352](../../scripts/run_full_pipeline.py#L284-L352))

`preflight_database()` runs before any data pull. Counts `reference_indicators` and per-level `geographies`. Tract pulls also require county geographies (for D1 imputation of non-ACS indicators). Any zero count raises `PipelinePreflightError` (a `SystemExit` subclass) with a multi-line block listing every failure and naming the exact remediation command — and a pointer to `scripts/doctor.py` for full diagnosis. Inherits `SystemExit` so users get a clean "exit 1" instead of a traceback for what is, from their POV, a setup problem.

Why first: catches the failure in seconds before spending minutes on API pulls.

### Layer 2: In-method fail-fast in `save_to_database` (3 sites)

For callers who bypass `run_full_pipeline.py` (notebooks, ad-hoc scripts):

| Site | File | Guard |
|---|---|---|
| 1 | [src/core/data_puller.py:527-550](../../src/core/data_puller.py#L527-L550) | indicator_map empty + reference rows present → raise; geo_id_map empty + data present → raise |
| 2 | [src/core/indicators.py:446-469](../../src/core/indicators.py#L446-L469) | same two checks, error message says `indicators` table |
| 3 | [src/core/aggregator.py:719-731](../../src/core/aggregator.py#L719-L731) | geo_id_map empty + agg rows present → raise (aggregator has no indicator_map axis) |

Doctrine: **partial misses still warn-and-continue** (single missing indicator name is a data-cleanliness issue), **TOTAL miss raises** (every lookup failing is a setup-state issue). Existing per-row warnings preserved; new guards fire only when the entire mapping is empty AND there's data to write.

### Layer 3: Parquet engine missing surfaced loudly ([src/core/data_puller.py:131-145](../../src/core/data_puller.py#L131-L145))

If `pyarrow`/`fastparquet` is missing, `pd.read_parquet` raises `ImportError`. Old code caught everything and warned, then fell through to the Census API path — which returns a stripped geography reference (no `state_abbr`, `county_name`, `region`) and produces tens of thousands of NaN-indexed rows on EAVS/CBP joins. New code separately catches `ImportError` and raises with `Run 'poetry install' to install pyarrow`. Other `Exception` types still warn-and-fall-through (preserves the recovery path for transient parquet read failures).

### Layer 4 (parallel): `scripts/doctor.py`

Standalone install diagnostic. Walks env → config → data files → database (incl. `reference_indicators` row count, geography level counts) → optional Census API ping. Prints paste-friendly human-readable report (or `--json` for machine consumption). Exit codes: 0 = pass (WARNs allowed), 1 = check failed, 2 = doctor itself errored. Designed for: sponsor pastes `poetry run python scripts/doctor.py` output into chat, you read it once, you know what's wrong — no screenshot interpretation, no question round-trips.

### Drop-log rewrite ([src/core/data_puller.py:401-426](../../src/core/data_puller.py#L401-L426))

Old:
```
Dropping 3496 rows with invalid index
```
Always WARNING, no kept-count, no explanation.

New:
```
Cleaning merge artifacts: dropped 3496 NaN-indexed rows (51.6%), keeping 3284 valid rows.
Outer-merge artifact from per-source data pulls — these are rows from one source
that have no matching key in any other source.
```
INFO if drop ratio ≤ 60%, WARNING if > 60% (catches a genuine regression — e.g. corrupted geography file producing 90% NaN-indexed rows). 60% chosen because a normal county pull lands ~51%, leaving headroom for tract/state variation. Kept at INFO minimum so a future regression isn't silently demoted to DEBUG.

---

## Implementation Notes

- `count()` added to `GeographyRepository` and `ReferenceIndicatorRepository` ([src/db/repositories.py](../../src/db/repositories.py)). Geography count supports a `level` filter (state/county/tract/tribal); reference count supports `active_only`. Required for preflight; useful elsewhere.
- Preflight runs **inside** the `try:` block so a failure still closes `db_session` cleanly via the existing `finally:` block.
- `--no-db` mode bypasses preflight (intentional: backwards-compatibility path that doesn't touch the DB at all).
- Aggregator has no `indicator_map` — writes are keyed only on geography. Comment at [src/core/aggregator.py:723-724](../../src/core/aggregator.py#L723-L724) documents this so future readers don't add a phantom indicator-map guard.

---

## Audit Findings

[docs/reviews/20260505_defense_in_depth_audit.md](../reviews/20260505_defense_in_depth_audit.md) (quality-auditor adversarial review):

- **3 PASS findings** on cross-site consistency, correct ordering relative to existing per-row warnings, doctrine alignment.
- **2 LOW findings**: `if not indicator_map and len(self.reference) > 0` will raise `TypeError` if `self.reference` is `None` (`len(None)` is invalid). Unreachable in practice — `_load_reference()` always returns a DataFrame — but a latent bug if a future refactor allows None. Cheap fix: `len(self.reference) if self.reference is not None else 0 > 0`. **Not addressed in this commit** — out of scope for the current change, captured as a known issue for future cleanup.

No HIGH/CRITICAL findings.

---

## Files Changed

| File | Change |
|---|---|
| `src/core/data_puller.py` | +59 / −3: parquet ImportError, drop-log rewrite, save_to_database 2-site fail-fast |
| `src/core/indicators.py` | +23: save_to_database 2-site fail-fast |
| `src/core/aggregator.py` | +14: save_to_database geo_id_map fail-fast |
| `src/db/repositories.py` | +14: `count()` helpers on 2 repos |
| `scripts/run_full_pipeline.py` | +81: `preflight_database()` + `PipelinePreflightError` + invocation |
| `scripts/doctor.py` | +496 new: install doctor (env/config/data/DB/API checks) |
| `tests/unit/test_data_puller.py` | +263: parquet ImportError, drop-log threshold/message, fail-fast |
| `tests/unit/test_indicators.py` | +102: save_to_database fail-fast (2 sites) |
| `tests/unit/test_aggregator.py` | +78: aggregator save_to_database fail-fast + early-return |
| `tests/unit/test_pipeline_helpers.py` | +114: preflight (populated/empty/tract-cross-level/multi-failure/doctor-pointer) |

Test count: 583 → 607 (+24). Full suite passes in 57s.

---

## What This Would Have Meant for the Sponsor

If the sponsor had been on this code:

1. He runs `poetry run python scripts/run_full_pipeline.py --geography county --year 2024`.
2. Preflight runs, sees `reference_indicators` count = 0.
3. Pipeline aborts with:
   ```
   ================================================================================
   PIPELINE PREFLIGHT FAILED
   ================================================================================
   Refusing to start data pull — the database is not bootstrapped, so the
   pipeline would silently produce empty/partial output.

     • reference_indicators table is empty
         Fix: poetry run python scripts/import_reference_data.py
     • geographies table has 0 rows for level='county'
         Fix: poetry run python scripts/sync_geographies.py --level county

   Run `poetry run python scripts/doctor.py` for a full install report.
   If you intentionally want to skip database persistence, re-run with --no-db.
   ================================================================================
   ```
4. He runs the two named scripts. Re-runs the pipeline. Done.

Time to diagnosis: ~5 seconds, not a Teams thread.

---

## Outstanding (Not in Scope for This Landing)

- README quickstart reorder: setup scripts currently listed *after* the run command at [README.md:83-87](../../README.md#L83-L87). Move them before. Same fix applies to [docs/guides/getting_started.md:71](../../docs/guides/getting_started.md#L71).
- The two LOW audit findings (`self.reference is None` latent bug at fail-fast sites 1 and 2). Cheap fix when next touching the area.
- Distribute regenerated 2024 outputs to FEMA RAPT (carryover from 2026-05-04).
- Draft RAPT write-up of code changes since Jan 30 (carryover from 2026-05-04).
- Fix `CLAUDE.md:28` reference to `src/core/calculator.py` → should be `indicators.py` (carryover from 2026-05-04).

---

## Lessons Learned

1. **"Indicator not found in database" is a setup error, not a data error.** It looked like a per-indicator data issue and was logged that way (warn, continue). Reframing it as a single setup-state failure (all-empty → halt) closed the silent-success path. The doctrine: warn for partial misses, raise for total misses.

2. **Preflight pays for itself in seconds.** A 5-second DB count check at startup saves 60-138 minutes of API pulls that produce nothing. The cost is negligible (two `SELECT COUNT(*)`), the savings are large.

3. **Defense in depth, not defense in one place.** Preflight catches `run_full_pipeline.py` callers; in-method guards catch notebooks and ad-hoc scripts; doctor catches "before I even try the pipeline." Different tools for different entry points; no single guard is sufficient.

4. **The drop-log message was unnecessarily scary.** `Dropping 3496 rows with invalid index` looks like a bug. `Cleaning merge artifacts: dropped 3496 NaN-indexed rows (51.6%), keeping 3284 valid rows. Outer-merge artifact...` reads as housekeeping. Same operation, completely different perception.

5. **Parquet engine missing must be loud.** Silent fallback to the API path produces a corrupted geography reference that breaks downstream joins in non-obvious ways. The 2026-04-29 parquet commit fixed the data path; this fix closes the diagnostic gap if pyarrow gets uninstalled.
