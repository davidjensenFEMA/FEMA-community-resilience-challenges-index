# Spreadsheet Enhancements Plan

**Date**: 2026-02-17
**Request**: Restore "ref" tab and show binning methodology on bin_meta tab

---

## Background

The old output spreadsheets (e.g., `cria_indicators_tract_2021.xlsx`) had:
1. A **ref** tab — full indicator reference table with settings used for the run
2. A **years** tab — data source year configuration
3. A **bin_meta** tab showing which binning method was selected per indicator, with scores and cutoffs

The current output (e.g., `cria_results_county_2024.xlsx`) has 9 sheets but is missing ref/years, and bin_meta only shows basic stats (bin, count, min, max, mean, median) — no method selection info.

## What's Missing

### 1. "ref" tab
The old ref tab had 22 rows (one per indicator) with columns: Order_Paper, Indicator, Label, Source, year, numerator, denominator, Function, Augment, Units, NAICS, rate, notes, etc.

**Current data sources**: `calculator.reference` (loaded from `data/cria_data_reference.xlsx` "Status" sheet) and `calculator.years` (from "Years" sheet merged with `settings.years_dict`). Both are available at runtime but never written to output.

### 2. Binning method on bin_meta
The old bin_meta showed per indicator:
- Row "choose": "selected"/"manual" and the method name (e.g., "Jenks Caspall")
- Rows 0-8: Each candidate method with its combined ADCM+TSS score (or "failed")
- Rows "group 1-5": Bin cutoffs and counts

The current `BinningEngine._auto_select_method()` computes the same ADCM+TSS scoring but **discards** the results — only bin assignments are returned.

---

## Implementation Steps

### Phase 1: Capture Binning Method Metadata

- [x] **Step 1**: Add `self._last_fit_results: Dict[str, Dict] = {}` to `BinningEngine.__init__()`
- [x] **Step 2**: Modify `_auto_select_method()` to store fit results (selected method, score, all method scores) into `self._last_fit_results[series.name]`
- [x] **Step 3**: Clear `_last_fit_results` at start of `bin_dataframe()` to prevent stale state
- [x] **Step 4**: Record method info in `bin_series()` for non-auto strategies too (single method = "direct", manual = "manual")
- [x] **Step 5**: Add `get_selection_metadata()` method returning stored method selection info
- [x] **Step 6**: Enhance `get_metadata()` to include `selected_method` and `selected_score` columns

### Phase 2: Flow Metadata Through Aggregator

- [x] **Step 7**: Update `_bin_indicators()` to pass method metadata into bin_meta DataFrames
- [x] **Step 8**: Update `_bin_aggregate()` similarly for agg_meta

### Phase 3: Add ref/years Tabs to Excel Output

- [x] **Step 9**: Add `reference` and `years` parameters to `AggregateIndicator.save_to_excel()`
- [x] **Step 10**: Build ref DataFrame with year enrichment (map each indicator's Source to its year from the years dict)
- [x] **Step 11**: Control sheet ordering so ref and years appear first
- [x] **Step 12**: Update `run_full_pipeline.py` to pass `calculator.reference` and `calculator.years` to `save_to_excel()`

### Phase 4: Tests

- [x] **Step 13**: Add unit tests for binning method metadata storage in `test_binning.py`
- [x] **Step 14**: Update aggregator Excel export tests to verify ref/years tabs and method metadata columns
- [x] **Step 15**: Run full test suite, verify no regressions (147 tests, 0 failures)

### Phase 5: Validation

- [x] **Step 16**: Run a test pipeline export — validated ref, years, bin_meta, agg_meta tabs with method diversity

---

## Files to Modify

| File | Change |
|------|--------|
| `src/core/binning.py` | Add `_last_fit_results`, modify `_auto_select_method()`, add `get_selection_metadata()`, enhance `get_metadata()` |
| `src/core/aggregator.py` | Update `_bin_indicators()`, `_bin_aggregate()`, and `save_to_excel()` |
| `scripts/run_full_pipeline.py` | Pass `calculator.reference` and `calculator.years` to `save_to_excel()` |
| `tests/unit/test_binning.py` | New tests for method metadata |
| `tests/unit/test_aggregator.py` | Updated Excel export tests |

---

## Year Enrichment Mapping (for ref tab)

The ref tab needs a "year" column mapping each indicator's Source to the year used:
```python
source_year_map = {
    "ACS": years["acs"],
    "CBP": years["cbp"],
    "EAVS": None,    # Static data
    "ARDA": None,     # Static data
    "POP": years["pop"],
}
```

## Enhanced bin_meta Format

Keep the current clean tabular format but add two columns:

| bin | count | min | max | mean | median | indicator | selected_method | selected_score |
|-----|-------|-----|-----|------|--------|-----------|-----------------|----------------|
| 1   | 645   | 0.0 | 12.3| 6.1  | 5.9    | Education | FisherJenks     | -0.628         |

This is more machine-readable than the old wide format while preserving the key information the user needs (which method was chosen and how well it scored).

---

## Risks and Considerations

1. **BinningEngine state** — `_last_fit_results` makes it stateful. Clear at start of `bin_dataframe()` to prevent stale data.
2. **Manual binning** — Some indicators use manual bins. Record method as "manual" with no score.
3. **Non-auto strategy** — When a specific method is requested, record it as a direct selection (no comparison scores).
4. **Sheet ordering** — Use explicit ordered list of sheet names rather than dict iteration order.
5. **Backward compatibility** — New columns in bin_meta. Low risk since output is for human consumption in Excel.
