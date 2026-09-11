---
date: 2026-03-19
tags: [#binning, #fix, #county, #tract, #tribal]
status: complete
---

# Restore Manual Bin Boundaries from Deprecated Code

**Date**: 2026-03-19
**Branch**: `main`

---

## Summary

Restored the manual bin boundaries that were removed during the codebase modernization. The deprecated code (`cria_functions.py:fit_manual()`) used hardcoded `pd.cut()` boundaries for 7 specific columns, bypassing auto-select. These boundaries encode domain knowledge — asymmetric bins that produce bell-curve distributions and label reversals for resilience scoring.

### Problem

Year-over-year comparison revealed two binning differences:
1. **CRCI percentile** (`cria_p`): Changed from bell curve (10%-20%-40%-20%-10%) to flat equal intervals (20% each)
2. **Population Change** (`pop change`): Changed from bell curve with reversed labels to right-skewed distribution

Root cause: The current code removed the deprecated `manual_list` concept and ran all columns through auto-select, which chose statistically optimal but domain-inappropriate methods.

---

## Changes Made

### `src/core/binning.py` — Manual bin support

**`MANUAL_BINS` constant** — 6 column configurations from deprecated code:

| Column | Boundaries (5-bin) | Reversed | Level |
|--------|-------------------|----------|-------|
| `Median Income` | [25k, 50k, 75k, 100k] | No | Indicator |
| `agg` | [-0.75, -0.25, 0.25, 0.75] | Yes | Aggregate |
| `cri` | [0.1, 0.3, 0.7, 0.9] | No | Aggregate |
| `cria_p` | [0.1, 0.3, 0.7, 0.9] | No | Aggregate |
| `pop change` | [0.1, 0.25, 0.85, 1.5] | Yes | Aggregate |
| `pop_p` | [0.1, 0.3, 0.7, 0.9] | Yes | Aggregate |

All also have 7-bin configurations for tract geography.

**`_apply_manual_bins()` method** — Uses `pd.cut()` with `[-inf, ...boundaries..., +inf]`, handles label reversal, records `selection_type: "manual"` in metadata.

**`bin_series()` modification** — Checks `MANUAL_BINS` before auto-select. If series name and k match a config, manual bins are used. Otherwise falls through to existing auto-select logic.

### `tests/unit/test_binning.py` — 15 new tests

`TestManualBins` class covering:
- Bell curve distribution for `cria_p`
- Reversed labels for `pop change`, `agg`, `pop_p`
- Non-reversed for `cri`, `cria_p`, `Median Income`
- 7-bin tract support
- NaN preservation
- Fallthrough for unconfigured k values
- Parametrized coverage of all 6 manual columns

### `tests/unit/test_bin_labels_regression.py` — Test data fix

`_make_indicator_data()` now generates realistic Median Income values (normal distribution around $55k) instead of 0-1 range, so manual bins produce multiple bin assignments.

---

## Test Results

| Metric | Before | After |
|--------|--------|-------|
| Total tests | 438 | 455 |
| New tests | — | 15 (TestManualBins) |
| Failures | 0 | 0 |

---

## Next Steps

- Regenerate county, tract, and tribal 2024 output with manual bins
- Verify cria_p shows bell-curve distribution in output spreadsheets
- Verify pop change bins match deprecated behavior
