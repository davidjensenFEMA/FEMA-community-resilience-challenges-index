# CONOP: Diagnose and Repair Tract/Tribal bin_labels Output Issue

**Classification**: UNCLASSIFIED
**DTG**: 04 MAR 2026
**Status**: COMPLETE — Executed 04 MAR 2026, 6 divergences fixed, 410 tests passing, audit PASS
**References**: `config/project.yaml`, `src/core/aggregator.py`, `src/core/binning.py`, `deprecated/old_scripts/cria_create_aggregate_indicator.py`, `deprecated/old_scripts/cria_create_aggregate_tract.py`

---

## I. SITUATION

### Reported Issue
Tract and tribal output workbooks have a `bin_labels` tab where **all indicator columns show the same numbers**. The issue was reported by the product owner after reviewing `cria_results_tract_2024.xlsx` and `cria_results_tribal_2024.xlsx` generated during the 24 FEB 2026 production run.

### Current Pipeline Flow (bin_labels path)
```
create_aggregate()
    → _clean_indicators()      → df_clean
    → _rescale_indicators()    → df_scale (fractions ×100)
    → _bin_indicators(df_scale) → calls binning_engine.bin_dataframe()
                                   → returns [original cols + _bins cols]
                                   → stored as results["bin_labels"]
    → save_to_excel()          → writes bin_labels DataFrame as-is to Excel
```

### Key Code Locations
| File | Lines | Component | Role |
|------|-------|-----------|------|
| `src/core/binning.py` | 136-185 | `bin_dataframe()` | Returns DataFrame with BOTH original columns AND `{col}_bins` columns |
| `src/core/aggregator.py` | 388-425 | `_bin_indicators()` | Calls `bin_dataframe()`, stores full output as `"bins"` key |
| `src/core/aggregator.py` | 442-479 | `_bin_aggregate()` | Same pattern for aggregate scores |
| `src/core/aggregator.py` | 144-155 | `create_aggregate()` | Stores `_bin_indicators()["bins"]` directly as `"bin_labels"` |
| `src/core/aggregator.py` | 674-678 | `save_to_excel()` | Writes `bin_labels` DataFrame to Excel sheet |

### Deprecated Pipeline (Baseline for Comparison)
The deprecated `fit_data()` function (`deprecated/old_scripts/cria_functions.py:387-521`) returns `{"bins": df_labels}` where `df_labels` **also** contained both original indicator values and `_bins` columns (line 419: `df_labels[key] = ser`, line 473: `df_labels[col_bins] = fit_yb[best] + ...`).

The deprecated output `d["bin_labels"]` was accessed with `_bins` suffixes (e.g., `cria_create_aggregate_indicator.py:348-358`: `df_bin_labels[["Inactive Voter_bins", "state_abbr"]]`), confirming the old format included both raw and binned values.

### Archived Output Files Available
| File | Geography | Year | Location |
|------|-----------|------|----------|
| `cria_results_tract_2024.xlsx` | Tract | 2024 | `data/output/` |
| `cria_results_tribal_2024.xlsx` | Tribal | 2024 | `data/output/` |
| `cria_results_county_2024.xlsx` | County | 2024 | `data/output/` (comparison — reportedly OK) |
| `impute_tract_data_match_county_2021.xlsx` | Tract | 2021 | `data/output/` (old pipeline output) |
| `impute_tract_data_match_county_2022.xlsx` | Tract | 2022 | `data/output/` (old pipeline output) |

### Diagnostic Hypotheses (Ordered by Likelihood)

| # | Hypothesis | Likelihood | Evidence Needed |
|---|-----------|-----------|-----------------|
| H1 | **bin_dataframe() returns both original + binned columns; bin_labels tab shows the `_bins` columns which are all integers 1–k, giving the appearance of "same numbers"** | HIGH | Open tract XLSX, inspect column names on bin_labels sheet. If `_bins` suffixed columns all contain integers 1-7, this is the issue. Compare to deprecated output structure. |
| H2 | **Tract non-ACS indicators are imputed with uniform county values (all tracts in a county get the same county value), producing degenerate bins** | MEDIUM | Check if Civil Org, Hospitals, Pop Change columns in bin_labels have identical values per county group. |
| H3 | **Tribal non-ACS indicators are all NaN (not dropped as in deprecated code), causing bin_series to return all-NaN for 5 indicators** | MEDIUM | Check tribal bin_labels for NaN columns. In deprecated code, these were dropped entirely. |
| H4 | **`geo_reference` not passed to `create_aggregate()` in pipeline, causing PR Limited English or CT CBP special cases to not fire, corrupting data distribution** | LOW-MED | Check `run_full_pipeline.py` for `geo_reference` parameter. |
| H5 | **Binning engine auto-select produces same method for every indicator on large datasets (88K tract rows), leading to similar break patterns** | LOW | Check bin_meta tab — if `selected_method` is identical for all indicators, this is a factor. |

