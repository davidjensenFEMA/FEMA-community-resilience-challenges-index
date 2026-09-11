# CONOP: Tribal Output — Remove Aggregation, Fix Binning

**Date**: 2026-03-05
**Status**: COMPLETE
**Priority**: High — stakeholder-reported defect + behavioral correction
**Supersedes**: Previous CONOP version (D10-only fix)

---

## 1. SITUATION

### Current State

The tribal output (`cria_results_tribal_2024.xlsx`) has two categories of defects:

**Defect A: Wrong output structure — tribal computes CRCI/aggregate (should not)**

The current pipeline runs tribal through the full `create_aggregate()` method, producing:
- `agg` tab (aggregate z-scores: agg, cri, cria_p)
- `agg_labels` tab (binned aggregate scores)
- `agg_meta` tab (aggregate binning metadata)
- `pos`, `scores`, `scores_percentiles` tabs (intermediate aggregation products)

The deprecated pipeline (`deprecated/old_scripts/cria_create_indicators_tribal.py`) produced NONE of these. Its output dict was:
```python
d = {"ref": ref, "bin_meta": bin_results["meta"], "bin_labels": bin_results["bins"],
     "data": data, "indicators": df}
```
No aggregation, no CRCI, no z-scores. Just binned indicators.

**Defect B: GEO_ID contamination — county rows in tribal output**

The DataPuller's outer merge (`data_puller.py:206`) introduces 3,301 county-format GEO_IDs (`0500000US*`) alongside 618 tribal GEO_IDs (`2500000US*`). The D8 zero-pop filter removes these from `indicators`/`agg` (they have NaN pop → fillna(0) → filtered out), but D8b reindexes `bin_labels` and `agg_labels` back to the full contaminated index of 3,919 rows. County rows (sorted first alphabetically) show as pages of NaN, burying the 618 valid tribal rows.

### Current Tribal Output Tabs

| Tab | Rows | Should Exist? | Issue |
|-----|------|--------------|-------|
| ref | 22 | Yes | OK |
| years | 6 | Yes | OK |
| indicators | 618 | Yes | OK (17 ACS indicators) |
| pos | 618 | **No** | Intermediate aggregation product |
| scores | 618 | **No** | Intermediate aggregation product |
| scores_percentiles | 618 | **No** | Intermediate aggregation product |
| agg | 618 | **No** | Aggregate CRCI — tribal should not have |
| bin_labels | 3,919 | Yes (but fix rows) | 3,301 county GEO_IDs contaminating |
| bin_meta | 85 | Yes | OK (17 indicators x 5 bins) |
| agg_labels | 3,919 | **No** | Aggregate bins — should not exist |
| agg_meta | 15 | **No** | Aggregate binning metadata — should not exist |

### Deprecated Tribal Behavior (Ground Truth)

From `deprecated/old_scripts/cria_create_indicators_tribal.py`:

1. **Indicators**: 17 ACS-only (dropped non-ACS: Civil Org, Hospitals, Religion, Inactive Voter, Population Change)
2. **Clean**: `clean_series(impute=False)` — NaN stays NaN, no mean imputation
3. **Rescale**: fractions/indexes × 100 (same as current)
4. **Zero-pop filter**: Filter to non-zero `S0101_C01_001E` before binning
5. **Bin**: `fit_data()` with `groups=5`, `drop_na_val=True` (auto-select best method)
6. **Reindex**: Bins reindexed to full tribal geography index (zero-pop rows get NaN bins)
7. **No aggregation**: No z-scores, no CRCI, no reorientation
8. **Output**: `{ref, bin_meta, bin_labels, data, indicators}` — 5 tabs only

### Stakeholder Requirement

> "Tribal shouldn't have an aggregate, and therefore, shouldn't have a CRCI. However, we should still apply the binning function to the base indicators. The bins were not showing for the indicators in the tribal sheet, and I use those for the visualizations."

---

## 2. MISSION

Update the tribal pipeline to:
1. **Remove aggregation** — no CRCI, no aggregate tabs
2. **Keep binning** — bin individual indicators into 5 bins for visualizations
3. **Fix GEO_ID contamination** — filter to tribal-only (`2500000US*`) GEO_IDs
4. **Match deprecated behavior** — same output structure as legacy scripts

---

## 3. EXECUTION

### Desired End State

**Tribal output tabs** (`cria_results_tribal_2024.xlsx`):

