---
date: 2026-02-17
tags: [#core, #binning, #feature, #fix, #county]
status: complete
---

# Spreadsheet Enhancements: ref/years Tabs and Binning Method Metadata

**Date**: 2026-02-17
**Branch**: `main`

---

## Summary

Restored "ref" and "years" tabs to output spreadsheets, added binning method selection metadata to bin_meta/agg_meta tabs, and fixed a critical bug in the auto-select binning scoring that caused fisher_jenks to win 100% of the time.

## Problem

A colleague requested two improvements to the output Excel files:
1. The old "ref" tab (indicator reference table with settings) was missing from the new OOP output
2. The bin_meta tab didn't show which binning methodology was chosen per indicator

Investigation revealed a third issue: the `_auto_select_method()` scoring used raw `(ADCM + TSS) / 2` instead of the original center-scaled (z-scored) approach from `fit_data()`. Since FisherJenks is designed to minimize ADCM, it won every single indicator — defeating the purpose of auto-selection.

## Changes Made

### 1. Ref and Years Tabs (`src/core/aggregator.py`)

- Added `reference` and `years` parameters to `save_to_excel()`
- Builds ref DataFrame with year enrichment (maps each indicator's Source to its data year)
- Builds years DataFrame from year configuration dict
- Controls sheet ordering: ref, years first, then standard result sheets

### 2. Binning Method Metadata (`src/core/binning.py`, `src/core/aggregator.py`)

- Added `_last_fit_results` dict to BinningEngine for storing method selection metadata
- `_auto_select_method()` now stores selected method, score, and all method scores
- `get_metadata()` includes `selected_method` and `selected_score` columns
- Aggregator flows metadata through `_bin_indicators()` and `_bin_aggregate()`

### 3. Fixed Auto-Select Scoring (`src/core/binning.py`)

**Root cause**: Raw `(ADCM + TSS) / 2` scoring vs the original center-scaled approach.

The old `fit_data()` code:
```python
for fit in fit_df:
    fit_cs[fit] = center_scale(fit_df[fit])  # z-score each metric across methods
fit_cs[col_final] = (fit_cs["ADCM"] + fit_cs["TSS"]) / 2
```

The new code was missing the `center_scale()` step, using raw values instead. This let FisherJenks dominate because it optimizes for the very metrics being measured.

**Fix**: Added `_center_scale()` static method, z-score ADCM and TSS across all candidate methods before combining. Also restored `headtail_breaks` and `std_mean` to the candidate pool (6 methods instead of 4).

| Scoring | fisher_jenks | headtail_breaks | Others |
|---------|-------------|-----------------|--------|
| Before (raw) | 22/22 | 0 | 0 |
| After (center-scaled) | 19/22 | 3/22 | 0 |
| Agg meta | 3/5 | 0 | equal_interval: 1, quantiles: 1 |

### 4. Pipeline Integration (`scripts/run_full_pipeline.py`)

- Passes `calculator.reference` and `calculator.years` to `save_to_excel()`

### 5. Tests

- 8 new tests in `test_binning.py` for method metadata storage
- 4 new tests in `test_aggregator.py` for ref/years tabs and method columns
- 147 total tests, all passing

## Files Changed

| File | Change |
|------|--------|
| `src/core/binning.py` | Center-scaled scoring, method metadata, `_center_scale()`, `get_selection_metadata()` |
| `src/core/aggregator.py` | Flow metadata, ref/years tabs, sheet ordering |
| `scripts/run_full_pipeline.py` | Pass reference/years to save_to_excel |
| `tests/unit/test_binning.py` | 8 new method metadata tests |
| `tests/unit/test_aggregator.py` | 4 new ref/years/method tests |
| `docs/plans/spreadsheet_enhancements.md` | Implementation plan (complete) |

## Output Validation

Generated `cria_results_county_2024.xlsx` (4.6 MB, 11 sheets):
- **ref**: 22 indicators with year enrichment
- **years**: 6 data sources with years (acs=2024, cbp=2022, etc.)
- **bin_meta**: selected_method and selected_score per indicator
- **agg_meta**: method diversity (fisher_jenks, equal_interval, quantiles)

## Lessons Learned

- **Center-scaling is critical for method comparison.** Without z-scoring metrics across methods, a method that's designed to optimize a specific metric will always win when scored on that metric. The original code knew this — the refactored code lost it.

## Next Steps

- Tract data pull for 2022-2024
- Refresh 2024 DB records to include Population Change
- Year-over-year comparison (2023 vs 2024)