### Known Issues (from `config/project.yaml`)
- `"Tract/tribal non-ACS indicators (Civil Org, Hospitals, Pop Change) are all-zero — legacy scripts dropped these columns"`
- `"Audit H1: _mean_function has no NaN mask"`
- County output reportedly looks correct — issue is tract/tribal specific.

---

## II. MISSION

Diagnose and repair the tract/tribal `bin_labels` output issue so that all indicator columns show correct, differentiated bin classifications. Compare current output against archived/deprecated output to identify behavioral divergence. Audit all changes before declaring the fix complete.

### Commander's Intent
Find the root cause quickly. The fix should produce tract and tribal bin_labels output that matches the expected behavior from the deprecated pipeline — each indicator should have a distinct distribution of bin values reflecting the underlying data variance. The solution should not introduce regressions to county output.

### End State
- Root cause identified with code-level evidence
- Fix implemented and tested
- New tract and tribal outputs generated to validate the fix
- Comparison against archived outputs confirms parity
- Quality audit passes with no CRITICAL findings
- County output regression-tested (no change to existing county behavior)

---

## III. EXECUTION

### Phase 0: Reconnaissance — Reproduce and Characterize the Issue
**Purpose**: Open the reported output files, characterize the exact nature of "same numbers," and narrow the hypothesis list.
**Agent**: quality-auditor (read-only)

**Tasks:**

1. **Inspect tract bin_labels output** (`data/output/cria_results_tract_2024.xlsx`, sheet `bin_labels`):
   - List all column names — are there both `{Indicator}` and `{Indicator}_bins` columns?
   - For each `_bins` column: what is the value distribution? (unique values, value_counts)
   - Are ALL indicators showing the same distribution, or only a subset?
   - Compare: do the raw indicator columns (without `_bins`) show different distributions?

2. **Inspect tribal bin_labels output** (`data/output/cria_results_tribal_2024.xlsx`, sheet `bin_labels`):
   - Same analysis as tract above
   - Specifically check non-ACS indicators: are they NaN, zero, or populated?

3. **Inspect county bin_labels output** (`data/output/cria_results_county_2024.xlsx`, sheet `bin_labels`):
   - Same analysis — this is the "known good" baseline
   - Characterize how county bin_labels DIFFERS from tract/tribal

4. **Inspect archived tract output** (`data/output/impute_tract_data_match_county_2021.xlsx`, sheet `bin_labels` or equivalent):
   - This is the deprecated pipeline's output — what does "correct" look like?
   - Compare column structure to current output

5. **Inspect bin_meta sheets** (all three geographies):
   - Check `selected_method` column — is the same method selected for every indicator?
   - Check bin edge values — are they differentiated across indicators?

6. **Inspect agg_labels sheets** (all three geographies):
   - Same issue? If agg_labels also shows "same numbers," the problem is in `_bin_aggregate()` too.

7. **Deliver diagnosis report**:
   - Which hypothesis (H1-H5) is confirmed?
   - Exact characterization of "same numbers" with data evidence
   - Which code path produces the incorrect output?
   - Recommended fix approach

**Decision Authority**: Commander receives backbrief after Phase 0 before proceeding to repair.

---

### Phase 1: Compare Deprecated Workflow to Current Workflow
**Purpose**: Trace the exact data flow difference between deprecated and current code for tract and tribal.
**Agent**: cria-analyst (domain expertise on indicator formulas and aggregation)

**Tasks:**

1. **Trace deprecated tract workflow** (`deprecated/old_scripts/cria_create_aggregate_tract.py`):
   - How were non-ACS indicators handled? (Lines 257-266: set to NaN, then imputed from county)
   - How did `fit_data()` handle mixed NaN/valid columns?
   - What did the final `bin_labels` output structure look like?
   - How was the vote data modification applied? (Lines 287-311)

