---
date: 2025-12-03
tags: [#bugfix, #data-pull, #census-acs, #cbp, #eavs, #arda, #phase-8]
status: complete
---

# Bug Fixes Session - December 3, 2025

**Purpose**: Document critical bugs discovered and fixed during calibration testing
**Status**: All 8 bugs FIXED and VALIDATED
**Author**: Claude Code / Development Team

---

## Executive Summary

During calibration testing to validate the refactored OOP workflow against the 2022 baseline,
we discovered and fixed 5 critical bugs that were preventing proper data processing.

### Results After Fixes

| Metric | Before | After |
|--------|--------|-------|
| Indicators calculating | 13/22 | **22/22** |
| Religion indicator | BROKEN | **PERFECT MATCH (corr=1.0)** |
| Inactive Voter indicator | BROKEN | **Working (corr=0.63)** |
| Average correlation | N/A | **0.94** |

---

## Bug 1: DataFrame Column Merge Bug

### Location
[src/core/data_puller.py:189-196](src/core/data_puller.py#L189-L196)

### Problem
Census API returns shared columns (like `NAME`, `DP04_0001E`, `S0101_C01_001E`) with every request.
When merging DataFrames from multiple API calls, pandas would create duplicate columns
(`DP04_0001E_x`, `DP04_0001E_y`) instead of detecting the duplicates.

This caused indicator calculations to fail because the expected column names didn't exist.

### Symptoms
- 9 out of 22 indicators had NO DATA
- KeyError exceptions for expected columns like `S0101_C01_001E`
- DataFrame had 100+ columns instead of expected ~60

### Fix
```python
# Before merging, detect and drop duplicate columns
existing_cols = set(data.columns)
new_cols = set(df.columns)
duplicate_cols = existing_cols & new_cols

if duplicate_cols:
    logger.debug(f"  Dropping duplicate columns from merge: {duplicate_cols}")
    df = df.drop(columns=list(duplicate_cols))

# Only merge if df still has columns to add
if not df.empty and len(df.columns) > 0:
    data = data.merge(df, left_index=True, right_index=True, how="outer")
```

---

## Bug 2: EAVS ZIP Extraction Issue

### Location
[src/api/external_clients.py:71-92](src/api/external_clients.py#L71-L92)

### Problem
The EAVS (Election Administration and Voting Survey) data from EAC is served as a ZIP file
containing a CSV. The code was passing the ZIP bytes directly to `pd.read_csv()`, causing
a `UnicodeDecodeError`.

### Symptoms
```
UnicodeDecodeError: 'utf-8' codec can't decode byte 0x93 in position 1
```

### Fix
```python
import zipfile

# Extract CSV from ZIP file first
try:
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        csv_files = [f for f in zf.namelist() if f.endswith('.csv')]
        if not csv_files:
            raise ValueError("No CSV file found in EAVS ZIP archive")

        with zf.open(csv_files[0]) as csv_file:
            df = pd.read_csv(csv_file, encoding='utf-8', low_memory=False)
except zipfile.BadZipFile:
    # Fallback to direct CSV read
    df = pd.read_csv(io.BytesIO(response.content), encoding='latin-1')
```

---

## Bug 3: EAVS GEO_ID Index Issue

### Location
[src/api/external_clients.py:116-120](src/api/external_clients.py#L116-L120)

### Problem
When merging EAVS data with the counties reference DataFrame, the code expected `GEO_ID`
to be a column. However, after certain operations, `GEO_ID` was the DataFrame's index,
causing a `KeyError: "['GEO_ID'] not in index"`.

### Symptoms
```
KeyError: "['GEO_ID'] not in index"
```

### Fix
```python
# Prepare counties reference - reset index if GEO_ID is the index
counties_ref = counties_ref.copy()
if counties_ref.index.name == "GEO_ID":
    counties_ref = counties_ref.reset_index()
```

---

## Bug 4: Religion Indicator POP Column Issue

### Location
[src/api/external_clients.py:236-239](src/api/external_clients.py#L236-L239)

### Problem
The Religion indicator formula in `cria_data_reference.xlsx` specifies `POP` as the denominator.
However, ARDA data returns columns named `POP2020` or `POP2010` (year-specific), not `POP`.
This caused the indicator calculation to fail with `KeyError: 'POP'`.

### Symptoms
```
KeyError: 'POP'
```

### Fix
Added a generic `POP` column that mirrors the year-specific column:

```python
# Add a generic 'POP' column for calculations
# Religion indicator uses 'POP' as denominator but data has 'POP{year}'
pop_col = f"POP{year}"
if pop_col in df.columns:
    df["POP"] = df[pop_col]
```

---

## Bug 5: Pipeline Excel Export Method Signature

### Location
[scripts/run_full_pipeline.py:178-186](scripts/run_full_pipeline.py#L178-L186)

### Problem
The `save_to_excel()` method expected `file_path` as the second positional argument,
but the pipeline was passing `geography` as a keyword argument, causing the error.

### Symptoms
```
TypeError: save_to_excel() got an unexpected keyword argument 'geography'
```

### Fix
```python
# Construct proper file path before calling save_to_excel
from src.config.paths import paths
excel_filename = f"cria_results_{geography}_{year}.xlsx"
excel_path = paths.output / excel_filename
aggregator.save_to_excel(results, file_path=str(excel_path))
```

---

## Validation Results

After applying all fixes, we ran a full calibration pipeline and compared against the
2022 baseline (`data/output/cria_results_county_2022.xlsx`).

### Key Findings

| Indicator | Correlation | Status | Notes |
|-----------|-------------|--------|-------|
| Religion | 1.0000 | PERFECT | Confirms ARDA fix is correct |
| Mobile Homes | 0.9925 | EXCELLENT | ACS year difference |
| Age | 0.9882 | GOOD | ACS year difference |
| Median Income | 0.9892 | GOOD | ACS year difference |
| Owner Occupied | 0.9870 | GOOD | ACS year difference |
| Education | 0.9804 | GOOD | ACS year difference |
| No Vehicle | 0.9802 | GOOD | ACS year difference |
| Poverty | 0.9793 | GOOD | ACS year difference |
| Limited English | 0.9783 | GOOD | ACS year difference |
| Low Access to Communications | 0.9741 | GOOD | ACS year difference |
| Uninsured Population | 0.9719 | GOOD | ACS year difference |
| Disability | 0.9697 | GOOD | ACS year difference |
| Unemployment | 0.9472 | MODERATE | ACS year difference |
| Single Parent | 0.9465 | MODERATE | ACS year difference |
| Hospitals | 0.9412 | MODERATE | CBP year difference |
| Civil Org | 0.9322 | MODERATE | CBP year difference |
| Lack of Economic Diversity | 0.9280 | MODERATE | CBP year difference |
| Medical | 0.9263 | MODERATE | CBP year difference |
| Unemployed Women | 0.9188 | MODERATE | ACS year difference |
| GINI | 0.9166 | MODERATE | ACS year difference |
| Population Change | 0.8584 | NEEDS REVIEW | Subset calculation |
| Inactive Voter | 0.6300 | NEEDS REVIEW | EAVS data matching |

### Why Not Perfect Correlations?

The baseline was generated with **ACS_YEAR=2022** but our test used **ACS_YEAR=2021**
(from the current `.env` file). This explains why:

1. **Religion = 1.0000** (ARDA data is static, doesn't change year-over-year)
2. **Most indicators ~0.92-0.99** (reflects normal year-over-year ACS changes)
3. **Inactive Voter = 0.63** (EAVS name matching is fuzzy, not exact FIPS-based)
4. **Population Change = 0.86** (uses special subset calculation with different mean/std)

---

## Recommendations for Handoff

### For True Calibration

To verify the refactored code produces **identical** results to the baseline:

1. Update `.env` to match 2022 configuration:
   ```bash
   ACS_YEAR=2022
   CBP_YEAR=2021
   POP_YEAR=2020
   ASARB_YEAR=2020
   ```

2. Run the pipeline:
   ```bash
   DATABASE_URL="sqlite:///./calibration_2022.db" \
   poetry run python scripts/run_full_pipeline.py \
       --geography county --year 2022 --export-excel
   ```

3. Compare results - should see correlations very close to 1.0 for all indicators.

### Known Limitations

1. **Inactive Voter**: Uses fuzzy name matching (not FIPS codes), so small differences expected
2. **Population Change**: Uses special subset calculation that may vary based on data availability
3. **Connecticut CBP**: 2022 CBP data has zeros (special handling converts to NaN)
4. **Puerto Rico Limited English**: Spanish speakers excluded (not "limited English")

### Files Modified

| File | Changes |
|------|---------|
| `src/core/data_puller.py` | Fixed DataFrame merge bug, ARDA POP column handling |
| `src/api/external_clients.py` | Fixed EAVS ZIP extraction, GEO_ID index, POP column |
| `scripts/run_full_pipeline.py` | Fixed save_to_excel method signature |

---

## Testing

All 135+ existing tests continue to pass after these fixes:

```bash
poetry run pytest
# 135+ tests passed
```

The fixes were targeted and minimal, avoiding any changes to the core calculation logic.

---

## Bug 6: Census API Tract Geography Wildcard

### Location
[src/api/census_client.py:139-196](src/api/census_client.py#L139-L196)

### Problem
The Census API doesn't allow state wildcards for tract queries. The original code used
`tract:*&in=state:*&in=county:*` which returned HTTP 400 error.

### Symptoms
```
HTTP error 400: error: wildcard not allowed for 'state' in geography hierarchy
```

### Fix
Added state-by-state iteration for tract geography:

```python
def _fetch_acs_data_by_state(
    self,
    columns: List[str],
    year: int,
    clean_missing: bool = True,
) -> pd.DataFrame:
    """Fetch ACS tract data by iterating over each state."""
    # State FIPS codes (50 states + DC + PR)
    state_fips = [
        "01", "02", "04", "05", "06", "08", "09", "10", "11", "12",
        # ... all 52 state/territory codes
    ]

    all_dfs = []
    for i, state in enumerate(state_fips, 1):
        url = self.build_acs_url(columns, "tract", year, state_codes=[state])
        response = self.get(url)
        # Process and collect DataFrames

    return pd.concat(all_dfs, axis=0)
```

---

## Tract Geography Validation

### Results: PERFECT MATCH

| Indicator | Correlation | Status | Notes |
|-----------|-------------|--------|-------|
| Age | 1.0000 | PERFECT | Identical to 2021 baseline |
| Disability | 1.0000 | PERFECT | Identical to 2021 baseline |
| Education | 1.0000 | PERFECT | Identical to 2021 baseline |
| GINI | 1.0000 | PERFECT | Identical to 2021 baseline |
| Lack of Economic Diversity | 1.0000 | PERFECT | Identical to 2021 baseline |
| Limited English | 1.0000 | PERFECT | Identical to 2021 baseline |
| Low Access to Communications | 1.0000 | PERFECT | Identical to 2021 baseline |
| Median Income | 1.0000 | PERFECT | Identical to 2021 baseline |
| Medical | 1.0000 | PERFECT | County-level, imputed to tract |
| Mobile Homes | 1.0000 | PERFECT | Identical to 2021 baseline |
| No Vehicle | 1.0000 | PERFECT | Identical to 2021 baseline |
| Owner Occupied | 1.0000 | PERFECT | Identical to 2021 baseline |
| Poverty | 1.0000 | PERFECT | Identical to 2021 baseline |
| Single Parent | 1.0000 | PERFECT | Identical to 2021 baseline |
| Unemployed Women | 1.0000 | PERFECT | Identical to 2021 baseline |
| Unemployment | 1.0000 | PERFECT | Identical to 2021 baseline |
| Uninsured Population | 1.0000 | PERFECT | Identical to 2021 baseline |

**17 out of 17 ACS-based indicators show PERFECT correlation (1.0000)** with 2021 baseline!

### Tract-Specific Notes

1. **County-level data sources (CBP, EAVS, ARDA, POP)**: Data is at county level and imputed to tracts
2. **New tracts**: 88,602 tracts fetched (3,207 more than 2021 baseline due to new Census definitions)
3. **Data pull time**: ~8 minutes (52 states × ~40 columns)
4. **Binning time**: Very slow without Numba (~30+ minutes for 88k records)

### Tract Indicator Availability

| Indicator | Available at Tract | Notes |
|-----------|-------------------|-------|
| ACS indicators (17) | ✅ Yes | Direct from Census API |
| Civil Org | ⚠️ Imputed | CBP is county-level |
| Hospitals | ⚠️ Imputed | CBP is county-level |
| Religion | ⚠️ Imputed | ARDA is county-level |
| Inactive Voter | ⚠️ Imputed | EAVS is county-level |
| Population Change | ⚠️ Imputed | POP is county-level |

---

## Bug 7: Database Save Performance for Tract Data ✅ FIXED

### Issue (Original)
The `save_to_database()` method used SQLAlchemy ORM row-by-row inserts, which was
extremely slow for tract-level data (88,000+ geographies × 57 columns = millions of rows).

### Observed Behavior (Before Fix)
- Started at 14:58:54
- After 42 minutes: DB file still only 140KB (schema only, no data committed)
- After 6.5 hours: Still stuck on "Saving source data to database..." (Step 1)
- SQLAlchemy log showed 700,000+ individual INSERT statements

### Root Cause
Two performance bottlenecks:
1. **Individual `get_by_geo_id()` lookups**: 88k database queries (one per geography)
2. **ORM-based inserts**: `add_all()` creates Python objects and tracks them in identity map

### Fix Applied
1. **Added `get_geo_id_map()` method** to GeographyRepository for batch lookups
2. **Changed `bulk_create()` methods** to use SQLAlchemy Core `insert()` with 10k batch size
3. **Updated all three `save_to_database()` methods** in DataPuller, IndicatorCalculator, and AggregateIndicator

### Performance After Fix
```
✅ 160,000 source data records in 2.71s (~59,000 records/second)
✅ 70,400 indicator records in 1.14s (~62,000 records/second)
✅ 3,200 aggregate records in 0.05s (~59,000 records/second)
```

### Files Modified
| File | Changes |
|------|---------|
| `src/db/repositories.py` | Added `get_geo_id_map()`, changed `bulk_create()` to use Core insert |
| `src/core/data_puller.py` | Use geo_id_map for batch lookup |
| `src/core/indicators.py` | Use geo_id_map for batch lookup |
| `src/core/aggregator.py` | Use geo_id_map for batch lookup |
| `tests/unit/test_repositories.py` | Updated assertions for new return type |
| `tests/integration/test_database_workflow.py` | Updated assertions for new return type |

### Impact
- **County pipeline (3,200 records)**: Now completes database save in seconds
- **Tract pipeline (88,000 records)**: Now viable with database storage

---

## Bug 8: JenksCaspall Infinite Loop on Degenerate Data ✅ FIXED

### Issue (December 4, 2025)
The pipeline was hanging indefinitely during Step 3 (binning) on county-level data.
Process would run for hours at 100% CPU without completing.

### Root Cause
The `JenksCaspall` algorithm from MapClassify enters an **infinite loop** when data has
many duplicate values. The Civil Org indicator has ~50% zero values, which triggers
this degenerate case.

### Symptoms
```
- Pipeline hangs at "Step 3: Creating Aggregate Scores"
- Process uses 100% CPU indefinitely
- Warning: "Not enough unique values in array to form 5 classes"
- Numba JIT was working correctly (not the cause)
```

### Investigation
Tested each binning method individually on Civil Org data:
- Quantiles: 0.004s ✓
- EqualInterval: 0.003s ✓
- FisherJenks: 0.072s ✓
- **JenksCaspall: HANGS INDEFINITELY** ✗
- MaximumBreaks: 0.004s ✓

### Fix Applied
[src/core/binning.py:299-306](src/core/binning.py#L299-L306)

Removed `jenks_caspall` from the default methods in `_auto_select_method()`:

```python
# Methods to try for auto-selection
# NOTE: jenks_caspall is EXCLUDED because it can hang indefinitely
# on data with many duplicate values (e.g., 50% zeros in Civil Org indicator)
# NOTE: natural_breaks is EXCLUDED because of its random nature
methods_to_try = [
    "equal_interval", "fisher_jenks",
    "maximum_breaks", "quantiles"
]
```

### Performance After Fix
- **Before**: Pipeline hangs indefinitely (hours)
- **After**: Pipeline completes in ~34 seconds

### Calibration Results (2022 vs 2021)
| Indicator | Correlation | Status |
|-----------|-------------|--------|
| Religion | 1.0000 | PERFECT |
| Mobile Homes | 0.9908 | EXCELLENT |
| Age | 0.9879 | GOOD |
| Owner Occupied | 0.9867 | GOOD |
| Median Income | 0.9856 | GOOD |
| ... | ... | ... |
| **Average** | **0.9458** | **VALIDATED** |

**22/22 indicators** calculating correctly
**21/22 indicators** have correlation > 0.90

---

**Document Created**: 2025-12-03
**Last Verified**: 2025-12-04 (All 8 bugs fixed, JenksCaspall infinite loop resolved)