| Tab | Rows | Columns | Description |
|-----|------|---------|-------------|
| ref | 22 | ~21 | Indicator reference metadata |
| years | 6 | 3 | Data year configuration |
| indicators | 618 | 17 | Raw ACS-only indicator values (non-zero-pop tribal) |
| bin_labels | ~700 | 34 | 17 indicators + 17 `_bins` columns (full tribal index, zero-pop = NaN) |
| bin_meta | 85 | ~10 | Binning metadata (17 indicators × 5 bins) |

**Tabs removed**: pos, scores, scores_percentiles, agg, agg_labels, agg_meta

**GEO_ID requirement**: ALL rows use `2500000US*` prefix (zero county-format GEO_IDs)

---

### Phase 1: Pre-Fix Audit (READ-ONLY)

**Agent**: quality-auditor
**Purpose**: Confirm both defects and establish baseline measurements

#### Task 1.1: Confirm aggregation tabs exist in current tribal output

**TASK**: Read `data/output/cria_results_tribal_2024.xlsx`. List all tab names. For tabs `agg`, `agg_labels`, `agg_meta`, document column names and row counts.

**CONDITION**: Current output contains aggregation-related tabs that should not exist for tribal.

**STANDARD**:
- [ ] Tabs `agg`, `agg_labels`, `agg_meta` exist in current output
- [ ] `agg` tab has columns: agg, cri, cria_p (and possibly pop change, pop_p)
- [ ] `pos`, `scores`, `scores_percentiles` tabs exist
- [ ] Document exact tab list, row counts, column counts per tab

**FAIL**: If agg/agg_labels/agg_meta do NOT exist (already fixed or different file)

#### Task 1.2: Confirm GEO_ID contamination in bin_labels

**TASK**: Read `bin_labels` tab. Count GEO_IDs by prefix pattern (`0500000US*` vs `2500000US*`).

**CONDITION**: County GEO_IDs are mixed into tribal output due to DataPuller outer merge.

**STANDARD**:
- [ ] bin_labels contains GEO_IDs starting with `0500000US*` (county format)
- [ ] bin_labels contains GEO_IDs starting with `2500000US*` (tribal format)
- [ ] All `0500000US*` rows have 100% NaN in data columns
- [ ] Document: N county GEO_IDs, N tribal GEO_IDs, N non-zero-pop tribal
- [ ] Verify same contamination in `agg_labels`

#### Task 1.3: Verify county and tract outputs are NOT affected

**TASK**: Spot-check `cria_results_county_2024.xlsx` and `cria_results_tract_2024.xlsx` for cross-contamination.

**CONDITION**: Only tribal output should change; county/tract must be untouched.

**STANDARD**:
- [ ] County bin_labels: all GEO_IDs match `0500000US*`
- [ ] Tract bin_labels: all GEO_IDs match `1400000US*`
- [ ] Both have agg/agg_labels tabs (correct for county/tract)

#### Task 1.4: Document baseline metrics for regression testing

**TASK**: Record all dimensions that the post-fix audit will compare against.

**STANDARD**:
- [ ] Table: tab name → row count, column count, non-NaN row count (for each tab)
- [ ] tribal indicators row count = 618
- [ ] tribal bin_meta indicator count (should be 17)
- [ ] tribal bin_labels `_bins` columns: value range (1-5)
- [ ] Baseline saved to task output for Phase 6 comparison

---

### Phase 2: Code Review + Design Validation (READ-ONLY)

**Agent**: cria-analyst
**Purpose**: Validate the design against deprecated behavior and identify all code touchpoints

#### Task 2.1: Confirm deprecated tribal had NO aggregation

**TASK**: Read `deprecated/old_scripts/cria_create_indicators_tribal.py` in full. Document the output dict structure.

**CONDITION**: Deprecated tribal output must not contain aggregate products.

**STANDARD**:
- [ ] Output dict keys: `{"ref", "bin_meta", "bin_labels", "data", "indicators"}` — NO agg/agg_labels
- [ ] No call to `calc_z_scores()` or aggregate-related functions
- [ ] `clean_series` called with `impute=False` (not `impute=True`)
- [ ] `fit_data()` called with `groups=5` (5 bins)
- [ ] Zero-pop filter applied BEFORE binning

#### Task 2.2: Trace current aggregation path for tribal

**TASK**: Read `scripts/run_full_pipeline.py` lines 498-531 and `src/core/aggregator.py` `create_aggregate()`. Document which steps apply to tribal.

**CONDITION**: Current pipeline runs tribal through full aggregation (steps 1-8 in create_aggregate).

