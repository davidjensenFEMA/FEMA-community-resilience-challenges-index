---
date: 2026-03-05
tags: [#fix, #tribal, #binning, #aggregation]
status: complete
---

# Tribal Output: Remove Aggregation, Fix Binning, Fix GEO_ID Contamination

**Date**: 2026-03-05
**Branch**: `main`

---

## Summary

Redesigned the tribal pipeline output to match deprecated behavior and stakeholder requirements. Tribal areas should NOT have an aggregate CRCI score — they only need binned indicators for visualizations. Additionally fixed county GEO_ID contamination (D10) that was burying bin values under pages of NaN rows.

### Key Insight

The deprecated tribal pipeline (`deprecated/old_scripts/cria_create_indicators_tribal.py`) produced only `{ref, bin_meta, bin_labels, data, indicators}` — no aggregation, no CRCI, no z-scores. The modern pipeline incorrectly ran tribal through the full aggregation path, producing 11 tabs with aggregate scores that shouldn't exist for tribal geography.

Stakeholder quote: "Tribal shouldn't have an aggregate, and therefore, shouldn't have a CRCI. The bins were not showing for the indicators in the tribal sheet, and I use those for the visualizations."

---

## Changes Made

### `src/core/aggregator.py` — `skip_aggregation` parameter

**Added `skip_aggregation: bool = False` to `create_aggregate()`**

When `skip_aggregation=True`:
- Executes steps 1-3 only: clean (with `impute=False`), rescale, bin indicators
- Skips steps 4-8: reorient, z-scores, aggregate, bin-aggregate, percentiles
- Returns dict with only: `{"indicators", "bin_labels", "bin_meta"}`

The `impute=False` behavior matches the deprecated tribal script (`clean_series(impute=False)` at line 100 of `cria_create_indicators_tribal.py`). NaN values stay as NaN rather than being mean-imputed — the binning engine drops NaN before computing bins, so they don't affect bin boundaries.

**Added `impute: bool = True` parameter to `_clean_indicators()`**

Private method now accepts imputation control. Default `True` preserves county/tract behavior. `False` used automatically when `skip_aggregation=True`.

### `scripts/run_full_pipeline.py` — D10 filter + tribal pipeline changes

**D10: Tribal GEO_ID filter** (lines 457-472, new)

Same pattern as D9 (tract). Filters `indicators`, `source_data`, and `geo_reference` to `2500000US*` prefix only. Removes 3,215 county-format GEO_IDs introduced by DataPuller's outer merge.

Placed BEFORE D1b (non-ACS column drop) and D8 (zero-pop filter) so both operate on clean tribal-only data.

**`skip_aggregation=True` for tribal** (line 532)

Pipeline passes `skip_aggregation=(geography == "tribal")` to `create_aggregate()`.

**Source data tab** (lines 535-537)

For tribal, adds `results["data"] = source_data` to include raw source data in the Excel output, matching deprecated behavior.

**Guard clauses** (lines 539-564)

- D8b reindex: Only reindexes `bin_labels` (no `agg_labels` for tribal)
- D6 vote nullify: Guard `"bin_labels" in results`
- Aggregate logging: `results.get("agg")` instead of `results["agg"]` (no KeyError)
- DB save: Only saves aggregates if `"agg" in results`

### `tests/unit/test_tribal_output.py` — 28 new tests

| Class | Tests | Coverage |
|-------|-------|----------|
| `TestSkipAggregationBehavior` | 6 | Returns only binning keys; excludes agg keys; impute=False verified |
| `TestTribalGeoIdFiltering` | 5 | D10 filter keeps only `2500000US*`; consistent across DataFrames |
| `TestTribalBinLabelsStructure` | 6 | Correct columns, bin range 1-5, bin_meta structure |
| `TestRegressionGuards` | 11 | County still has agg; parametrized GEO_ID prefix check; guard clauses |

### `docs/plans/CONOP_tribal_output_fix.md` — Full CONOP

Task-Condition-Standard format with 6 phases: Pre-fix audit, Code review, Implement, Test, Regenerate, Post-fix audit. Documents deprecated vs current behavior, design decisions, and all stakeholder decisions.

---

## CONOP Execution Summary

### Phase 1+2: Pre-Fix Audit + Code Review

Executed via 4 parallel exploration agents:
- **Current tribal output**: 11 tabs, 3,919 rows in bin_labels (704 tribal + 3,215 county), agg/agg_labels tabs that shouldn't exist
- **Deprecated tribal pipeline**: Output dict `{ref, bin_meta, bin_labels, data, indicators}` — NO aggregation
- **Current workflow**: `create_aggregate()` runs all 8 steps for tribal (should skip 4-8)
- **County/tract comparison**: Confirmed aggregation is correct for county/tract, incorrect for tribal

### Phase 3: Implementation

Code changes to `aggregator.py` and `run_full_pipeline.py` — 77 insertions, 13 deletions across 2 files.

### Phase 4: Tests

28 new tests in `test_tribal_output.py` — all passing.

### Phase 5: Regeneration

Full pipeline run (with data pull): 18 seconds.

Log confirmations:
- D10: `Tribal: filtered to 704 tribal GEO_IDs (removed 3215 county-format GEO_IDs)`
- D1b: `dropping 5 non-ACS indicator columns`
- D8: `filtered to 618 non-zero-population rows (excluded 86 zero-population GEOs)`
- Skip: `Skipping aggregation (binning-only mode) — 618 rows, 17 indicators`

### Phase 6: Post-Fix Audit

13/13 success criteria PASS:

| # | Criterion | Result |
|---|-----------|--------|
| 1 | No aggregation tabs | PASS |
| 2 | Correct tabs (ref, years, indicators, bin_labels, bin_meta, data) | PASS |
| 3 | Bins visible on first row (GEO_ID: `2500000US0010`) | PASS |
| 4 | No county GEO_IDs in any tab | PASS |
| 5 | All GEO_IDs are tribal (`2500000US*`) | PASS |
| 6 | 618 non-NaN rows in bins | PASS |
| 7 | 17 ACS-only indicators, 5 bins (values 1-5) | PASS |
| 8 | bin_labels: 34 cols (17 + 17 `_bins`) | PASS |
| 9 | bin_meta: 85 rows (17 x 5) | PASS |
| 10 | bin_labels: 704 total rows (618 data + 86 zero-pop NaN) | PASS |
| 11 | data tab: 704 rows x 58 cols, tribal-only | PASS |
| 12 | indicators: 618 rows | PASS |
| 13 | Non-ACS absent (Civil Org, Hospitals, Religion, Inactive Voter, Pop Change) | PASS |

---

## Stakeholder Decisions

Three open questions were presented and resolved:

1. **Imputation**: `impute=False` for tribal — match deprecated behavior. NaN stays NaN.
2. **Filename**: Keep `cria_results_tribal_2024.xlsx` (current naming convention).
3. **Source data tab**: Include `data` tab in results file — match deprecated behavior.

---

## Output Comparison: Before vs After

### Before (11 tabs)

| Tab | Rows | Issue |
|-----|------|-------|
| ref | 22 | OK |
| years | 6 | OK |
| indicators | 618 | OK |
| pos | 618 | **Should not exist** |
| scores | 618 | **Should not exist** |
| scores_percentiles | 618 | **Should not exist** |
| agg | 618 | **Should not exist** |
| bin_labels | 3,919 | **County contamination** |
| bin_meta | 85 | OK |
| agg_labels | 3,919 | **Should not exist + contamination** |
| agg_meta | 15 | **Should not exist** |

### After (6 tabs)

| Tab | Rows | Status |
|-----|------|--------|
| ref | 22 | OK |
| years | 6 | OK |
| indicators | 618 | OK — 17 ACS-only, tribal-only |
| bin_labels | 704 | OK — tribal-only, bins visible first row |
| bin_meta | 85 | OK — 17 indicators x 5 bins |
| data | 704 | OK — source data included |

---

## Test Results

| Metric | Before | After |
|--------|--------|-------|
| Total tests | 410 | 438 |
| New test file | — | `test_tribal_output.py` |
| New tests | — | 28 |
| Failures | 0 | 0 |
| Runtime | ~29s | ~38s |

---

## Regression Verification

- **County output**: Untouched (same modification time: Feb 24 16:08), still has all 11 tabs including agg/agg_labels
- **Tract output**: Untouched (same modification time: Mar 4 15:02), still has all 11 tabs including agg/agg_labels

---

## Next Steps

- Distribute validated tribal output to team
- Consider whether `cria_indicators_tribal_2024.xlsx` should also filter to tribal-only GEO_IDs (currently has 3,919 mixed rows)
