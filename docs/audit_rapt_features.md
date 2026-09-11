# Audit: RAPT Features (Pop Change Direction, Lowest Indicators, Correlation Matrix)

**Date**: 2026-04-07
**Auditor**: quality-auditor agent
**Test suite**: 541 tests passing (0 failures)
**Scope**: All code changes for 3 features: pop change/pop_p bin direction fix, lowest indicators tab, correlation matrix output

---

## Findings Table

| ID | Severity | Description | File | Line |
|----|----------|-------------|------|------|
| F1 | **must-fix** | `_compute_lowest_indicators` crashes with `KeyError` on empty DataFrame (0 rows) | `src/core/aggregator.py` | 382 |
| F2 | **should-fix** | `corr_zero` reports `1` (significant) when `r=NaN` (all-NaN or constant column) -- claims significant correlation when none exists | `src/core/transformations.py` | 359,374 |
| F3 | **should-fix** | `_compute_correlation` uses hardcoded relative path `"data/cria_data_reference.xlsx"` instead of `Paths.reference_data` from `src/config/paths.py:89` -- will fail if cwd differs from project root | `src/core/aggregator.py` | 418 |
| F4 | **note** | `pearsonr_ci` with `n=3` triggers `RuntimeWarning: divide by zero` (`se=1/sqrt(0)=inf`), producing CI=[-1,1] -- functionally correct but noisy | `src/core/transformations.py` | 326 |
| F5 | **note** | `arctanh(1.0)=inf` on diagonal (self-correlation) triggers `RuntimeWarning: divide by zero in arctanh` -- functionally correct (`tanh(inf)=1.0`) but noisy | `src/core/transformations.py` | 325 |
| F6 | **note** | `save_to_excel` mutates the caller's `results` dict in-place when `include_geo=True` (replaces DataFrames with geo-merged versions) -- pre-existing issue, not introduced by these changes | `src/core/aggregator.py` | 803-810 |
| F7 | **note** | `_score` suffix replaces deprecated `_perc` suffix in lowest_ind columns -- intentional rename, verified in tests | `src/core/aggregator.py` | 398 |
| F8 | **note** | Pop change/pop_p `reverse: False` is an **intentional divergence** from deprecated behavior (which used `[::-1]` reversed labels) -- confirmed by task assignment and updated tests | `src/core/binning.py` | 40-45 |

---

## F1 Detail: Empty DataFrame Crash in `_compute_lowest_indicators`

**Evidence**: Running `_compute_lowest_indicators(pd.DataFrame(columns=['A','B','C']), n=3)` raises:
```
KeyError: "['ind_1_score', 'ind_2_score', 'ind_3_score', 'list_labels'] not in index"
```

**Root cause**: `np.argsort(values, axis=1)[:, :n]` on a 0-row array produces shape `(0, n)`. The subsequent `pd.concat([df_names, df_values], axis=1)` produces an empty DataFrame with only the `ind_*` columns from `df_names`, missing the `ind_*_score` and `list_labels` columns that would come from `df_values`. The final `result[sorted_cols]` then fails because those columns don't exist.

**Impact**: Would crash if somehow an empty z-score DataFrame reached this function (unlikely in normal pipeline, but possible in edge cases or testing).

**Recommendation**: Add an early return guard:
```python
if len(df_scores) == 0:
    return pd.DataFrame()
```

## F2 Detail: `corr_zero` Misleading for NaN Correlations

**Evidence**: When a column is all-NaN or constant (zero variance), `pearsonr_ci` returns `r=NaN, lo=NaN, hi=NaN`. The `corr_zero` matrix is initialized to `1` (significant). The guard at line 374:
```python
if not np.isnan(lo) and lo < 0 < hi:
    corr_zero.iloc[i, j] = 0
```
short-circuits on `np.isnan(lo)`, leaving `corr_zero = 1`. This claims "the CI does NOT contain zero" (i.e., significant correlation) when in reality there is no correlation at all.

**The deprecated code has the same behavior** (`cria_functions.py:624`), so this is matched behavior. However, it is semantically wrong.

**Recommendation**: After the `pearsonr_ci` call, add:
```python
if np.isnan(r):
    corr_zero.iloc[i, j] = 0
```

## F3 Detail: Hardcoded Reference Path

**Evidence**: `_compute_correlation` at line 418 defaults to `reference_path: str = "data/cria_data_reference.xlsx"`. The project has a centralized path at `src/config/paths.py:89` (`Paths.reference_data`). The hardcoded relative path is cwd-dependent and will fail if the script is run from a different directory.

