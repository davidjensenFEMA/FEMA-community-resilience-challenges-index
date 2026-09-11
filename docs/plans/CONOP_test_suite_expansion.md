# CONOP: Test Suite Expansion — Shift-Left Quality Defense

**Classification**: UNCLASSIFIED
**DTG**: 24 FEB 2026
**Status**: COMPLETE — Executed 24 FEB 2026, 353 tests passing, 81% coverage
**References**: `config/project.yaml`, `config/indicators.yaml`, `tests/conftest.py`, `pytest.ini`, `docs/design/testing_guide.md`

---

## I. SITUATION

### Current Test Landscape

The CRIA project (v1.0.0, production-ready) has **147 tests** (132 unit, 15 integration) organized across 9 test files. All tests pass. A 300-second per-test timeout is enforced (incident-driven, 2025-12-22). Total test code: ~4,100 lines.

**Well-Tested Modules:**

| Module | Test File | Tests | Quality |
|--------|-----------|-------|---------|
| `src/db/models.py` | `test_db_models.py` | ~40 | Constraints, cascades, relationships |
| `src/db/repositories.py` | `test_repositories.py` | ~50 | CRUD, bulk ops, upserts, queries |
| `src/api/base_client.py` | `test_base_client.py` | 13 | Retry, timeout, session, errors |
| `src/api/census_client.py` | `test_census_client.py` | 12 | URL building, data parsing, missing codes |
| `src/core/binning.py` | `test_binning.py` | 24 | Strategies, NaN, auto-select, metadata |
| `src/core/aggregator.py` | `test_aggregator.py` | 24 | Init, clean, CT CBP, PR English, pipeline |

**CRITICAL GAPS (zero tests):**

| Module | LOC | Risk | What's Untested |
|--------|-----|------|-----------------|
| `src/core/indicators.py` | 503 | **CRITICAL** | 22 indicator formulas, 5 function types, NaN propagation |
| `src/core/transformations.py` | 428 | **CRITICAL** | `clean_series`, `calc_z_scores`, `normalize_to_range`, 7 other functions |
| `src/core/data_puller.py` | 576 | **HIGH** | API orchestration, source dispatch, post-processing |
| `src/api/cbp_client.py` | 204 | **HIGH** | URL building, NAICS queries, CT zero handling |
| `src/api/external_clients.py` | 352 | **HIGH** | EAVS ZIP extraction, ARDA year-specific POP, POP year clamping |
| `src/config/settings.py` | 183 | **MEDIUM** | Pydantic validation, year bounds, property methods |
| `src/config/paths.py` | 264 | **MEDIUM** | Path resolution, directory auto-creation |