**STANDARD**:
- [ ] Document: which of the 8 steps in `create_aggregate()` tribal NEEDS vs should SKIP
- [ ] Steps tribal NEEDS: 1 (clean), 2 (rescale), 3 (bin indicators)
- [ ] Steps tribal should SKIP: 4 (reorient), 5 (z-scores), 6 (aggregate), 7 (bin aggregate), 8 (percentiles)
- [ ] Confirm: `create_aggregate()` currently has no mechanism to skip steps 4-8

#### Task 2.3: Validate proposed design — `skip_aggregation` parameter

**TASK**: Evaluate adding `skip_aggregation: bool = False` parameter to `create_aggregate()`.

**CONDITION**: The method must support tribal (binning-only) and county/tract (full aggregation) from the same entry point.

**STANDARD**:
- [ ] When `skip_aggregation=True`:
  - Execute steps 1-3 (clean, rescale, bin)
  - Skip steps 4-8 (reorient, z-scores, aggregate, bin-aggregate, percentiles)
  - Return dict with keys: `{"indicators", "bin_labels", "bin_meta"}` only
  - Do NOT include empty DataFrames for skipped keys
- [ ] When `skip_aggregation=False` (default): existing behavior unchanged
- [ ] Identify all callers of `create_aggregate()` — confirm only `run_full_pipeline.py`
- [ ] Confirm `save_to_excel()` already handles missing keys (iterates `sheet_order`, checks `if sheet_name in results`)

#### Task 2.4: Identify all pipeline code that accesses aggregation results

**TASK**: In `run_full_pipeline.py`, find every line that reads from `results["agg"]`, `results["agg_labels"]`, etc.

**CONDITION**: Lines that assume aggregation results exist will break when tribal skips aggregation.

**STANDARD**:
- [ ] Line 531: `agg_df = results["agg"]` — will KeyError if no "agg" key
- [ ] Line 536-539: database save — calls `aggregator.save_to_database(results, ...)` which reads `results.get("agg")`
- [ ] Lines 516-520: D8b reindex of `bin_labels` and `agg_labels` — `agg_labels` won't exist
- [ ] Document each line that needs a guard clause or conditional

#### Task 2.5: Validate tribal GEO_ID prefix

**TASK**: Confirm tribal GEO_IDs use prefix `2500000US` from at least 2 sources.

**STANDARD**:
- [ ] Deprecated code: `ser_ref["geographies"]["tribal"].index` uses `2500000US*`
- [ ] Current output: tribal rows in `cria_results_tribal_2024.xlsx` use `2500000US*`
- [ ] Document: `2500000US` = Census AIANNH summary level (American Indian Area/Alaska Native Area/Hawaiian Home Land)

---

### Phase 3: Implement Changes

**Agent**: data-engineer
**Purpose**: Modify aggregator and pipeline to support tribal binning-only mode

#### Task 3.1: Add `skip_aggregation` parameter to `create_aggregate()`

**TASK**: Edit `src/core/aggregator.py` method `create_aggregate()`.

**CONDITION**: The method currently always runs all 8 steps including aggregation.

**STANDARD**:
- [ ] Add parameter: `skip_aggregation: bool = False`
- [ ] When `skip_aggregation=True`:
  - Execute Step 1 (`_clean_indicators`) — but pass `impute=False` for tribal matching deprecated behavior consideration (see Note below)
  - Execute Step 2 (`_rescale_indicators`)
  - Execute Step 3 (`_bin_indicators`) if `bin_indicators=True`
  - SKIP Steps 4-8
  - Return: `{"indicators": df_clean, "bin_labels": bin_labels, "bin_meta": bin_meta}`
- [ ] When `skip_aggregation=False`: behavior is **identical** to before (no regression)
- [ ] Update docstring to document the parameter

**Note on imputation**: The deprecated tribal script used `clean_series(impute=False)`. The current aggregator uses `impute=True`. For this CONOP, keep `impute=True` as default for `skip_aggregation` path to minimize behavior change. If stakeholder reports issues with bin distributions, changing to `impute=False` can be a follow-up. Document this decision.

**FAIL CONDITIONS**:
- Modifying the `impute=True` default behavior when `skip_aggregation=False` (would break county/tract)
- Removing or renaming existing parameters
- Changing behavior when `skip_aggregation=False` in any way

#### Task 3.2: Add D10 tribal GEO_ID filter to pipeline

