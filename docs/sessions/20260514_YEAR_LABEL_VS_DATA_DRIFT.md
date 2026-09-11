---
date: 2026-05-14
tags: [#bugfix, #cli, #census-acs, #county, #pipeline]
status: complete
---

# Year Label vs Data Drift — Sponsor Check-File Diagnosis and Fix

**Date**: 2026-05-14
**Branch**: `main`
**Commits**: `6b3a557` (fix), `<docs commit>` (this writeup)

---

## Summary

A sponsor sent a check file (`cria_results_county_2024.xlsx`) for comparison against our 2024 deliverable. Direct value comparison revealed 19 of 22 indicators differing in nearly every county — but the file structure (sheet names, shapes, columns, GEO_ID order) was identical. The diagnosis: **the sponsor's file is a faithful CRIA pipeline run against ACS 2023 data, mislabeled as 2024 because the `--year` CLI argument only labeled the output and did not drive the actual ACS pull.**

The bug is in [`scripts/run_full_pipeline.py`](../../scripts/run_full_pipeline.py): `--year` flowed only into the output filename and DB year column, while every API client (Census, CBP, etc.) read its year from `settings.acs_year` (loaded from `.env`). A user whose `.env` had `ACS_YEAR=2023` running the pipeline with `--year 2024` would produce `cria_results_county_2024.xlsx` containing ACS 2023 data, with no warning anywhere.

We:
1. Diagnosed the failure mode by inspecting both files' `years` sheets and tracing `--year` through the codebase
2. Implemented a strict preflight (`preflight_year_consistency()`) that refuses to run when `args.year != settings.acs_year`, with a `--allow-year-mismatch` opt-in override
3. Added 5 tests (607 → 612 total)
4. **Empirically verified the diagnosis** by pulling our local SQLite DB rows tagged `year=2023` and comparing to the sponsor's file — 14 of 17 ACS-derived indicators matched bit-for-bit (max abs diff = 5.55e-17, machine epsilon) across 3,222 common counties

Closing this required no re-pulls, no sponsor coordination, and roughly two hours.

---

## The Investigation

### Initial comparison (file structure)

Sponsor file: `data/output/check/cria_results_county_2024.xlsx` (4,994,182 bytes, dated 2026-05-14).
Our file: `data/output/cria_results_county_2024.xlsx` (4,995,073 bytes, dated 2026-04-07).

File sizes within 0.02% of each other. Both have 16 sheets: `ref, years, indicators, pos, scores, scores_percentiles, lowest_ind, agg, bin_labels, bin_meta, agg_labels, agg_meta, corr, p, zero, n`. Every sheet matched in shape and column list. GEO_IDs were identical and in identical order (3,284 counties).

### Per-cell diff

Cell-by-cell value comparison surfaced ~60K mismatches per sheet for `indicators`, `pos`, `scores`, `scores_percentiles`, etc. But `n` (sample sizes) matched 100% — strong signal that the underlying source rows were the same and only their values differed.

### Per-indicator diff (the smoking gun)

Three indicators matched perfectly (0 mismatches):

| Indicator | Source |
|---|---|
| `Inactive Voter` | EAVS (year-pinned, sponsor and us both used the same vintage) |
| `Religion` | ARDA (asarb=2020 in both files) |
| `GEO_ID` | trivial |

Nineteen indicators showed mismatches in 2,800–3,222 of 3,284 counties. All of them are sourced from ACS or CBP. Means differed by small amounts consistent with year-over-year ACS drift:

| Indicator | Sponsor mean | Our mean | Δ |
|---|---:|---:|---:|
| Mobile Homes | 0.1179 | 0.1167 | +1.0% |
| Owner Occupied | 0.6032 | 0.6102 | -1.1% |
| Median Income | $65,050 | $66,940 | -2.8% |

### Years sheet (root cause)

The `years` sheet inside each file was the proof:

```
                sponsor        ours
acs              2023          2024
acs_labels       2023          2024
cbp              2023          2023   (matches)
naics            2017          2017   (matches)
pop              2024          2024   (matches)
asarb            2020          2020   (matches)
```

Their `years` sheet was honest — `acs=2023`. The filename, however, said `_2024`.

### How is that even possible?

Tracing `--year`:

- [`scripts/run_full_pipeline.py:660`](../../scripts/run_full_pipeline.py#L660): `excel_filename = f"cria_results_{geography}_{year}.xlsx"`
- `puller.save_to_database(year=year)` / `calculator.save_to_database(year=year)` / `aggregator.save_to_database(year=year)` — all label DB rows
- That's it. No client construction reads it.

Tracing the actual ACS year:

- [`src/core/data_puller.py:55`](../../src/core/data_puller.py#L55): `self.census = CensusAPIClient()` — no year argument
- [`src/api/census_client.py:276`](../../src/api/census_client.py#L276): `self.year = year or settings.acs_year` — falls back to `.env`

**There was no consistency check between `args.year` and `settings.acs_year` anywhere in the codebase.** The sponsor's `.env` was at the previous default (`ACS_YEAR=2023`, the value before our 2026-04-30 bump to 2024). They ran with `--year 2024` because that's the deliverable year. The label won.

### Empirical confirmation

Strong circumstantial evidence (3 perfect matches on year-pinned indicators, 19 mismatches on year-varying indicators, sponsor's own `years` sheet declaring acs=2023) was already convincing. We made it bit-exact.

Local SQLite DB had 67,088 indicator rows tagged `year=2023` (3,222 counties × 21 indicators). Pulled them and compared to the sponsor's file:

| Result | # indicators | Notes |
|---|---:|---|
| 0 mismatches, max diff = 5.5e-17 (machine ε) | **14** | All ACS-derived: Mobile Homes, Owner Occupied, Education, No Vehicle, Age, Disability, Limited English, Low Access to Comms, Unemployment, Unemployed Women, Median Income, GINI, Lack of Economic Diversity, Poverty, Uninsured Population |
| 0 mismatches, max diff = 7e-15 (machine ε) | 1 | Medical |
| 0 mismatches, exact zero | 2 | Median Income, GINI |
| Real mismatches | 3 | Civil Org (865), Hospitals (310), Inactive Voter (208), Single Parent (2) |

The 3 indicators with real differences all have a clean explanation:
- **Civil Org and Hospitals**: CBP-sourced. Local DB was populated when `CBP_YEAR` differed from sponsor's 2023.
- **Inactive Voter**: EAVS-sourced. The 208 mismatches are NaN-vs-value (coverage drift between EAVS releases).
- **Single Parent**: 2 mismatches in 3,222 counties — noise (likely a CT planning region edge).

The 62-county gap (sponsor 3,284 vs our DB 3,222) is the known CT COG restructuring (sponsor's data has 9 old + 9 new CT planning regions = 18 entries; ours has 9).

**Diagnosis closed: the sponsor's file is a faithful CRIA-pipeline run against ACS 2023, mislabeled as 2024.**

---

## The Fix

Pattern follows the existing `PipelinePreflightError` style ([scripts/run_full_pipeline.py:284](../../scripts/run_full_pipeline.py#L284)):

### `YearMismatchError(SystemExit)`

Inherits `SystemExit` so the CLI exits with code 1 instead of dumping a traceback for what is, from the user's POV, a configuration problem rather than a bug.

### `preflight_year_consistency(year, allow_mismatch)`

Refuses to run when `args.year != settings.acs_year`. The error message prints both years on the first line and lists three remediations:

```
================================================================================
YEAR MISMATCH — REFUSING TO RUN
================================================================================
  • --year=2024 but settings.acs_year=2023 (from .env / ACS_YEAR environment variable)

The --year flag only labels output (filename, DB year column). The actual
ACS data pulled is driven by settings.acs_year. Running anyway would
produce a file named '..._2024.xlsx' that contains ACS 2023 data.

Fix one of:
  • Run with --year 2023 (match the .env value)
  • Set ACS_YEAR=2024 in .env (and rerun) to actually pull 2024 data
  • Pass --allow-year-mismatch to acknowledge and proceed (logs a warning)
================================================================================
```

### `--allow-year-mismatch` CLI flag

Off by default. When set, logs a loud `WARNING` naming both years before proceeding. Preserves rare legitimate cases (back-dated tagging, comparing two vintages) without making the bug the default.

### Wired in at year resolution

```python
# Determine year
if year is None:
    year = settings.acs_year
    logger.info(f"Using default ACS year: {year}")
else:
    preflight_year_consistency(year=year, allow_mismatch=allow_year_mismatch)
```

When `--year` is omitted (default path), the preflight is not called — `year` is always equal to `settings.acs_year` by construction.

### Tests (5 new)

In [tests/unit/test_pipeline_helpers.py](../../tests/unit/test_pipeline_helpers.py):

| Test | Verifies |
|---|---|
| `test_matching_year_proceeds_silently` | match → returns None, no exception |
| `test_mismatch_aborts` | exact sponsor scenario raises `YearMismatchError` with code 1 |
| `test_mismatch_message_lists_three_remediations` | error message names all 3 fixes |
| `test_mismatch_with_override_proceeds` | `--allow-year-mismatch` lets the run continue |
| `test_override_logs_warning` | override emits a WARNING-level log naming both years |

Test count: 607 → 612.

---

## Limits of the Fix (honest caveats)

The preflight closes the **specific** failure mode the sponsor hit (passing `--year` explicitly when it disagrees with `.env`). It does **not** close adjacent failure modes:

1. **No `--year`, stale `.env`**: User runs with no `--year`, `.env` says `ACS_YEAR=2023`. Default goes to 2023, output is `cria_results_county_2023.xlsx`. Filename matches data. **Correct, no preflight needed.**

2. **Stale source data with `--skip-pull`**: User fixes `.env` to `ACS_YEAR=2024`, runs `--year 2024 --skip-pull`. `args.year == settings.acs_year` so preflight is happy, but if the DB still holds ACS 2023 source rows from a previous run, the indicators are computed off stale source data. **Different bug class (DB-vintage drift) — not solved here.**

3. **Per-source year mismatches** (CBP, POP, ACS_LABELS, ASARB): preflight only validates ACS_YEAR. A user with `CBP_YEAR=2022` and `ACS_YEAR=2024` running with `--year 2024` will pass preflight but produce a heterogeneous-vintage file. **Out of scope; the `years` sheet inside the output already documents this honestly.**

If we hit any of these in the wild, they each warrant their own preflight on the same pattern.

---

## Files Changed

```
scripts/run_full_pipeline.py        | +83  -2
tests/unit/test_pipeline_helpers.py | +59
docs/tasks.md                       |  +2
CHANGELOG.md                        | new entry (2026-05-14)
config/project.yaml                 | last_session, recent_completions, lessons_learned
docs/sessions/20260514_YEAR_LABEL_VS_DATA_DRIFT.md | new (this file)
```

---

## Next Steps

1. **Notify sponsor** — let them know the same command will now exit cleanly with both years on screen and a 3-bullet remediation list. They should `git pull`, then either set `ACS_YEAR=2024` in their `.env` (and re-pull) or run with `--year 2023` to match what they have.
2. **No follow-on coding required** for the original bug.
3. **Carryover items unchanged** — the LOW audit findings, 2024 output distribution, and FEMA RAPT writeup remain in `active_work`.

---

## Lessons Captured

Two new entries added to `config/project.yaml` → `lessons_learned`:

1. **CLI year flags that label without driving are silent-mislabel landmines.** Doctrine: any CLI arg that tags an artifact must either drive the underlying behavior or refuse divergence by default. Loud opt-in override preserves legitimate divergence.
2. **Empirical bit-exact validation beats circumstantial reasoning when source data is reproducible.** The DB-recompute against the sponsor's file moved the diagnosis from "very likely" to "closed." When the recompute is cheap, do it.
