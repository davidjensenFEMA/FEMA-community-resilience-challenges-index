---
date: 2026-04-07
tags: [#indicators, #aggregation, #binning, #county, #tract, #tribal, #feature]
status: complete
---

# RAPT Team Features: Lowest Indicators, Correlation Matrix, Pop Change Bins

**Date**: 2026-04-07
**Branch**: `main`
**Follows**: [20260325_IMPUTATION_AND_NODATA_FIX.md](20260325_IMPUTATION_AND_NODATA_FIX.md)

---

## Summary

Addressed 3 of 4 questions from the FEMA RAPT team. Rebuilt the `lowest_ind` tab (top 3 drivers of resilience per geography) and full correlation matrix output (r, p-values, significance, sample sizes) from the deprecated codebase. Fixed population change bin direction so most change = bin 5 (was reversed). Regenerated all 2024 output.

Question #3 (high-level write-up of code changes since Jan 30) deferred to next session.

## Problem Statement

The RAPT team asked:
1. **Lowest indicators**: "Did we lose the top 3 drivers of resilience? In the old spreadsheet it was on a tab called lowest_ind." — Yes, it was not rebuilt. Now restored.
2. **Correlation matrix**: "We'll need the correlation matrix for county and tract. Is that an easy add?" — Partially rebuilt (r-only function existed but was unused). Now fully rebuilt with p-values, significance, and sample sizes.
3. **Write-up**: Deferred.
4. **Pop change bins**: "The bins for population change are reversed. We want the most change to be in bin 5." — Fixed. Both `pop change` and `pop_p` now use ascending labels.

## Changes Made

### Feature 1: Pop Change Bin Direction (`src/core/binning.py`)

**Commit**: `ba2668f`

Changed `MANUAL_BINS` for `"pop change"` and `"pop_p"` from `reverse: True` to `reverse: False` (lines 39-46).

| Before | After |
|--------|-------|
| Most change = bin 1 | Most change = bin 5 |
| Least change = bin 5 | Least change = bin 1 |

This is an intentional departure from the deprecated code, which used `labels=range(1, len(list_bins))[::-1]`. The deprecated comment said "lower group, higher resilience" but the user wants standard ascending order where bin number tracks with value magnitude.

### Feature 2: Lowest Indicators Tab (`src/core/aggregator.py`)

New method `_compute_lowest_indicators(df_scores, n=3)`:
- Uses `np.argsort(values, axis=1)[:, :n]` to find the n indicators with lowest z-scores per geography
- Returns DataFrame with columns: `ind_1, ind_1_score, ind_2, ind_2_score, ind_3, ind_3_score, list_labels`
- Handles edge cases: fewer than n indicators (caps n), empty DataFrame (returns empty)
- Replicates `deprecated/old_scripts/cria_create_aggregate_indicator.py:140-167`
- Added to pipeline as Step 9, output dict key `"lowest_ind"`, Excel sheet order after `scores_percentiles`

### Feature 3: Full Correlation Matrix (`src/core/transformations.py` + `src/core/aggregator.py`)

**New functions in transformations.py:**

`pearsonr_ci(x, y, alpha=0.05)`:
- Pearson r with Fisher z-transformation confidence interval
- Fixes deprecated bug: uses valid pair count (pairwise NaN deletion) instead of raw `len(x)`
- Returns `(r, p, ci_lower, ci_upper, n_valid)`
- Guard: returns all NaN if < 3 valid pairs

`calc_full_corr_matrix(data, alpha=0.05)`:
- Full pairwise correlation for all columns
- Returns 4 DataFrames: `corr_r`, `corr_p`, `corr_zero`, `corr_n`
- `corr_zero = 1` if CI does NOT contain zero (significant), `0` if it does or if r is NaN
- O(n^2) where n = number of indicators (22) = 484 pearsonr calls

**New method in aggregator.py:**

`_compute_correlation(indicators, reference_path=None)`:
- Reads `Label_Correlation` and `Order_Correlation` from `data/cria_data_reference.xlsx` Status sheet
- Relabels indicator columns (e.g., "Education" -> "Low Educational Attainment")
- Reorders columns by `Order_Correlation`
- Falls back to original names if reference file not found
- Uses `PathConfig().reference_file` for path resolution

Added to pipeline as Step 10, output dict keys `"corr"`, `"p"`, `"zero"`, `"n"`.

### Audit Fixes

Quality auditor identified 3 actionable findings, all resolved:

| ID | Severity | Issue | Fix |
|----|----------|-------|-----|
| F1 | must-fix | `_compute_lowest_indicators` crashed on empty DataFrame | Added guard: `if len(df_scores) == 0: return pd.DataFrame()` |
| F2 | should-fix | `corr_zero` reported `1` (significant) when r=NaN | Added `if np.isnan(r): corr_zero = 0` |
| F3 | should-fix | Hardcoded relative path for reference Excel | Changed to `PathConfig().reference_file` |

### Tests

| File | New Tests | Purpose |
|------|-----------|---------|
| `tests/unit/test_binning.py` | 6 new, 2 updated | Pop change/pop_p ascending for k=5 and k=7, parametrized regression |
| `tests/unit/test_transformations.py` | 17 new | pearsonr_ci (8): perfect/negative/no correlation, NaN, edge cases. calc_full_corr_matrix (9): symmetry, diagonal, significance, NaN, scipy match |
| `tests/unit/test_aggregator.py` | 14 new | lowest_ind (7): columns, correct ID, fewer indicators, single indicator. correlation (7): keys, square, diagonal, relabeling, fallback |
| `tests/smoke/test_pipeline_smoke.py` | 0 new, 1 updated | Updated expected output keys |
| `tests/unit/test_tribal_output.py` | 0 new, 1 updated | Updated FULL_EXPECTED_KEYS |

**Test suite**: 504 -> 541 tests (+37)

### Output Regeneration

| Geography | File | Rows | Indicators | New Tabs | Pop Change Bins |
|-----------|------|------|------------|----------|-----------------|
| County | `cria_results_county_2024.xlsx` | 3,284 | 22 | lowest_ind, corr, p, zero, n | Ascending (1=least, 5=most) |
| Tract | `cria_results_tract_2024.xlsx` | 85,382 | 22 | lowest_ind, corr, p, zero, n | Ascending (1=least, 7=most) |
| Tribal | `cria_results_tribal_2024.xlsx` | 704 | 17 | None (binning-only) | N/A |

All Excel files now have 16 tabs (was 11): ref, years, indicators, pos, scores, scores_percentiles, lowest_ind, agg, bin_labels, bin_meta, agg_labels, agg_meta, corr, p, zero, n.

## Agent Team Execution

### Team: rapt-features

| Agent | Type | Tasks | Result |
|-------|------|-------|--------|
| team-lead | (self) | Implemented all 3 features, applied audit fixes | 3 methods + 2 functions, 159 lines in aggregator |
| tester | statistical-tester | Wrote tests for all 3 features | 37 tests, all passing |
| auditor | quality-auditor | Adversarial review | PASS WITH CONCERNS (3 findings, all resolved) |

## Deprecated Code References

| New Code | Deprecated Source | Notes |
|----------|-------------------|-------|
| `_compute_lowest_indicators()` | `cria_create_aggregate_indicator.py:140-167` | Faithful reproduction, added edge case guards |
| `pearsonr_ci()` | `cria_functions.py:542-571` | Bug fix: valid pair count instead of len(x) |
| `calc_full_corr_matrix()` | `cria_functions.py:574-627` | Added NaN r -> significance=0 guard |
| `_compute_correlation()` | `cria_create_aggregate_indicator.py:199-206` | Uses PathConfig, try/except for reference file |
| Pop change `reverse: False` | `cria_functions.py:268-289` (was `[::-1]`) | **Intentional change** from deprecated behavior |

## Next Steps

- Distribute regenerated 2024 output to team
- Draft high-level write-up of code changes since Jan 30 (RAPT question #3)
- Investigate 3 county Inactive Voter values showing old imputed value (rounding artifact?)
- Consider suppressing arctanh/se RuntimeWarnings with np.errstate context manager