**TASK**: Edit `scripts/run_full_pipeline.py`. Add tribal GEO_ID prefix filter BEFORE D1b.

**CONDITION**: Same contamination pattern as D9 (tract). Place between D9 and D1b.

**STANDARD**:
- [ ] Filter: `indicators.index.str.startswith("2500000US")`
- [ ] Also filter `source_data` and `geo_reference` to same mask
- [ ] Place BEFORE D1b (non-ACS column drop) and D8 (zero-pop filter)
- [ ] Log: `"Tribal: filtered to N tribal GEO_IDs (removed N county-format GEO_IDs)"`
- [ ] Comment references D10

#### Task 3.3: Call `create_aggregate()` with `skip_aggregation=True` for tribal

**TASK**: Edit `scripts/run_full_pipeline.py` Step 3 to pass `skip_aggregation=True` when `geography == "tribal"`.

**STANDARD**:
- [ ] `results = aggregator.create_aggregate(..., skip_aggregation=(geography == "tribal"))`
- [ ] Guard line 531: `agg_df = results.get("agg")` instead of `results["agg"]`
- [ ] Guard lines 532-533: Only log aggregate count if `agg_df is not None`
- [ ] Guard lines 536-539: Only save to database if `"agg" in results`
- [ ] Guard D8b (lines 516-520): Only reindex keys that exist in results
- [ ] Guard D6 (lines 522-529): Only call `_nullify_zero_vote_states` if `"bin_labels" in results and "Inactive Voter_bins" in results.get("bin_labels", pd.DataFrame()).columns` (tribal drops Inactive Voter anyway, so this is just safety)

#### Task 3.4: Run existing test suite

**TASK**: `poetry run pytest -x -q`

**CONDITION**: All 410 existing tests must pass.

**STANDARD**:
- [ ] All 410 tests pass
- [ ] No errors or unexpected warnings
- [ ] If tests fail, fix the code (not the tests) — unless the test was asserting tribal has aggregation

---

### Phase 4: Write Tests

**Agent**: statistical-tester
**Purpose**: Add tests enforcing tribal-specific behavior and preventing regression

#### Task 4.1: Test tribal output has NO aggregation tabs

**TASK**: Add test(s) verifying tribal results dict does NOT contain aggregation keys.

**STANDARD**:
- [ ] Test: `create_aggregate(skip_aggregation=True)` returns dict WITHOUT keys: `pos`, `scores`, `scores_percentiles`, `agg`, `agg_labels`, `agg_meta`
- [ ] Test: `create_aggregate(skip_aggregation=True)` returns dict WITH keys: `indicators`, `bin_labels`, `bin_meta`
- [ ] Test: `create_aggregate(skip_aggregation=False)` still returns ALL keys (regression guard)
- [ ] Uses synthetic data (no API calls)

#### Task 4.2: Test tribal GEO_ID filtering (D10)

**TASK**: Add test(s) verifying tribal output contains ONLY `2500000US*` GEO_IDs.

**STANDARD**:
- [ ] Test: after D10 filter, all `indicators.index` start with `2500000US`
- [ ] Test: no `0500000US*` GEO_IDs remain
- [ ] Test: row count decreases (contaminated → tribal-only)
- [ ] Uses synthetic data

#### Task 4.3: Test tribal bin_labels structure

**TASK**: Add test(s) verifying bin_labels has correct structure for tribal.

**STANDARD**:
- [ ] Test: bin_labels contains indicator columns + matching `_bins` columns
- [ ] Test: `_bins` columns contain values 1-5 (5 bins, not 7)
- [ ] Test: non-NaN row count matches indicators row count
- [ ] Test: bin_labels index is superset of indicators index (reindexed includes zero-pop NaN rows)

#### Task 4.4: Parametrized GEO_ID prefix guard

**TASK**: Add parametrized test across ALL geographies ensuring GEO_ID consistency.

**STANDARD**:
- [ ] Parametrized: county (`0500000US`), tract (`1400000US`), tribal (`2500000US`)
- [ ] Each geography verifies its results contain ONLY matching-prefix GEO_IDs
- [ ] Prevents any future cross-geography contamination

#### Task 4.5: Test county/tract unchanged (regression)

**TASK**: Add test(s) verifying county and tract still have aggregation.

**STANDARD**:
- [ ] Test: county `create_aggregate()` returns `agg`, `agg_labels`, `agg_meta`
- [ ] Test: tract `create_aggregate()` returns `agg`, `agg_labels`, `agg_meta`
- [ ] These are regression guards — they fail if someone accidentally adds `skip_aggregation=True` for county/tract

