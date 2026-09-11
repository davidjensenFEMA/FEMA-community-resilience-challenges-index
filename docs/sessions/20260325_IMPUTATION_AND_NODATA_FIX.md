---
date: 2026-03-25
tags: [#indicators, #aggregation, #eavs, #bugfix, #county, #tract, #tribal]
status: complete
---

# Fix Indicator Imputation Display and No-Data Handling

**Date**: 2026-03-25
**Branch**: `main`
**Follows**: [20260324_UPSTREAM_DOCTRINE_SYNC.md](20260324_UPSTREAM_DOCTRINE_SYNC.md)

---

## Summary

Two related bugs were fixed in response to team feedback about the Inactive Voter indicator and missing data handling across all geographies. The indicators tab was showing imputed national averages where data was missing (should be blank/gray on map), and EAVS survey code `-88` ("does not apply") was being converted to `0` instead of NaN, creating false indicator values for non-reporting states.

Additionally, all five indicator calculation functions were fixed to return NaN (not `0`) when the denominator is zero — a zero denominator means the indicator is undefined, not zero.

The upstream doctrine sync from the utils repo was also completed in this session (proposer agent, wave terminology, skills framework).

## Problem Statement

The team reported:
> "We want to make sure [non-reporting states are] showing as gray on the map and not the imputed national average. [...] We need a tab in the spreadsheet that provides actual data (including blanks), and a separate tab that includes imputed data for the CRCI calculation."

### Root Causes

1. **Single DataFrame serving double duty**: `_clean_indicators(impute=True)` produced one DataFrame used for both the indicators tab (display) and the CRCI pipeline (calculation). Missing values were mean-imputed, so the indicators tab showed the national average (0.08583769 for Inactive Voter) instead of blank.

2. **EAVS -88 → false zero**: The EAVS survey uses `-88` for "does not apply" and `-99` for "data not available." The client code mapped `-88` to `0` (should be NaN). When both A1a and A1c were 0, `_divide_function` produced `0/0 → 0` via the denominator guard, creating a false Inactive Voter value of `0.0` for non-reporting jurisdictions.

3. **Zero-denominator → false zero**: All five indicator calculation functions (`_divide`, `_max`, `_mean`, `_divide_scalar`, `_reverse_divide`) had `result.loc[denominator == 0] = 0`. A zero denominator (e.g., zero total population) means the rate is undefined — should be NaN, not zero.

## Changes Made

### Fix 1: Imputation Split (`src/core/aggregator.py`)

**Commit**: `046c595`

In `create_aggregate()`, added a second call to `_clean_indicators()` with `impute=False` to create a display copy:

```python
# Create display copy WITHOUT imputation (NaN stays NaN for gray-on-map)
if impute:
    df_display = self._clean_indicators(
        indicators, reference, geo_reference, impute=False
    )
else:
    df_display = df_clean
```

- `results["indicators"]` now uses `df_display` (true values, NaN preserved)
- The CRCI pipeline continues using `df_clean` (mean-imputed) for z-scores, aggregation, and binning
- Performance: ~74ms overhead at tract scale (85K rows) — negligible
- CT CBP and PR Limited English special cases apply to BOTH copies (handled inside `_clean_indicators()`)
- Tribal path unchanged (`impute=False` already used via `skip_aggregation=True`)

### Fix 2: EAVS -88 → NaN (`src/api/external_clients.py`)

**Commit**: `92e2672`

Changed line 110 in `EAVSClient.fetch_eavs_data()`:
```python
# Before:
eavs_issues = {-88: 0, -99: np.nan}

# After:
eavs_issues = {-88: np.nan, -99: np.nan}
```

Impact: 208 additional counties now correctly show NaN for Inactive Voter (previously showed false `0` from `-88` codes).

### Fix 3: Zero-Denominator → NaN (`src/core/indicators.py`)

**Commit**: `92e2672`

Changed all five calculation functions:
```python
# Before (in each function):
result.loc[denominator == 0] = 0

# After:
result.loc[denominator == 0] = np.nan
```

Functions changed: `_divide_function` (L179), `_max_function` (L212), `_mean_function` (L256), `_divide_scalar_function` (L285), `_reverse_divide_function` (L324).

### Tests

| File | Tests | Purpose |
|------|-------|---------|
| `tests/unit/test_imputation_split.py` | 19 new | NaN preservation on indicators tab, CRCI uses imputed, CT/PR special cases, tribal, all-NaN edge case, bin labels |
| `tests/unit/test_nodata_handling.py` | 30 new | EAVS -88/-99 → NaN, zero-denom → NaN for all 5 functions, guard tests (valid data not broken), end-to-end aggregator integration |
| `tests/unit/test_indicators.py` | 5 updated | `test_zero_denominator_returns_zero` → `test_zero_denominator_returns_nan` |
| `tests/unit/test_external_clients.py` | 1 updated | EAVS -88 assertion: `== 0` → `pd.isna()` |
| `tests/unit/test_tribal_output.py` | 1 updated | Strengthened: checks BOTH display (NaN) and scores (no NaN) |

**Test suite**: 455 → 504 tests (+49)

### Upstream Doctrine Sync

**Commit**: `399f105`

Synced `.claude/` infrastructure from the upstream `utils` repo:
- Added `proposer` agent (CRIA-adapted, sonnet model, docs/-only write)
- Updated `task.md` with wave terminology, TCS universal language, military origin
- Added `session-start.md` Step 5 for upstream doctrine propagation
- Copied 5 Level 0 skills to `.claude/skills/`
- Created `bug-fix` and `code-review` team templates
- Updated `indicator-development` team with proposer workflow
- Updated `CLAUDE.md`, `agents/README.md`, `teams/README.md`
- Quality audit: 7 findings identified and resolved

### Output Regeneration

All three geographies regenerated with both fixes:

| Geography | Output File | Rows | Indicators | Inactive Voter NaN | CRCI Rows |
|-----------|-------------|------|------------|-------------------|-----------|
| County | `cria_results_county_2024.xlsx` | 3,284 | 22 | 677 (was 0) | 3,284 |
| Tract | `cria_results_tract_2024.xlsx` | 85,382 | 22 | 11,666 | 85,382 |
| Tribal | `cria_results_tribal_2024.xlsx` | 704 | 17 | N/A (dropped) | N/A |

## Agent Team Execution

### Doctrine Sync Team (`doctrine-sync`)

| Agent | Tasks | Wave |
|-------|-------|------|
| wave-1 | session-start.md, task.md, proposer agent | 1 |
| wave-2 | Skills framework (5 files) | 1 |
| wave-3a | Team templates (3 files) | 3 |
| wave-3b | Agents README | 3 |
| auditor | Full audit, 7 findings | Post |

### Imputation Fix Team (`inactive-voter-fix`)

| Agent | Role | Result |
|-------|------|--------|
| proposer (sonnet) | Evaluated Option A vs B vs C | Option A confirmed optimal |
| engineer (data-engineer) | Implemented imputation split | 14-line diff, all tests pass |
| tester (statistical-tester) | Wrote imputation split tests | 19 tests, 1 existing test updated |
| auditor (quality-auditor) | Adversarial review | PASS, 0 must-fix |

### No-Data Fix Team (`nodata-fix`)

| Agent | Role | Result |
|-------|------|--------|
| proposer (cria-analyst) | Audited all 5 data sources | Table of all no-data codes and handling |
| engineer (data-engineer) | Fixed EAVS -88, zero-denom | 2 files, 6 existing tests updated |
| tester (statistical-tester) | Wrote no-data handling tests | 30 tests across 6 classes |
| auditor (quality-auditor) | Adversarial review | PASS, 0 must-fix |

## Data Source No-Data Audit Results

| Source | No-Data Code | Previous Handling | Fixed? |
|--------|-------------|-------------------|--------|
| EAVS | `-88` (does not apply) | `0` (false zero) | **Yes → NaN** |
| EAVS | `-99` (data not available) | `NaN` (correct) | No change needed |
| Census ACS | `-666666666` (missing sentinel) | `NaN` (correct) | No change needed |
| CBP | Suppressed cells | `0` via `fillna(0)` | No change — CBP fills numerators only, denominators from ACS |
| ARDA | Blank/missing cells | Pandas default NaN | No change needed |
| POP | No special codes | Numeric values used directly | No change needed |

## Next Steps

- Distribute regenerated 2024 output to team
- Draft response to team explaining the fixes
- Investigate 3 remaining county Inactive Voter values showing old imputed value (rounding artifact?)
- Consider adding Level 1 CRIA-specific skills (census-api-integration, indicator-calculation, binning-methodology)
- Test proposer agent on a real task to validate the workflow