**Missing Test Categories:**
- No **smoke tests** (thin E2E "does the pipeline crash?")
- No **calibration/regression tests** (assert known baselines haven't drifted)
- No **known-answer tests** for any of the 22 indicator formulas
- No **property-based tests** (`hypothesis` not installed)
- No **year-over-year comparison** validation
- No `smoke` or `calibration` pytest markers registered

### Legacy Context

The deprecated system (`deprecated/old_scripts/`) had **zero tests**. Validation was entirely manual (run pipeline, inspect Excel output). The new OOP architecture was designed for testability but test coverage was front-loaded on infrastructure (DB, API clients) and has not yet reached the core calculation logic where the highest risk resides.

### Key Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Indicator formula bug undetected | **HIGH** | Wrong resilience scores for 3,200+ counties | Known-answer tests with hand-calculated values |
| `clean_series` replacement map drift | Medium | Dirty data leaks through pipeline | Boundary tests for every replacement value |
| `calc_z_scores` Pop Change special case regresses | Medium | Population Change scores contaminated | Dedicated test: subset vs full z-score behavior |
| Auto-select scoring regresses to raw (FisherJenks bias) | Medium | Method diversity lost | Test center-scaling produces different winners |
| API client parsing changes break silently | Medium | Bad data enters pipeline | Mock-based tests for all 5 clients |
| Test bloat without value (structure-only tests) | Medium | False confidence, slow CI | Quality audit in Phase 4 |

---

## II. MISSION

Build a comprehensive, layered test suite that closes all critical coverage gaps, adds smoke and calibration test categories, and establishes automated regression defense for the CRIA pipeline.

### Commander's Intent

Every indicator formula, every transformation function, and every API client must have tests that verify **correctness of values**, not merely structure. Failure modes must be tested before happy paths. The quality-auditor reviews the test suite itself before it is considered complete. The team will also deliver a clear recommendation on where the boundary lies between automated tests (pytest pass/fail) and analytical comparisons (scripts/reports).

### End State

**Test count**: 147 → ~300 tests across 4 categories (unit, integration, smoke, calibration).

**New test files:**

| File | Category | Target Tests | Tests Module |
|------|----------|-------------|--------------|
| `tests/unit/test_indicators.py` | Unit | 35-45 | `src/core/indicators.py` |
| `tests/unit/test_transformations.py` | Unit | 25-35 | `src/core/transformations.py` |
| `tests/unit/test_data_puller.py` | Unit | 15-20 | `src/core/data_puller.py` |
| `tests/unit/test_cbp_client.py` | Unit | 10-15 | `src/api/cbp_client.py` |
| `tests/unit/test_external_clients.py` | Unit | 15-20 | `src/api/external_clients.py` |
| `tests/unit/test_settings.py` | Unit | 8-12 | `src/config/settings.py` |
| `tests/unit/test_paths.py` | Unit | 8-10 | `src/config/paths.py` |
| `tests/smoke/test_pipeline_smoke.py` | Smoke | 5-8 | End-to-end pipeline |
| `tests/calibration/test_calibration.py` | Calibration | 10-15 | Baseline assertions |

**New pytest markers**: `smoke`, `calibration`

**New directories**: `tests/smoke/`, `tests/calibration/`

---

## III. EXECUTION

### Phase 0: Reconnaissance

**Purpose**: Review existing tests, design documents, deprecated code, and indicator definitions. Catalog patterns, extract known-answer data, build fixture inventory.

**Agent**: quality-auditor (read-only)

**Tasks:**

1. **Catalog existing test patterns** across all 9 test files:
   - Fixture patterns from `tests/conftest.py`
   - Mock patterns (census client: `@patch("src.api.census_client.BaseAPIClient.get")`)
   - DataFrame assertion patterns (`pd.testing.assert_series_equal`, `pytest.approx()`)
   - Class-based test organization (`class Test*`)

2. **Extract known-answer test data** from:
   - `config/indicators.yaml` — all 22 indicator formulas with column references
   - `data/cria_data_reference.xlsx` — Status sheet for authoritative column names
   - `config/project.yaml` — calibration targets (0.94 county, 1.0 tract)

3. **Hand-calculate expected values** for representative indicators (see Annex A)

4. **Review deprecated code** for test-relevant patterns:
   - `deprecated/old_scripts/cria_create_indicators.py` — original formula implementations
   - `deprecated/old_scripts/cria_functions.py` — original transformation functions
   - `deprecated/old_scripts/cria_create_aggregate_indicator.py` — aggregation flow

5. **Deliver recon report**:
   - Fixture inventory (what exists, what gaps)
   - Mock pattern recommendations
   - Known-answer reference table
   - Recommended fixture additions to `tests/conftest.py`

**Decision Authority**: None required — read-only recon.

---

### Phase 1: Close Critical Unit Test Gaps

**Purpose**: Write unit tests for all zero-coverage modules. Priority: indicators.py (highest risk) → transformations.py → API clients → config.

**Agents**: statistical-tester (primary writer), cria-analyst (domain knowledge for formulas), data-engineer (API client knowledge)

#### Phase 1a: `tests/unit/test_indicators.py` (~40 tests)

**Agent**: statistical-tester (with cria-analyst consulting on formula verification)
**Target**: `src/core/indicators.py` — `IndicatorCalculator` class

```
class TestParseNumerator:
    test_single_column_string           # "DP04_0014E" → ["DP04_0014E"]
    test_multi_column_string            # "S1501_C01_007E, S1501_C01_008E" → list of 2
    test_numeric_naics_code             # "813410" → ["813410"]
    test_whitespace_handling            # " DP04_0014E , DP04_0001E " → stripped

class TestDivideFunction:
    test_known_answer_mobile_homes      # 150 / 1000 = 0.15
    test_known_answer_education_multi   # (80 + 20) / 500 = 0.20
    test_known_answer_scalar_denom      # GINI: 0.45 / 1 = 0.45
    test_zero_denominator               # returns 0 (not NaN — per code)
    test_nan_numerator_returns_nan      # missing mask propagates
    test_multiple_rows_vectorized       # 4-row DataFrame
    test_empty_dataframe                # graceful handling

class TestMaxFunction:
    test_known_answer_econ_diversity    # max(5000,3000) / 10000 = 0.50
    test_all_nan_numerators             # uses .all() missing mask
    test_single_column_max              # max of 1 col = that col
    test_zero_denominator

class TestMeanFunction:
    test_known_answer_pop_change        # mean(100,120,80) / 50000 = 0.002
    test_year_column_construction       # NETMIG{year} columns
    test_missing_netmig_columns         # graceful fallback
    test_subset_years_available         # only existing cols used
    test_zero_denominator

class TestDivideScalarFunction:
    test_known_answer_civil_org         # (5 / 50000) * 10000 = 1.0
    test_known_answer_hospitals         # (3 / 50000) * 10000 = 0.6
    test_known_answer_medical           # (500 / 50000) * 1000 = 10.0
    test_nan_handling
    test_zero_denominator

class TestReverseDivideFunction:
    test_known_answer_communications    # (1000 - 800) / 1000 = 0.20
    test_known_answer_religion          # (50000 - 30000) / 50000 = 0.40
    test_denom_less_than_numer_capped   # capped at 0 (not negative)
    test_nan_handling
    test_zero_denominator

class TestCalculateAllIndicators:
    test_dispatches_to_correct_function # mock _calculate_indicator, verify dispatch
    test_unknown_function_returns_empty # graceful fallback
    test_exception_returns_nan_column   # catches and continues
    test_output_shape_matches_reference # len(reference) columns
    test_index_preserved
```

**Assertion rules:**
- `pytest.approx()` for all float comparisons
- `pd.isna()` explicitly (never `== np.nan`)
- Test NaN propagation logic: `.any()` vs `.all()` differs between `_max_function` and `_divide_function` — both behaviors are intentional

#### Phase 1b: `tests/unit/test_transformations.py` (~30 tests)

**Agent**: statistical-tester
**Target**: `src/core/transformations.py` — 10 standalone functions

```
class TestCleanSeries:
    test_excel_errors_replaced          # "#DIV/0!", "#VALUE!" → None
    test_null_representations           # "null", "<Null>", "-" → None
    test_census_missing_code            # "-666666666" → None
    test_cbp_top_coding                 # "250,000+" → 250000
    test_cbp_bottom_coding              # "2,500-" → 2500
    test_conversion_to_float            # output dtype is float64
    test_impute_with_mean               # NaN replaced with series mean
    test_impute_with_custom_value       # NaN replaced with specific value
    test_no_impute_preserves_nan        # impute=False keeps NaN
    test_deep_copy                      # original series unchanged

class TestCalcZScores:
    test_series_mean_near_zero          # z-scored series centered
    test_series_std_near_one            # z-scored series unit variance
    test_zero_std_returns_zeros         # constant series → all 0
    test_dataframe_regular_features     # mean ~0 for non-PopChange
    test_population_change_not_centered # /std only, no -mean
    test_sub_index_uses_subset_stats    # means/stds from subset only
    test_sub_index_applied_to_full      # all rows standardized
    test_known_values                   # [10,20,30] → specific z-scores

class TestNormalizeToRange:
    test_default_zero_to_one            # min=0, max=1
    test_custom_range                   # min=0, max=100
    test_all_same_returns_min           # constant series → min_val
    test_known_values                   # [10,20,30,40,50] → [0,0.25,0.5,0.75,1.0]

class TestMultRound:
    test_round_up                       # 23, base=5 → 25
    test_round_down                     # 22, base=5 → 20
    test_exact_multiple                 # 25, base=5 → 25

class TestCalcCorrMatrix:
    test_perfect_positive               # A=[1,2,3], B=[2,4,6]
    test_perfect_negative
    test_with_nan_values

class TestCalcPairwiseCorrelation:
    test_perfect_correlation            # (1.0, very_small_p)
    test_too_few_observations           # < 3 valid → (nan, nan)

class TestPercentileRank:
    test_known_values                   # [10,20,30,40,50] → [20,40,60,80,100]
    test_handles_nan
```

#### Phase 1c: `tests/unit/test_cbp_client.py` (~12 tests)

**Agent**: data-engineer
**Target**: `src/api/cbp_client.py` — `CBPClient` class

```
class TestCBPClient:
    test_initialization_defaults        # uses settings values
    test_build_cbp_url_basic            # correct URL structure
    test_build_cbp_url_naics_in_query   # NAICS{year} parameter

class TestFetchCBPData:
    test_basic_fetch                    # mock JSON → DataFrame
    test_column_renamed                 # ESTAB → NAICS code
    test_geo_id_as_index                # set_index("GEO_ID")
    test_fill_missing_true              # NaN → 0
    test_fill_missing_false             # NaN preserved
    test_numeric_conversion             # string ESTAB → numeric

class TestFetchMultipleNaics:
    test_multiple_codes_merged          # two codes, outer join
    test_one_code_fails_gracefully      # empty DataFrame for failed
    test_fill_missing_across_codes      # remaining NaN filled
```

#### Phase 1d: `tests/unit/test_external_clients.py` (~18 tests)

**Agent**: data-engineer
**Target**: `src/api/external_clients.py` — `EAVSClient`, `ARDAClient`, `POPClient`

```
class TestEAVSClient:
    test_fetch_parses_zip               # mock ZIP containing CSV
    test_fetch_fallback_direct_csv      # BadZipFile → CSV fallback
    test_special_values                 # -88 → 0, -99 → NaN
    test_county_merge                   # counties_ref merge logic
    test_geo_id_index                   # set_index("GEO_ID")

class TestARDAClient:
    test_fetch_2020                     # mock Excel, verify TOTADH/POP
    test_fetch_2010                     # local file path
    test_unsupported_year_raises        # year=2015 → error
    test_pop_alias_created              # POP column alongside POP2020
    test_geo_id_format                  # "0500000US" + FIPS

class TestPOPClient:
    test_fetch_basic                    # mock CSV → DataFrame
    test_year_clamping_to_decade        # years before decade excluded
    test_default_years_calculation      # 5 years back from pop_year
    test_no_valid_years_raises          # all clamped out → error
    test_geo_id_construction            # STATE+COUNTY → "0500000US01001"
    test_csv_encoding                   # ISO-8859-1 handling
```

**Key mock patterns:**
- EAVSClient: Create `zipfile.ZipFile` in memory with `io.BytesIO`
- ARDAClient: Mock `pd.read_excel`
- POPClient: Mock `BaseAPIClient.get` returning CSV content

#### Phase 1e: `tests/unit/test_data_puller.py` (~18 tests)

**Agent**: statistical-tester (with data-engineer consulting)
**Target**: `src/core/data_puller.py` — `DataPuller` class

Mock all 5 API clients and reference/years loading. Test orchestration, not API calls.

```
class TestDataPullerInit:
    test_initialization_sets_geography
    test_initialization_creates_clients

class TestPullAllData:
    test_dispatches_acs_for_acs_source
    test_dispatches_cbp_for_cbp_source
    test_dispatches_eavs_for_eavs_source
    test_dispatches_arda_for_arda_source
    test_dispatches_pop_for_pop_source
    test_unknown_source_skipped         # warning logged, continues
    test_exception_in_pull_continues    # other indicators still pulled
    test_duplicate_columns_dropped

class TestPostProcessData:
    test_invalid_index_dropped          # NaN indices removed
    test_cbp_missing_filled_zero
    test_pr_limited_english_nan         # state=72, Limited English → NaN
    test_pr_exclusion_geography_gate    # only state/county/tract, not tribal
```

#### Phase 1f: `tests/unit/test_settings.py` and `tests/unit/test_paths.py` (~18 tests)

**Agent**: data-engineer

**`test_settings.py`:**
```
class TestSettings:
    test_default_values                 # all defaults match expectations
    test_year_validation_bounds         # ge=2010, le=2030
    test_years_dict_property            # returns all 6 years
    test_is_docker_property             # "postgres" in URL
    test_geography_validation           # only state/county/tract/tribal
    test_log_level_validation
    test_pipeline_timeout_bounds        # ge=5, le=1440
```

**`test_paths.py`:**
```
class TestPathConfig:
    test_root_resolves_to_project
    test_data_creates_directory
    test_output_creates_directory
    test_reference_file_path
    test_get_output_file_basic
    test_get_output_file_with_geo_year
    test_get_output_file_subfolder
    test_verify_paths_returns_dict
```

---

### Phase 2: Smoke Tests and Integration Enhancements

**Purpose**: Add thin E2E smoke tests and fill integration gaps. Smoke tests prove "does not crash" — they do NOT validate values.

**Agents**: data-engineer (smoke infrastructure + tests), statistical-tester (integration tests)

#### Phase 2a: Infrastructure

**Agent**: data-engineer

1. Create `tests/smoke/__init__.py`
2. Create `tests/calibration/__init__.py`
3. Register new markers in `pytest.ini`:
   ```
   smoke: Thin end-to-end pipeline sanity checks (mocked APIs, fast)
   calibration: Baseline regression tests (run on-demand: pytest -m calibration)
   ```
4. Update `tests/conftest.py` `pytest_collection_modifyitems` to auto-mark:
   ```python
   elif 'smoke' in rel_path.parts:
       item.add_marker(pytest.mark.smoke)
   elif 'calibration' in rel_path.parts:
       item.add_marker(pytest.mark.calibration)
   ```

#### Phase 2b: `tests/smoke/test_pipeline_smoke.py` (~7 tests)

**Agent**: data-engineer

**Design**: Mock all external APIs. Synthetic data (3-5 rows). Assert "does not crash" and "output has expected shape". Each test < 5 seconds.

```
class TestPipelineSmokeCounty:
    test_indicator_calculation_no_crash
        # Mock DataPuller → synthetic source data
        # Run IndicatorCalculator.calculate_all_indicators()
        # Assert: result is DataFrame, >0 columns

    test_aggregation_no_crash
        # Feed synthetic indicators → AggregateIndicator.create_aggregate()
        # Assert: result dict has all expected keys

    test_full_pipeline_mock_no_crash
        # Mock all API clients
        # Run Calculator → Aggregator pipeline
        # Assert: final result has "agg", "bin_labels", "agg_meta"

    test_excel_export_no_crash
        # Pipeline → save_to_excel to tmp_path
        # Assert: file exists, has expected sheets

class TestPipelineSmokeTract:
    test_tract_7_bins_no_crash          # Same as county but bins=7

class TestPipelineSmokeTribal:
    test_tribal_acs_only_no_crash       # Non-ACS indicators NaN, still completes
```

#### Phase 2c: Additional Integration Tests (~5 tests)

**Agent**: statistical-tester

```
class TestCrossComponentIntegration:
    test_transformations_fed_into_aggregator
    test_calculator_output_compatible_with_aggregator
    test_binning_metadata_flows_to_excel
    test_clean_series_through_z_scores_through_aggregate
```

---

### Phase 3: Calibration/System Tests

**Purpose**: On-demand tests asserting known baselines haven't drifted. NOT run on every commit — run after major refactors, before production runs, or on explicit command.

**Agents**: cria-analyst (defines baselines), statistical-tester (writes tests)

#### Phase 3a: Calibration Fixture Data

**Agent**: cria-analyst

Create `tests/fixtures/calibration_data.py`:
- Synthetic county dataset (100 rows, all 22 indicator columns, realistic distributions)
- Synthetic reference DataFrame matching all 22 indicators
- Known-good baseline values (mean, std, bin distribution) for comparison

#### Phase 3b: `tests/calibration/test_calibration.py` (~12 tests)

**Agent**: statistical-tester (with cria-analyst providing baseline values)

**Design**: Use synthetic data with known properties. Assert statistical invariants with tolerance. No external APIs or production DB required.

```
class TestIndicatorFormulaCalibration:
    @pytest.mark.calibration
    test_all_22_indicators_produce_valid_ranges
    test_divide_indicators_bounded_zero_to_one
    test_divide_scalar_indicators_positive
    test_reverse_divide_bounded_zero_to_one

class TestAggregationCalibration:
    @pytest.mark.calibration
    test_county_cri_distribution_centered    # mean(CRI) near 0
    test_cria_percentile_spans_full_range    # min < 0.05, max > 0.95
    test_pop_change_subset_zscore_differs    # subset ≠ full method

class TestBinningCalibration:
    @pytest.mark.calibration
    test_county_5_bins_all_populated         # 200+ values → all bins used
    test_tract_7_bins_all_populated          # 500+ values → all bins used
    test_auto_select_not_always_fisher_jenks # center-scaling produces diversity

class TestDomainSpecialCases:
    @pytest.mark.calibration
    test_ct_cbp_propagates_nan_through_pipeline
    test_pr_limited_english_excluded_through_pipeline
```

---

### Phase 4: Quality Audit of the New Test Suite

**Purpose**: Adversarial review of every test written in Phases 1-3. This phase is MANDATORY.

**Agent**: quality-auditor (read-only)

**Audit Checklist:**

1. **Value Correctness** — For every known-answer test:
   - [ ] Expected value independently verifiable (hand-calculated, not copy-pasted from code output)?
   - [ ] Uses `pytest.approx()` for floats?
   - [ ] Would FAIL if the formula were wrong?

2. **Failure Mode Coverage** — For every module:
   - [ ] Empty DataFrame tested?
   - [ ] NaN input tested?
   - [ ] Zero denominator tested?
   - [ ] Missing column tested?

3. **Anti-Tautology** — For every assertion:
   - [ ] Testing the code's logic, not reimplementing it?
   - [ ] Would a mutation (changing `>` to `>=`) cause failure?

4. **Mock Appropriateness**:
   - [ ] External APIs: mocked (correct)
   - [ ] Internal logic: NOT mocked (mocking internal functions hides bugs)
   - [ ] Database: session-scoped fixtures with rollback

5. **Coverage Scan**:
   - [ ] Run `pytest --cov=src --cov-report=term-missing`
   - [ ] Identify remaining uncovered business logic branches
   - [ ] Prioritize: which uncovered branches contain calculation logic?

6. **Smoke Test Validity**:
   - [ ] Tests "does not crash" without being tautological?
   - [ ] Would catch real failures (import error, schema change)?

7. **Calibration Test Independence**:
   - [ ] Uses own data, not production DB state?
   - [ ] Can run in CI without external API access?

**Deliverable**: Formal audit report per quality-auditor format:
- Findings (CRITICAL/HIGH/MEDIUM/LOW)
- Test Quality assessment per module
- Recommended fixes
- Verdict: PASS / PASS WITH CONCERNS / FAIL

---

## IV. AGENT TASK ASSIGNMENT

### Team Composition

| Agent | Role | Write Scope | Phases |
|-------|------|-------------|--------|
| **quality-auditor** | Recon + final audit | Read-only | 0, 4 |
| **statistical-tester** | Primary test writer | `tests/` only | 1a, 1b, 1e, 2c, 3b |
| **data-engineer** | API/config tests, smoke infra | `tests/`, `pytest.ini` | 1c, 1d, 1f, 2a, 2b |
| **cria-analyst** | Domain knowledge, baselines | `tests/fixtures/` | 1a (consult), 3a, 3b (consult) |

### Dependency Chain

```
Phase 0 (quality-auditor: recon)
    │
    ▼
Phase 1a-1f (statistical-tester + data-engineer) ← PARALLEL
    │
    ▼
Phase 2a (data-engineer: smoke/calibration infra)
    │
    ▼
Phase 2b-2c + Phase 3a-3b ← PARALLEL
    │
    ▼
Phase 4 (quality-auditor: audit) → Fix findings → Re-audit
```

### Coordination Protocol

- **Phase 0**: quality-auditor delivers recon report. All agents read it before Phase 1.
- **Phase 1**: statistical-tester and data-engineer work in parallel on different files:
  - statistical-tester: `test_indicators.py`, `test_transformations.py`, `test_data_puller.py`
  - data-engineer: `test_cbp_client.py`, `test_external_clients.py`, `test_settings.py`, `test_paths.py`
- **Phase 2-3**: data-engineer creates infrastructure. Tests in 2b/2c/3a/3b can parallelize.
- **Phase 4**: quality-auditor reviews all work. statistical-tester fixes audit findings.

---

## V. NEW PYTEST MARKERS AND RUN COMMANDS

### Markers to Register in `pytest.ini`

```ini
markers =
    unit: Fast unit tests (no external dependencies)
    integration: Integration tests (database, API calls)
    slow: Tests that take > 10 seconds
    requires_db: Tests that require database connection
    requires_api: Tests that require external API calls
    requires_docker: Tests that require Docker
    smoke: Thin end-to-end pipeline sanity checks (mocked APIs, fast)
    calibration: Baseline regression tests (run on-demand: pytest -m calibration)
```

### Recommended Run Commands

```bash
# Standard development (fast):
pytest -m unit

# Pre-commit (unit + smoke):
pytest -m "unit or smoke"

# Full CI (everything except on-demand calibration):
pytest -m "not calibration"

# Post-refactor / pre-production validation:
pytest -m calibration

# Everything:
pytest
```

---

## VI. TEST vs. ANALYTICAL COMPARISON BOUNDARY

### The Rule

**If you can write down an expected value (or a tight tolerance band) before running the test, it belongs in pytest.**

**If the answer requires domain judgment, visual inspection, or comparison to external baseline data that lives outside the repository, it belongs in an analytical script.**

### Classification

| Category | Belongs In | Rationale |
|----------|-----------|-----------|
| Indicator formula correctness | `pytest` (unit) | Deterministic. Known-answer. Must never regress. |
| Transformation function correctness | `pytest` (unit) | Pure functions. Easy to test. |
| API client parsing | `pytest` (unit) | Deterministic given mock input. |
| "Does the pipeline crash?" | `pytest` (smoke) | Binary pass/fail. |
| Bin count correctness (5 vs 7) | `pytest` (unit) | Deterministic configuration. |
| CT CBP / PR Limited English handling | `pytest` (unit + calibration) | Deterministic special cases. |
| Auto-select scoring not biased | `pytest` (calibration) | Statistical property, testable with synthetic data. |
| CRI distribution centered near 0 | `pytest` (calibration) | Statistical invariant, wide tolerance. |
| **Calibration correlation 0.94** | **Analytical** | Requires real production data. Exact value depends on data vintage. |
| **Year-over-year county stability** | **Analytical** | Requires multiple production runs. Trends, not pass/fail. |
| **"Are CBP 2023 values plausible?"** | **Analytical** | Judgment call. No deterministic threshold. |
| **"Do tribal outputs match historical?"** | **Analytical** | Requires deprecated output files. Domain judgment. |
| **Bin distribution quality** | **Analytical** | "Are bins roughly balanced?" is subjective. |

### Recommendation: Future Analytical Scripts

Not part of this CONOP, but recommended for future work:

```
scripts/analysis/
    compare_year_over_year.py       # Compare county outputs across years
    validate_calibration.py          # Correlation against baseline Excel
    inspect_bin_distributions.py     # Visualization of bin quality
    tribal_comparison.py             # Compare against deprecated tribal output
```

These scripts should produce reports (markdown or HTML) in `data/output/reports/`, not pytest pass/fail results.

---

## VII. SUCCESS CRITERIA

- [ ] All critical gap modules have unit tests (`indicators.py`, `transformations.py`, `data_puller.py`, `cbp_client.py`, `external_clients.py`, `settings.py`, `paths.py`)
- [ ] Total test count: 280+ (up from 147)
- [ ] Every indicator function type (`divide`, `max`, `mean`, `divide_scalar`, `reverse_divide`) has at least 1 known-answer test with hand-calculated expected value
- [ ] Every transformation function has at least 2 tests (happy path + edge case)
- [ ] All 5 API clients have mock-based tests
- [ ] Smoke tests cover county, tract, and tribal geography levels
- [ ] Calibration tests cover: indicator ranges, CRI distribution, bin population, auto-select diversity, CT CBP, PR Limited English
- [ ] `pytest -m "unit or smoke"` completes in under 30 seconds
- [ ] `pytest -m calibration` completes in under 60 seconds
- [ ] `pytest --cov=src` shows > 70% line coverage (up from ~40%)
- [ ] Quality auditor verdict: PASS or PASS WITH CONCERNS
- [ ] Zero tests depend on external API calls or production database
- [ ] All tests pass: `pytest` returns exit code 0

---

## ANNEXES

### Annex A: Indicator Formula Reference (for Known-Answer Tests)

All 22 indicators with hand-calculated expected values. These are the **authoritative test inputs** for Phase 1a.

| # | Indicator | Function | Formula | Test Input | Expected Output |
|---|-----------|----------|---------|------------|-----------------|
| 1 | Mobile Homes | divide | `DP04_0014E / DP04_0001E` | 150 / 1000 | 0.15 |
| 2 | Owner Occupied | divide | `DP04_0046E / DP04_0001E` | 600 / 1000 | 0.60 |
| 3 | Education | divide | `(S1501_C01_007E + S1501_C01_008E) / S1501_C01_006E` | (80+20) / 500 | 0.20 |
| 4 | No Vehicle | divide | `B08201_002E / B08201_001E` | 50 / 1000 | 0.05 |
| 5 | Age | divide | `S0101_C01_030E / S0101_C01_001E` | 200 / 1000 | 0.20 |
| 6 | Disability | divide | `S1810_C02_001E / S1810_C01_001E` | 130 / 1000 | 0.13 |
| 7 | Limited English | divide | `S1602_C03_001E / S1602_C01_001E` | 40 / 1000 | 0.04 |
| 8 | Single Parent | divide | `(B09005_004E + B09005_005E) / B09005_001E` | (50+30) / 500 | 0.16 |
| 9 | Low Access to Comms | reverse_divide | `(S2801_C01_001E - S2801_C01_005E) / S2801_C01_001E` | (1000-800) / 1000 | 0.20 |
| 10 | Inactive Voter | divide | `A1c / A1a` | 500 / 5000 | 0.10 |
| 11 | Civil Org | divide_scalar | `(813410 / S0101_C01_001E) * rate * 1000` | (5/50000)*10000 | 1.0 |
| 12 | Population Change | mean | `mean(NETMIG{years}) / S0101_C01_001E` | mean(100,120,80) / 50000 | 0.002 |
| 13 | Religion | reverse_divide | `(POP - TOTADH) / POP` | (50000-30000) / 50000 | 0.40 |
| 14 | Unemployment | divide | `DP03_0005E / DP03_0003E` | 500 / 10000 | 0.05 |
| 15 | Unemployed Women | reverse_divide | `(DP03_0012E - DP03_0013E) / DP03_0012E` | (5000-2500) / 5000 | 0.50 |
| 16 | Median Income | divide | `S1903_C03_001E / 1` | 55000 / 1 | 55000.0 |
| 17 | GINI | divide | `B19083_001E / 1` | 0.45 / 1 | 0.45 |
| 18 | Lack of Econ Diversity | max | `max(DP03_0033E..DP03_0045E) / DP03_0032E` | max(5000,3000,...) / 10000 | 0.50 |
| 19 | Poverty | divide | `S1701_C02_001E / S1701_C01_001E` | 150 / 1000 | 0.15 |
| 20 | Hospitals | divide_scalar | `(622110 / S0101_C01_001E) * rate * 1000` | (3/50000)*10000 | 0.60 |
| 21 | Medical | divide_scalar | `(S2401_C01_016E / S0101_C01_001E) * rate * 1000` | (500/50000)*1000 | 10.0 |
| 22 | Uninsured Pop | divide | `S2701_C04_001E / S2701_C01_001E` | 80 / 1000 | 0.08 |

**Note on scalars**: `divide_scalar` formula is `(numerator / denominator) * rate * 1000`. Civil Org/Hospitals have rate=10.0 → scalar=10000. Medical has rate=1.0 → scalar=1000.

### Annex B: Existing Fixture Inventory

**Current fixtures** (from `tests/conftest.py`):

| Fixture | Scope | Purpose |
|---------|-------|---------|
| `test_database_url` | session | PostgreSQL test URL |
| `test_engine` | session | SQLAlchemy engine with create/drop |
| `db_session` | function | Isolated session with rollback |
| `sample_reference_data` | function | 3 indicators (Poverty, GINI, Unemployment) |
| `sample_acs_data` | function | 2 counties (01001, 01003) |
| `sample_geography_data` | function | 2 county metadata records |
| `sample_years` | function | Year config dict (6 sources) |
| `mock_census_api_response` | function | Census JSON array |
| `temp_output_dir` | function | tmp_path for output |
| `temp_data_dir` | function | tmp_path for data |

**New fixtures needed:**

| Fixture | Purpose | Added By |
|---------|---------|----------|
| `indicator_source_data` | DataFrame with columns for all 5 function types | statistical-tester |
| `full_reference_data` | All 22 indicators (synthetic but realistic) | cria-analyst |
| `cbp_mock_response` | CBP API JSON response (including CT zeros) | data-engineer |
| `eavs_mock_zip` | EAVS ZIP file bytes for extraction test | data-engineer |
| `pop_mock_csv` | POP CSV content | data-engineer |
| `arda_mock_excel` | ARDA Excel mock data | data-engineer |
| `calibration_county_data` | 100-row synthetic county dataset, all 22 indicators | cria-analyst |

### Annex C: Estimated Test Count by File

| File | Existing | New | Total |
|------|----------|-----|-------|
| `test_db_models.py` | ~40 | 0 | ~40 |
| `test_repositories.py` | ~50 | 0 | ~50 |
| `test_base_client.py` | 13 | 0 | 13 |
| `test_census_client.py` | 12 | 0 | 12 |
| `test_binning.py` | 24 | 0 | 24 |
| `test_aggregator.py` | 24 | 0 | 24 |
| `test_full_workflow.py` | ~10 | 0 | ~10 |
| `test_database_workflow.py` | ~4 | 0 | ~4 |
| `test_phase6_pipeline.py` | ~3 | 0 | ~3 |
| **test_indicators.py** | 0 | **40** | **40** |
| **test_transformations.py** | 0 | **30** | **30** |
| **test_data_puller.py** | 0 | **18** | **18** |
| **test_cbp_client.py** | 0 | **12** | **12** |
| **test_external_clients.py** | 0 | **18** | **18** |
| **test_settings.py** | 0 | **10** | **10** |
| **test_paths.py** | 0 | **8** | **8** |
| **test_pipeline_smoke.py** | 0 | **7** | **7** |
| **test_calibration.py** | 0 | **12** | **12** |
| **TOTAL** | **147** | **~155** | **~302** |

### Annex D: Escalation Criteria

Pause and report to commander if:
1. Quality auditor issues CRITICAL finding that requires production code changes
2. Known-answer tests reveal formula bugs in production code (`indicators.py`)
3. Smoke tests reveal import/dependency issues blocking test execution
4. Calibration test design requires real production data not available in repository
5. Test count exceeds 350 (scope creep — reassess value)
6. Any agent recommends changes to `src/` production code to fix issues found during testing

### Annex E: Test Directory Structure (End State)

```
tests/
├── conftest.py                         # Shared fixtures (extended)
├── __init__.py
├── fixtures/
│   ├── __init__.py
│   └── calibration_data.py             # NEW: synthetic calibration data
├── unit/
│   ├── __init__.py
│   ├── test_base_client.py             # (existing)
│   ├── test_census_client.py           # (existing)
│   ├── test_db_models.py              # (existing)
│   ├── test_repositories.py           # (existing)
│   ├── test_aggregator.py            # (existing)
│   ├── test_binning.py               # (existing)
│   ├── test_indicators.py            # NEW
│   ├── test_transformations.py        # NEW
│   ├── test_data_puller.py           # NEW
│   ├── test_cbp_client.py            # NEW
│   ├── test_external_clients.py       # NEW
│   ├── test_settings.py              # NEW
│   └── test_paths.py                 # NEW
├── integration/
│   ├── __init__.py
│   ├── test_full_workflow.py          # (existing, extended)
│   ├── test_database_workflow.py      # (existing)
│   └── test_phase6_pipeline.py        # (existing)
├── smoke/
│   ├── __init__.py                    # NEW
│   └── test_pipeline_smoke.py         # NEW
└── calibration/
    ├── __init__.py                    # NEW
    └── test_calibration.py            # NEW
```