2. **Trace deprecated tribal workflow** (`deprecated/old_scripts/cria_create_indicators_tribal.py`):
   - Non-ACS indicators were dropped (`ref.loc[ref["Source"] != "ACS", "Indicator"]`)
   - Zero-population tribes excluded from binning
   - Only 17 indicators binned (not 22)

3. **Trace current pipeline for tract/tribal** (`src/core/aggregator.py`, `scripts/run_full_pipeline.py`):
   - Does the current pipeline impute tract non-ACS indicators from county? Or are they NaN/zero?
   - Does the current pipeline drop non-ACS indicators for tribal? Or does it bin all 22?
   - Is `geo_reference` passed to `create_aggregate()` for special case handling?

4. **Document behavioral divergences**:
   - For each divergence: is the current behavior intentional (improvement) or accidental (regression)?
   - Map each divergence to its impact on the bin_labels output

5. **Deliver comparison report** with table:
   ```
   | Behavior | Deprecated | Current | Impact on bin_labels |
   ```

---

### Phase 2: Implement Fix
**Purpose**: Repair the identified issue based on Phase 0/1 findings.
**Agent**: data-engineer (production code changes), cria-analyst (domain validation)

**Probable Fix Targets** (refined by Phase 0/1 findings):

#### Fix Path A: Column Filtering (if H1 confirmed)
If the issue is that `bin_dataframe()` returns both original and `_bins` columns:

In `aggregator.py` `_bin_indicators()` (line 389-393) and `_bin_aggregate()` (line 443-447), filter the output of `bin_dataframe()` to extract only the `_bins` columns:

```python
bin_labels_full = self.binning_engine.bin_dataframe(indicators, k=self.bins, exceptions_dict=exceptions)
# Extract only binned columns, rename to remove suffix
bin_cols = [c for c in bin_labels_full.columns if c.endswith("_bins")]
bin_labels = bin_labels_full[bin_cols].copy()
bin_labels.columns = [c.replace("_bins", "") for c in bin_labels.columns]
```

**Decision**: Should `_bins` suffix be kept or stripped? Compare to deprecated output format to match expectations.

#### Fix Path B: Tribal Non-ACS Indicator Handling (if H3 confirmed)
If tribal is attempting to bin all 22 indicators including 5 NaN columns:

Add tribal-specific handling in `_bin_indicators()` or `create_aggregate()` to drop non-ACS indicators before binning (matching deprecated behavior):

```python
if self.geography == "tribal" and reference is not None:
    non_acs = reference.loc[reference["Source"] != "ACS", "Indicator"].tolist()
    indicators = indicators.drop(columns=[c for c in non_acs if c in indicators.columns])
```

#### Fix Path C: Tract Imputation Logic (if H2 confirmed)
If tract non-ACS indicators have uniform county values creating degenerate bins:

The deprecated `cria_create_aggregate_tract.py` script (lines 247-281) had specific imputation logic that ran BEFORE aggregation. The current pipeline may be missing this step. If so, add tract-specific imputation or handle the imputed columns differently during binning.

#### Fix Path D: Combined Fix
Multiple hypotheses may be confirmed — implement all confirmed fixes.

**Constraints:**
- County output must not change (regression test)
- Fix must be minimal — no refactoring beyond what's needed
- All changes in `src/core/aggregator.py` and/or `scripts/run_full_pipeline.py` only

**Validation Steps:**
1. Run `poetry run pytest` — all existing tests pass
2. Regenerate tract output: `--geography tract --year 2024 --bins 7 --export-excel`
3. Regenerate tribal output: `--geography tribal --year 2024 --export-excel`
4. Regenerate county output: `--geography county --year 2024 --export-excel`
5. Spot-check: bin_labels tab in tract/tribal should show differentiated indicator bins
6. Regression check: county bin_labels should be unchanged from previous run

---

### Phase 3: Write Regression Tests
**Purpose**: Add tests that would catch this bug if it recurred.
**Agent**: statistical-tester (write access to `tests/` only)

**New Tests** (in `tests/unit/test_aggregator.py` or new file):

