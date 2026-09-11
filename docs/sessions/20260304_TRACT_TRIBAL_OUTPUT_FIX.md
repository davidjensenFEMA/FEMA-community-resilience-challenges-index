---
date: 2026-03-04
tags: [#bugfix, #tract, #tribal, #aggregation, #binning]
status: complete
---

# Fix Tract and Tribal Output Quality Issues

**Date**: 2026-03-04
**Branch**: `main`

---

## Summary

Fixed three data quality issues discovered by quality-auditor subagents during post-fix validation of tract and tribal pipeline outputs. Regenerated and re-audited both outputs — all checks pass.

## Changes Made

### D9: Tract County GEO_ID Contamination (`run_full_pipeline.py:440-455`)

**Problem**: DataPuller's `outer` merge (`data_puller.py:206`) introduces county-format GEO_IDs (`0500000US*`) alongside tract GEO_IDs (`1400000US*`). The deprecated pipeline filtered these via `data.index = tracts.index` (`cria_create_aggregate_tract.py:236`), but the refactored pipeline did not.

**Impact**: 3,215 county rows with identical z-scores (std=0 from mean imputation) all landed in Bin 4, inflating it from 11.1% to 14.3%.

**Fix**: Filter `indicators.index.str.startswith("1400000US")` before aggregation. Result: 85,382 tract-only rows with uniform bin distribution.

### D8: Tribal Zero-Population Filtering (`run_full_pipeline.py:467-497`)

**Problem**: 3,301 of 3,919 tribal GEO_IDs have zero population. When mean-imputed, they get identical values creating degenerate bins.

**Fix**: Filter to non-zero `S0101_C01_001E` before aggregation, reindex to full set afterward. Result: 618 non-zero-pop rows with valid bin distribution.

### CT Dedup: Connecticut Merge Expansion (`run_full_pipeline.py:119-122`)

**Problem**: CT's COG restructuring creates 18 county entries (9 old + 9 new planning regions). Merging tract indicators with county lookup on `(_state, _county)` expanded from 88,597 to 284,712 rows.

**Fix**: `drop_duplicates(subset=["_state", "_county"], keep="first")` on county lookup before merge.

## Validation

- **Tract output**: 85,382 rows, all `1400000US*` format, uniform bin distribution (~14.3% each), mean cria_p = 0.500006
- **Tribal output**: 618 non-zero-pop rows with valid bin distributions
- **Quality auditor**: All structural checks pass. Three "degenerate" indicators (Mobile Homes 73.3%, Limited English 71.5%, Hospitals 54.5% in bin 1) confirmed as expected real-world data skew via comparison with pre-fix archive
- **Tests**: 410 passing

## Pipeline Timing

| Geography | Step 1 (Pull) | Step 2 (Indicators) | Step 3 (Aggregation) | Total |
|-----------|--------------|--------------------|--------------------|-------|
| Tract     | ~10 min      | ~1 min             | ~53 min            | ~69 min |
| Tribal    | ~12 sec      | ~1 sec             | ~1 sec             | ~21 sec |

## Output Files

- `data/output/cria_results_tract_2024.xlsx` — 85,382 tracts
- `data/output/cria_results_tribal_2024.xlsx` — 618 tribal areas (3,919 total with NaN rows)
- `data/output/cria_inputs_tract.xlsx` — Source data
- `data/output/cria_indicators_tract_2024.xlsx` — 22 indicators

## Next Steps

- Distribute validated tract and tribal outputs to team
- Consider moving binning exceptions from `run_full_pipeline.py` to `config/indicators.yaml`