**Impact**: Low in practice (production scripts run from project root), but inconsistent with the project's path management pattern.

**Recommendation**: Import and use `Paths().reference_data` or accept the path as a parameter from the caller.

---

## Statistical Correctness

| Check | Result |
|-------|--------|
| `pearsonr_ci` Fisher z-transformation formula | CORRECT -- matches `cria_functions.py:542-571` |
| Bug fix: valid pair count vs raw array length | CORRECT improvement over deprecated code |
| Significance flag logic (`lo < 0 < hi`) | CORRECT for non-degenerate cases, matches deprecated line 624 |
| `arctanh(1.0)` on diagonal | Produces `inf`, but `tanh(inf)=1.0` -- functionally correct |
| `_compute_lowest_indicators` argsort algorithm | CORRECT -- matches deprecated `np.argsort(df_scores.values, axis=1)[:, :n_cols_large]` at line 144 |
| NaN sort order in argsort | NaN sorts to end (least problematic) -- correct prioritization |
| Pop change orientation | Ascending labels (intentional change from deprecated reversed labels) |
| Calibration impact | Correlation/lowest_ind are additive outputs, do not affect CRCI scores; pop change reversal changes bin assignments but not z-scores or aggregate |
| Center-scaling bias | Not affected -- binning auto-select unchanged |
| Bin counts (county=5, tract=7) | Unchanged and correct |

## Domain Compliance

| Special Case | Status |
|--------------|--------|
| Connecticut CBP 2022 | Not affected -- `_clean_indicators` unchanged |
| Puerto Rico Limited English | Not affected -- `_clean_indicators` unchanged |
| Population Change subset z-scores | Not affected -- `calc_z_scores` unchanged |
| EAVS -88 handling | Not affected |
| ARDA POP column | Not affected |

## Test Quality

| Check | Result |
|-------|--------|
| Tests exist | Yes -- `test_aggregator.py` (lowest_ind, correlation), `test_transformations.py` (pearsonr_ci, calc_full_corr_matrix), `test_binning.py` (pop change direction), `test_tribal_output.py` (output keys), `test_pipeline_smoke.py` (output keys) |
| Tests prove value correctness | Yes -- known-answer tests for lowest_ind, directional checks for pop change, statistical value checks for correlation |
| Edge case coverage | Partial -- missing empty DataFrame (F1), all-NaN column significance (F2), n=3 pearsonr_ci |
| Mock appropriateness | Good -- reference Excel mocked for correlation tests, no over-mocking |
| Regression guards | Present in `test_tribal_output.py` and `test_pipeline_smoke.py` for new output keys |

### Test Coverage Gaps

- No test for `_compute_lowest_indicators` with empty DataFrame (would catch F1)
- No test for `corr_zero` with all-NaN or constant columns (would catch F2)
- No test for `_compute_correlation` with malformed reference Excel (partially covered -- nonexistent path tested)
- No test for `pearsonr_ci` with exactly `n=3` valid pairs (produces `se=inf`, CI=[-1,1])

## Bias Check

| Bias | Status | Finding |
|------|--------|---------|
| Confirmation bias | Checked | Actively tested disconfirming evidence (empty DataFrames, NaN columns, constant columns). Found F1 and F2. |
| Selection bias | Checked | Test data uses realistic distributions (exponential for pop change, uniform for percentiles). |
| Survivorship bias | Checked | Examined fallback paths (missing file, n<3 guard, empty DataFrame). Found F1 through failure testing. |
| Anchoring bias | Not applicable | No method selection decisions to review. |
| Automation bias | Not applicable | No automated selection being reviewed. |

---

## Verdict: PASS WITH CONCERNS

### Must-fix before production use
- **F1**: Guard `_compute_lowest_indicators` against empty DataFrame

### Should-fix (not blocking)
- **F2**: Set `corr_zero = 0` when `r` is NaN (matches semantic intent)
- **F3**: Use centralized `Paths.reference_data` instead of hardcoded relative path

### Accepted (no action needed)
- **F4, F5**: RuntimeWarnings are functionally correct; suppress with `np.errstate` if desired
- **F6**: Pre-existing `save_to_excel` mutation, not introduced by these changes
- **F7**: Intentional column rename from `_perc` to `_score`
- **F8**: Intentional pop change direction reversal from deprecated behavior