#### Task 4.6: Run full test suite

**TASK**: `poetry run pytest -x -q`

**STANDARD**:
- [ ] All tests pass (410 existing + new)
- [ ] Document new test count

---

### Phase 5: Regenerate Tribal Output

**Agent**: data-engineer
**Purpose**: Run the tribal pipeline to produce corrected output

#### Task 5.1: Archive current output

**TASK**: Copy current tribal output to archive directory.

```bash
mkdir -p data/output/archive_pre_tribal_fix
cp data/output/cria_results_tribal_2024.xlsx data/output/archive_pre_tribal_fix/
```

**STANDARD**:
- [ ] Archive file exists and is byte-identical to current output

#### Task 5.2: Run tribal pipeline

**TASK**: Run pipeline with `--geography tribal --year 2024 --export-excel --skip-pull`.

```bash
DATABASE_URL="postgresql://cria_user:cria_password@localhost:5433/cria_db" \
  poetry run python scripts/run_full_pipeline.py \
  --geography tribal --year 2024 --export-excel --skip-pull
```

**STANDARD**:
- [ ] Pipeline completes without errors
- [ ] Log shows D10: "Tribal: filtered to N tribal GEO_IDs (removed N county-format GEO_IDs)"
- [ ] Log shows D8: "Tribal: filtered to N non-zero-population rows"
- [ ] Log does NOT show "Creating aggregate indicator" or aggregate-related messages (or shows skip message)
- [ ] Output file: `data/output/cria_results_tribal_2024.xlsx`
- [ ] Pipeline runtime ~21 seconds (no slower than before)

**FAIL CONDITIONS**:
- Pipeline crashes
- D10 log shows 0 removed (contamination not present — investigate)
- Aggregate-related log messages appear (aggregation not skipped)

---

### Phase 6: Post-Fix Audit

**Agent**: quality-auditor
**Purpose**: Validate the regenerated output meets all acceptance criteria

#### Task 6.1: Structural validation — correct tabs exist

**TASK**: Read `cria_results_tribal_2024.xlsx`. List all tab names.

**STANDARD**:
- [ ] Tabs present: `ref`, `years`, `indicators`, `bin_labels`, `bin_meta` (5 tabs)
- [ ] Tabs ABSENT: `pos`, `scores`, `scores_percentiles`, `agg`, `agg_labels`, `agg_meta` (6 tabs removed)
- [ ] Total tab count: 5 (was 11)

#### Task 6.2: GEO_ID validation — no county contamination

**TASK**: Check all tabs for GEO_ID prefix consistency.

**STANDARD**:
- [ ] `indicators`: ALL GEO_IDs start with `2500000US` (ZERO `0500000US*`)
- [ ] `bin_labels`: ALL GEO_IDs start with `2500000US` (ZERO `0500000US*`)
- [ ] `bin_labels` row count < 1,000 (was 3,919 with contamination)

#### Task 6.3: Bin population validation — bins visible on open

**TASK**: Check that `bin_labels` has populated values starting from the first row.

**STANDARD**:
- [ ] First row of `bin_labels` has non-NaN bin values (not all None)
- [ ] Non-NaN row count in `bin_labels` = 618 (matches indicators row count)
- [ ] NaN-only rows are ONLY for zero-population tribal areas (legitimate)
- [ ] Bins are visible immediately when file is opened (no scrolling past NaN rows)

#### Task 6.4: Bin distribution validation

**TASK**: Check bin value distributions for non-NaN rows.

**STANDARD**:
- [ ] `_bins` columns contain values 1-5 (5 bins for tribal)
- [ ] No single bin has >50% of values (no degenerate concentration) — exception for real-world skew like Mobile Homes, Limited English which were validated as acceptable in previous audit
- [ ] All 17 indicator `_bins` columns have non-NaN values
- [ ] bin_meta has 85 rows (17 indicators × 5 bins)

#### Task 6.5: Indicator column validation

**TASK**: Verify tribal has exactly 17 ACS-only indicators.

**STANDARD**:
- [ ] indicators tab: 17 columns (ACS-only)
- [ ] Missing (correct): Civil Org, Hospitals, Religion, Inactive Voter, Population Change
- [ ] Present: Mobile Homes, Owner Occupied, Education, No Vehicle, Age, Disability, Limited English, Single Parent, Low Access to Communications, Unemployment, Unemployed Women, Median Income, GINI, Lack of Economic Diversity, Poverty, Medical, Uninsured Population
- [ ] bin_labels: 34 columns (17 indicators + 17 `_bins`)

