---
date: 2025-12-05
tags: [#bugfix, #binning, #performance]
status: complete
---

# Bug Fix: JenksCaspall Infinite Loop on Degenerate Data

**Date**: 2025-12-05
**Bug ID**: #8
**Status**: FIXED
**Severity**: Critical (pipeline hang)

---

## Summary

The CRIA pipeline was hanging indefinitely during the binning step (Step 3: Creating Aggregate Scores). The root cause was the `JenksCaspall` algorithm from MapClassify entering an infinite loop when processing data with many duplicate values.

## Symptoms

- Pipeline hangs at "Step 3: Creating Aggregate Scores"
- Process uses 100% CPU indefinitely (observed 3+ hours)
- Warning messages appear before hang:
  ```
  UserWarning: Not enough unique values in array to form 5 classes. Setting k to 4.
  RuntimeWarning: Mean of empty slice.
  RuntimeWarning: invalid value encountered in scalar divide
  ```
- Numba JIT was installed and working correctly (not the cause)

## Root Cause Analysis

### Investigation

1. **Initial hypothesis**: Numba JIT not working → **RULED OUT** (Numba was functional)

2. **Isolated the problem**: Tested each binning method individually on Civil Org indicator data:
   ```
   Quantiles:      0.004s ✓
   EqualInterval:  0.003s ✓
   FisherJenks:    0.072s ✓
   JenksCaspall:   HANGS INDEFINITELY ✗
   MaximumBreaks:  0.004s ✓
   ```

3. **Root cause**: The Civil Org indicator has ~50% zero values. JenksCaspall's iterative algorithm fails to converge on this degenerate distribution, entering an infinite loop.

### Affected Data

The Civil Org indicator distribution:
- Total values: 3,283 counties
- 50% of values are 0.0 (median = 0.0)
- This creates a degenerate case for JenksCaspall's class optimization

## Fix Applied

**File**: `src/core/binning.py` (lines 299-306)

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

### Why This Fix is Safe

1. **FisherJenks** provides equivalent functionality to JenksCaspall (both are natural breaks algorithms)
2. **FisherJenks** handles degenerate data gracefully (tested: 0.072s on Civil Org)
3. Users can still explicitly request `jenks_caspall` if needed via the `exceptions` parameter
4. All 22 indicators now calculate correctly

## Performance Impact

| Metric | Before | After |
|--------|--------|-------|
| Pipeline runtime | Hangs indefinitely | ~34 seconds |
| Binning step | Never completes | ~5 seconds |
| CPU usage | 100% (stuck) | Normal |

## Validation

### Calibration Results (2022 vs 2021)

| Indicator | Correlation | Status |
|-----------|-------------|--------|
| Religion | 1.0000 | PERFECT |
| Mobile Homes | 0.9908 | EXCELLENT |
| Owner Occupied | 0.9867 | GOOD |
| Median Income | 0.9856 | GOOD |
| ... | ... | ... |
| **Average** | **0.9458** | **VALIDATED** |

- **22/22 indicators** calculating correctly
- **21/22 indicators** have correlation > 0.90
- Only outlier: Inactive Voter (0.6272) - expected due to different EAVS data years

### Test Results

```
135 passed in 10.38s
```

All existing tests continue to pass.

## Note on Inactive Voter Correlation

The Inactive Voter indicator shows a correlation of 0.6272 between 2022 and 2021 results. This is **expected behavior**, not a bug:

- **Raw A1c correlation** (old vs new): 0.9794 (strong)
- **Calculation accuracy**: 1.0000 (perfect match to A1c/A1a in both years)
- **Cause**: 2022 EAVS data shows ~23% more inactive voters than 2020/2018 data
- Both calculations are correct - they use different source data years as expected

## Files Changed

| File | Change |
|------|--------|
| `src/core/binning.py` | Removed jenks_caspall from auto-select methods |
| `docs/20251203_BUG_FIXES_SESSION.md` | Added Bug #8 documentation |
| `docs/20251205_JENKSCASPALL_BUG_FIX.md` | This document |

## Commit

```
1bfd9e8 Fix JenksCaspall infinite loop on degenerate data (Bug #8)
```

---

**Document Created**: 2025-12-05
**Author**: Claude Code / Development Team