```
class TestBinLabelsOutput:
    test_bin_labels_columns_are_binned_not_raw
        # bin_labels should contain bin classifications (integers 1-k)
        # NOT raw indicator values (floats 0-100)

    test_bin_labels_indicators_have_distinct_distributions
        # Each indicator's bin distribution should differ
        # (unless data is genuinely uniform — edge case)

    test_tract_bin_labels_uses_7_bins
        # Tract output bins should range 1-7

    test_tribal_bin_labels_excludes_non_acs_indicators
        # Tribal bin_labels should NOT contain CBP/EAVS/ARDA/POP indicators
        # (or they should be NaN, matching deprecated behavior)

    test_agg_labels_columns_are_binned_not_raw
        # Same check for aggregate labels

    test_county_bin_labels_unchanged_after_fix
        # County output regression — no change from existing behavior
```

**Smoke Test Addition** (in `tests/smoke/test_pipeline_smoke.py`):
```
    test_tract_bin_labels_differentiated
        # After pipeline run with synthetic data, bin_labels tab
        # should have indicators with different value distributions

    test_tribal_bin_labels_acs_only
        # After pipeline run, tribal bin_labels should only have
        # ACS-sourced indicator bins
```

---

### Phase 4: Quality Audit
**Purpose**: Adversarial review of the diagnosis, fix, and tests.
**Agent**: quality-auditor (read-only — MANDATORY)

**Audit Checklist:**

1. **Diagnosis Accuracy**:
   - [ ] Root cause is identified with code-level evidence (not just symptoms)
   - [ ] All 5 hypotheses were evaluated (not just the first one that seemed right)
   - [ ] Evidence from actual output files supports the diagnosis

2. **Fix Correctness**:
   - [ ] Fix addresses root cause, not just symptoms
   - [ ] Fix does not introduce new issues in other code paths
   - [ ] County output regression confirmed (bit-for-bit identical or documented acceptable differences)
   - [ ] Fix matches deprecated behavior where appropriate

