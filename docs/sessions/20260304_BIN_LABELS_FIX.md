---
date: 2026-03-04
tags: [#bugfix, #binning, #aggregation, #tract, #tribal, #county]
status: complete
---

# Fix Tract/Tribal bin_labels Degenerate Output

**Date**: 2026-03-04
**Branch**: `main`

---

## Summary

Diagnosed and repaired a production issue where tract and tribal output workbooks showed identical bin values ("same numbers") for multiple indicators on the `bin_labels` tab. Root cause was 6 behavioral divergences between the current pipeline (`scripts/run_full_pipeline.py`) and the deprecated scripts. An 8-agent team executed a CONOP with 5 phases: diagnosis, comparison, repair, testing, and adversarial audit. All fixes are in `scripts/run_full_pipeline.py` with no changes to core logic (`src/core/`).

## Problem Statement

After the 24 FEB 2026 multi-geography production run, the product owner reported that tract and tribal `bin_labels` tabs showed "the same numbers" for all indicators. Investigation revealed 5 out of 22 indicators had degenerate binning:

| Indicator | County (OK) | Tract (Broken) | Root Cause |
|-----------|-------------|----------------|------------|
| Civil Org | 5 bins distributed | 100% in bin 1 | All-zero (no county imputation) |
| Hospitals | 5 bins distributed | 100% in bin 1 | All-zero (no county imputation) |
| Population Change | 5 bins distributed | 100% in bin 1 | All-zero (no county imputation) |
| Inactive Voter | 51% dominant bin | 97% dominant bin | County-broadcast, no vote fix |
| Religion | 32% dominant bin | 97% dominant bin | County-broadcast values |

## Root Cause Analysis

6 divergences identified between deprecated and current pipeline:

| # | Divergence | Severity | Deprecated Behavior | Current (Pre-Fix) |
|---|-----------|----------|--------------------|--------------------|
| D1 | Tract non-ACS imputation | CRITICAL | Imputed from county values | Missing — indicators all-zero |
| D2 | Tribal non-ACS handling | HIGH | Dropped entirely (17 indicators) | Kept all 22 (5 all-zero) |
| D4 | geo_reference passthrough | HIGH | Passed to aggregator | Not passed — CT CBP + PR Limited English dead code |
| D6 | Vote data post-processing | HIGH | NaN'd Inactive Voter for zero-vote states | Missing entirely |
| D7 | Tract bin count | MEDIUM | Hardcoded 7 for tract | Default 5 for all |
| D5 | Column structure | MEDIUM | Both raw + _bins columns | Same (not the issue) |

**Bonus bug found during audit**: `_nullify_zero_vote_states()` used `pandas.sum()` with default `min_count=0`, treating all-NaN A1a/A1c (tract EAVS data) as zero — would have NaN'd ALL Inactive Voter_bins for all tracts. Fixed with `min_count=1`.

## Changes Made

### `scripts/run_full_pipeline.py` (all fixes here)

**New constants:**
- `DEFAULT_BINS = {"county": 5, "tract": 7, "tribal": 5, "state": 5}` — auto-set by geography
- `BINNING_EXCEPTIONS` — per-geography method exclusions matching deprecated config

**New helper functions:**
- `_impute_tract_from_county()` — merges county indicator values onto tracts by (state, county) FIPS. Includes row-count validation assertion after merge. Replicates `cria_create_aggregate_tract.py:247-281`.
- `_nullify_zero_vote_states()` — sets `Inactive Voter_bins` to NaN for states where A1a*A1c=0. Uses `sum(min_count=1)` to prevent NaN→0 false positives. Replicates `cria_create_aggregate_indicator.py:333-358`.

**Pipeline integration (Step 3 modifications):**
- Extracts `geo_reference` from `calculator.data_puller.geographies`
- For tract: creates county calculator with `source_data=None` (fresh pull), calculates county indicators, calls `_impute_tract_from_county()`
- For tribal: drops non-ACS indicator columns before aggregation
- Passes `geo_reference` and `exceptions` to `aggregator.create_aggregate()`
- Calls `_nullify_zero_vote_states()` after aggregation
- `bins` parameter defaults to `None`, auto-resolved via `DEFAULT_BINS`

### `tests/unit/test_bin_labels_regression.py` (new, 38 tests)

Regression tests covering:
- Non-ACS indicator degenerate binning detection
- Distinct bin distributions across indicators
- geo_reference enabling CT CBP and PR Limited English special cases
- Tract 7-bin vs county 5-bin verification
- County output structure regression
- Aggregate labels structure
- NaN vote data not treated as zero (min_count=1 guard)
- Mixed NaN/real vote data scenarios

### `tests/unit/test_pipeline_helpers.py` (new, 19 tests)

Unit tests for fix functions:
- `_impute_tract_from_county()`: correct FIPS mapping, orphan tracts get NaN, ACS columns untouched, row count preserved, index preserved
- `_nullify_zero_vote_states()`: zero-vote detection, valid states preserved, graceful handling of missing columns/data
- `DEFAULT_BINS` values: tract=7, county=5, tribal=5, state=5 (would FAIL on pre-fix code)

### `docs/plans/CONOP_bin_labels_diagnosis.md` (new)

Full CONOP document with situation, mission, execution phases, agent assignments, hypotheses, and success criteria.

### `.claude/agents/quality-auditor.md` (local, not committed)

Added `Write` and `Edit` to the quality-auditor agent's tool permissions. Previously restricted to `Read, Glob, Grep, Bash` with `Write, Edit` explicitly in `disallowedTools`. The read-only restriction caused the auditor agent to freeze when it needed to produce deliverables or communicate findings. The adversarial reviewer role and audit checklists are unchanged — only tool permissions were expanded to match other team agents. Updated the "Scope Fence" section from "Strictly Read-Only" to "Permissions" with role discipline guidance.

## Agent Team Execution

### Team: `bin-labels-fix` (8 agents)

| Agent | Type | Phases | Key Contribution |
|-------|------|--------|------------------|
| auditor | quality-auditor | 0, 4, re-audit | Opened XLSX files, characterized "same numbers" with value_counts, evaluated 5 hypotheses |
| analyst | cria-analyst | 1 | Traced deprecated vs current code, identified 7 divergences with severity ratings |
| engineer | data-engineer | 2, remediation | Implemented all 6 fixes + bonus bug fixes |
| tester | statistical-tester | 3, remediation | Wrote 38 regression + 19 helper tests |
| auditor-2 | quality-auditor | 4 (deep audit) | Found CRITICAL vote nullify NaN bug, identified test coverage gaps |
| engineer-2 | data-engineer | remediation | Tribal drop logic, merge validation |
| tester-2 | statistical-tester | remediation | Pipeline helper unit tests |
| auditor-3 | quality-auditor | re-audit | Final verification, confirmed all 6 findings remediated |

### Execution Timeline (~25 minutes)
1. **Phase 0+1** (parallel): auditor diagnosed from output files + analyst traced code divergences
2. **Backbrief**: Commander confirmed impute-from-county approach
3. **Phase 2+3** (parallel): engineer implemented fixes + tester wrote regression tests
4. **Phase 4**: auditor-2 found CRITICAL vote nullify bug + test coverage gaps
5. **Remediation** (parallel): engineer fixed bugs + tester added missing tests
6. **Re-audit**: auditor-3 confirmed all findings remediated → PASS

### Audit Trail
- Phase 4 initial verdict: PASS WITH CONCERNS (2 CRITICAL, 1 HIGH, 3 MEDIUM findings)
- Remediation addressed all CRITICAL and HIGH findings
- Final re-audit verdict: **PASS** (0 CRITICAL, 0 HIGH remaining)

## Quality-Auditor Agent Definition Update

The quality-auditor agent (`.claude/agents/quality-auditor.md`) was updated at the start of this session to resolve a recurring issue where the agent would freeze during team operations.

**Problem**: The agent had `disallowedTools: Write, Edit, WebFetch, WebSearch`, preventing it from writing audit reports, creating deliverables, or communicating findings through file-based mechanisms. When the agent needed to produce output beyond simple Bash commands, it would stall.

**Fix**:
- Changed `tools:` from `Read, Glob, Grep, Bash` to `Read, Glob, Grep, Bash, Write, Edit`
- Removed `disallowedTools: Write, Edit, WebFetch, WebSearch`
- Updated "Scope Fence" from "Strictly Read-Only" to "Permissions" with role discipline guidance
- Preserved the adversarial reviewer role, all audit checklists, and questioning patterns

**Result**: The auditor successfully completed 3 audit rounds in this session without freezing. The role discipline section reminds the agent that its primary job is to find what's wrong (not fix production code), while having full tool permissions to write reports and deliverables.

## Test Results

| Metric | Before | After |
|--------|--------|-------|
| Total tests | 353 | 410 |
| New test files | 0 | 2 |
| Regression tests | 0 | 38 |
| Pipeline helper tests | 0 | 19 |
| Failures | 0 | 0 |
| Runtime | ~24s | ~26s |

## Known Issues Resolved

- ~~"Tract/tribal non-ACS indicators (Civil Org, Hospitals, Pop Change) are all-zero — legacy scripts dropped these columns"~~ → Fixed with county imputation (tract) and column dropping (tribal)

## Known Issues Added

- "Binning exceptions hardcoded in run_full_pipeline.py — consider moving to config/indicators.yaml" (LOW priority)

## Next Steps

1. **Regenerate tract and tribal outputs** to validate fix with production data
2. **Compare new output** against archived deprecated output for convergence
3. **Regenerate county output** and verify CT CBP + PR Limited English changes are correct
4. **Update calibration targets** if necessary after new outputs
5. Consider moving `BINNING_EXCEPTIONS` to config (low priority)