#### Task 6.6: Row count consistency

**TASK**: Verify row counts are consistent across tabs.

**STANDARD**:
- [ ] indicators: 618 rows (non-zero-pop tribal only)
- [ ] bin_labels: > 618 rows (includes zero-pop rows with NaN bins)
- [ ] bin_labels non-NaN row count = indicators row count (618)
- [ ] bin_labels index is superset of indicators index

#### Task 6.7: County and tract regression check

**TASK**: Verify county and tract outputs are UNCHANGED.

**STANDARD**:
- [ ] County output file: unchanged (same modification time or byte-identical)
- [ ] Tract output file: unchanged (same modification time or byte-identical)
- [ ] County output still has agg/agg_labels/agg_meta tabs
- [ ] Tract output still has agg/agg_labels/agg_meta tabs

---

## 4. AGENT TEAM ASSIGNMENT

| Phase | Agent | Type | Mode | Isolation |
|-------|-------|------|------|-----------|
| 1. Pre-Fix Audit | auditor | quality-auditor | read-only | none |
| 2. Code Review | analyst | cria-analyst | read-only | none |
| 3. Implement | engineer | data-engineer | edit | none |
| 4. Tests | tester | statistical-tester | edit | none |
| 5. Regenerate | engineer | data-engineer | edit | none (needs DB) |
| 6. Post-Fix Audit | auditor-2 | quality-auditor | read-only | none |

### Parallelization

- **Phase 1 + Phase 2**: Run in parallel (both read-only)
- **Phase 3**: Sequential (depends on Phase 2 validation)
- **Phase 4**: Can START in parallel with Phase 3 (tests written against expected behavior), but must RUN after Phase 3 merges
- **Phase 5**: Sequential (depends on Phase 3 completion + Phase 4 tests passing)
- **Phase 6**: Sequential (depends on Phase 5 output)

---

## 5. FILES MODIFIED

| File | Change | Risk |
|------|--------|------|
| `src/core/aggregator.py` | Add `skip_aggregation` parameter to `create_aggregate()` | LOW — new param with default preserves behavior |
| `scripts/run_full_pipeline.py` | D10 filter + `skip_aggregation=True` for tribal + guard clauses | MEDIUM — multiple touchpoints |
| `tests/unit/test_tribal_output.py` (new) | Tribal-specific tests | NONE — new file |
| `tests/unit/test_bin_labels_regression.py` | May need updates if tests assume tribal has agg | LOW |
| `data/output/cria_results_tribal_2024.xlsx` | Regenerated with correct structure | LOW — archived first |

---

## 6. SUCCESS CRITERIA (Overall)

The fix is COMPLETE when ALL of the following are true:

1. **No aggregation in tribal output** — zero `agg`, `agg_labels`, `agg_meta` tabs
2. **No intermediate tabs** — zero `pos`, `scores`, `scores_percentiles` tabs
3. **Bins visible on first row** — open file, see bin values immediately
4. **No county GEO_IDs** — zero `0500000US*` entries in any tab
5. **618 non-NaN rows** — matches count of valid non-zero-pop tribal areas
6. **17 indicators binned into 5 bins** — ACS-only, correct bin count
7. **All tests pass** — 410+ existing + new tribal tests
8. **County and tract unaffected** — no regressions
9. **Quality auditor sign-off** — Phase 6 all PASS

---

## 7. ROLLBACK PLAN

If the fix causes unexpected issues:
1. Restore archived output: `cp data/output/archive_pre_tribal_fix/cria_results_tribal_2024.xlsx data/output/`
2. Revert code: `git revert HEAD` (or HEAD~N for multi-commit)

---

## 8. OPEN QUESTIONS FOR STAKEHOLDER

1. **Imputation behavior**: Deprecated tribal used `impute=False` (NaN stays NaN). Current pipeline uses `impute=True` (NaN → column mean). CONOP keeps `impute=True` for now. Should tribal match deprecated `impute=False`?

2. **Output filename**: Current is `cria_results_tribal_2024.xlsx`. Deprecated was `cria_tribal_bins_2024.xlsx`. Keep current naming for consistency?

3. **Source data tab**: Deprecated included `data` tab (raw source data). Current `cria_results_*` files don't include source data (it's in separate `cria_inputs_tribal.xlsx`). Keep current separation?