3. **Test Coverage**:
   - [ ] New tests would FAIL on the pre-fix code (test the test)
   - [ ] New tests are not tautological (don't just re-implement the code)
   - [ ] Edge cases covered: empty DataFrame, all-NaN column, single-value column

4. **Domain Compliance**:
   - [ ] Tribal output drops non-ACS indicators (matching deprecated behavior)
   - [ ] Tract output handles imputed indicators correctly
   - [ ] Bin counts match geography expectations (5 for county/tribal, 7 for tract)

5. **Comparison Validation**:
   - [ ] New output compared to archived deprecated output
   - [ ] Differences documented and explained
   - [ ] No unexplained divergences remain

**Deliverable**: Audit report with findings (CRITICAL/HIGH/MEDIUM/LOW) and verdict (PASS / PASS WITH CONCERNS / FAIL).

---

## IV. AGENT TASK ASSIGNMENT

### Team Composition

| Agent | Role | Write Scope | Phases |
|-------|------|-------------|--------|
| **quality-auditor** | Diagnosis recon + final audit | Read-only | 0, 4 |
| **cria-analyst** | Deprecated vs current comparison | Read-only | 1 |
| **data-engineer** | Implement fix, regenerate outputs | `src/`, `scripts/` | 2 |
| **statistical-tester** | Write regression tests | `tests/` only | 3 |

### Dependency Chain

```
Phase 0 (quality-auditor: reproduce & characterize)
    │
    ├── delivers diagnosis report
    │
    ▼
BACKBRIEF TO COMMANDER — confirm root cause, approve fix approach
    │
    ▼
Phase 1 (cria-analyst: deprecated vs current comparison) ← can run parallel with Phase 0
    │
    ▼
Phase 2 (data-engineer: implement fix + regenerate outputs)
    │
    ▼
Phase 3 (statistical-tester: regression tests) ← can run parallel with Phase 2 validation
    │
    ▼
Phase 4 (quality-auditor: audit fix + tests + outputs)
```

### Coordination Protocol
- **Phase 0**: quality-auditor works independently on output inspection. Delivers findings as structured report.
- **Backbrief**: Commander reviews Phase 0 findings. Approves fix approach before Phase 2 begins.
- **Phase 1**: cria-analyst can start in parallel with Phase 0 (code comparison doesn't require output inspection).
- **Phase 2**: data-engineer implements fix based on confirmed hypothesis. Regenerates all three geography outputs.
- **Phase 3**: statistical-tester writes tests based on Phase 0 characterization (can begin once diagnosis is clear, doesn't need to wait for fix).
- **Phase 4**: quality-auditor reviews everything. If CRITICAL findings, loop back to Phase 2.

---

## V. ESCALATION CRITERIA

Pause and report to commander if:
1. Phase 0 reveals the issue is NOT in bin_labels but in upstream data (indicators or source data) — scope change
2. Fix requires changes to `src/core/binning.py` (BinningEngine core logic) — higher risk
3. County output changes as a result of the fix — unintended regression
4. Quality auditor issues CRITICAL finding after fix
5. Multiple hypotheses are confirmed simultaneously — need commander's priority call on fix ordering
6. Archived deprecated output files are missing or corrupted — cannot validate comparison

---

## VI. SUCCESS CRITERIA

- [ ] Root cause identified with code-level evidence and output file evidence
- [ ] Fix implemented: tract bin_labels shows differentiated indicator bins (not "same numbers")
- [ ] Fix implemented: tribal bin_labels shows differentiated indicator bins for ACS indicators
- [ ] County regression: bin_labels output unchanged (or changes documented and approved)
- [ ] New regression tests added (≥6 tests) that would catch recurrence
- [ ] All existing tests pass (`poetry run pytest` exit code 0)
- [ ] Quality audit verdict: PASS or PASS WITH CONCERNS (no CRITICAL findings)
- [ ] Deprecated output comparison documented with table of differences

---

## ANNEXES

### Annex A: Quick Diagnostic Commands
```python
# Load and inspect bin_labels from tract output
import pandas as pd

# Tract
df_t = pd.read_excel("data/output/cria_results_tract_2024.xlsx", sheet_name="bin_labels")
print("Tract bin_labels columns:", list(df_t.columns))
print("Tract bin_labels shape:", df_t.shape)
bins_cols = [c for c in df_t.columns if c.endswith("_bins")]
print("_bins columns:", bins_cols)
for col in bins_cols[:5]:
    print(f"\n{col}:", df_t[col].value_counts().to_dict())

# Tribal
df_r = pd.read_excel("data/output/cria_results_tribal_2024.xlsx", sheet_name="bin_labels")
print("\nTribal bin_labels columns:", list(df_r.columns))
bins_cols_r = [c for c in df_r.columns if c.endswith("_bins")]
for col in bins_cols_r[:5]:
    print(f"\n{col}:", df_r[col].value_counts().to_dict())

# County (known good)
df_c = pd.read_excel("data/output/cria_results_county_2024.xlsx", sheet_name="bin_labels")
print("\nCounty bin_labels columns:", list(df_c.columns))
```

### Annex B: Deprecated vs Current Pipeline Comparison (Pre-Analysis)

| Aspect | Deprecated (tract) | Deprecated (tribal) | Current Pipeline |
|--------|-------------------|--------------------|--------------------|
| Non-ACS indicator handling | Set to NaN, imputed from county | Dropped entirely | Kept as NaN (no imputation, no drop) |
| Binning input | `df_scale` (rescaled indicators) | `df_scale` (17 ACS indicators only) | `df_scale` (all 22 indicators) |
| `fit_data` / `bin_dataframe` output | `{original + _bins}` columns | `{original + _bins}` columns | `{original + _bins}` columns |
| Zero-population handling | N/A | Excluded from binning | Not excluded |
| `geo_reference` passed | Via geographies dict merge | Via geographies dict merge | **Not passed to `create_aggregate()`** |
| Vote data modification | Post-hoc on bin_labels | N/A | Not in current pipeline |
| Bin count | 7 | 5 | Configurable (default 5) |

### Annex C: Key File Paths
```
Current Code:
  src/core/aggregator.py            # _bin_indicators(), _bin_aggregate(), create_aggregate()
  src/core/binning.py               # bin_dataframe(), bin_series()
  scripts/run_full_pipeline.py      # Pipeline orchestration, --bins CLI arg

Deprecated Code:
  deprecated/old_scripts/cria_functions.py                  # fit_data() - old binning
  deprecated/old_scripts/cria_create_aggregate_indicator.py # Old county aggregation
  deprecated/old_scripts/cria_create_aggregate_tract.py     # Old tract aggregation + imputation
  deprecated/old_scripts/cria_create_indicators_tribal.py   # Old tribal indicator calc

Output Files:
  data/output/cria_results_tract_2024.xlsx   # Current (issue reported)
  data/output/cria_results_tribal_2024.xlsx  # Current (issue reported)
  data/output/cria_results_county_2024.xlsx  # Current (reportedly OK)
  data/output/impute_tract_data_match_county_2021.xlsx  # Deprecated output (baseline)
```
