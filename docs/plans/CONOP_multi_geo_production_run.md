# CONOP: Multi-Geography CRIA Production Run with CBP 2023

**Classification**: UNCLASSIFIED
**DTG**: 24 FEB 2026
**References**: `config/project.yaml`, `docs/design/pipeline_guide.md`, `.env`

---

## I. SITUATION

### Current State
The CRIA pipeline is production-ready with validated county outputs for 2021, 2022, and 2024. The current `.env` configures ACS_YEAR=2024 and CBP_YEAR=2022. Tract data has NOT been pulled for 2022-2024. Tribal has not been run through the current production pipeline, but was handled historically by a dedicated script (`deprecated/old_scripts/cria_create_indicators_tribal.py`) that dropped all non-ACS indicators and used 5 bins.

### Data Year Mapping (Baseline from `.env`)
```
label        year_2021  year_2022  year_2023  year_2024
acs          2021       2021       2022       2023
cbp          2020       2020       2021       2021
naics        2017       2017       2017       2017
pop          2021       2021       2022       2022
asarb        2020       2020       2020       2020
```

### Modification from Baseline
CBP year for the 2024 run is changed to **2023** per commander's intent. The current `.env` already uses CBP_YEAR=2022 (exceeding baseline), so this is an incremental advance. CBP 2023 is a **hard requirement** — if unavailable, the operation is paused for commander's guidance. There is no fallback to CBP 2022.

### Tribal Historical Context
Analysis of deprecated code (`deprecated/old_scripts/cria_create_indicators_tribal.py`) reveals:
- **Non-ACS indicators were dropped**: CBP, EAVS, ARDA, POP data does not exist at tribal geography level. The old pipeline dropped these columns before binning (line 95: `ref.loc[ref["Source"] != "ACS", "Indicator"]`).
- **5 bins** used for tribal (same as county, not 7 like tract).
- **Zero-population tribes** were excluded from binning but kept in the output structure.
- **Puerto Rico Limited English exclusion** was skipped for tribal (no PR in tribal areas).
- **Connecticut CBP fix** was never applied to tribal (not relevant — no CBP data).
- **Binning exceptions**: Limited English and Medical used JenksCaspall exceptions for tribal.

The current production pipeline (`run_full_pipeline.py --geography tribal`) uses the Census ACS geography `american%20indian%20area/alaska%20native%20area/hawaiian%20home%20land:*`. The CBP client is hardcoded to `county:*` — it will pull county-level data that cannot join to tribal GEO_IDs, resulting in NaN for CBP indicators. This matches historical behavior. The team should review deprecated code for any additional tribal handling that should be replicated and provide recommendations on the old process.

### Key Assumptions
1. **CBP 2023 data is available** on the Census API (`api.census.gov/data/2023/cbp`). If unavailable: **ABORT and escalate to commander**.
2. **NAICS_YEAR=2017 remains valid** for CBP 2023 queries. If CBP 2023 requires NAICS 2022, escalate for guidance before updating.
3. **Connecticut CBP special case** applies to CBP 2023 (zero values → NaN). This logic is in `src/core/aggregator.py:183-198` but only fires when `geo_reference` is provided to `create_aggregate()`. Team must verify whether the standard pipeline passes this parameter.
4. Database (PostgreSQL on port 5433) is running and accessible.
5. Census API key is valid and rate limits are respected.

### Known Risks
| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| CBP 2023 not yet released | Medium | **Operation paused** | Verify API in Phase 0. ABORT if unavailable — no fallback. |
| NAICS 2017 codes invalid for CBP 2023 | Low-Medium | API returns empty/error | Test NAICS code in Phase 0. Escalate if change needed. |
| Tract timeout | Medium | Pipeline killed before completion | Set PIPELINE_TIMEOUT_MINUTES=240. Monitor. |
| DB duplicate key violations (2024) | High | Pipeline fails at DB write | Clear existing 2024 records in Phase 1 before fresh run. |
| CT CBP special case not firing | Medium | CT gets invalid CBP indicator values | Verify `geo_reference` parameter is passed. Spot-check CT in output. |
| Tribal non-ACS indicators as NaN | Expected | Reduced indicator count for tribal | Matches historical behavior. Document in output. |

---

## II. MISSION

Generate validated CRIA indicator outputs (both **database records** and **Excel workbooks**) for **county**, **tract**, and **tribal** geographies using current-year data (ACS 2024, CBP 2023, POP 2024), with comparison runs for years 2021-2023 at county level. Review all outputs for statistical correctness, domain compliance, and year-over-year consistency. The team will review deprecated code for historical tribal handling and provide recommendations on the old process.

### Commander's Intent
Produce a complete, audited set of CRIA outputs across all operational geography levels using the most current data available. CBP year is advanced to 2023 — this is a hard requirement with no fallback. Year-over-year county comparison provides trend validation and anomaly detection. All runs produce both DB records and Excel outputs. The quality-auditor reviews every output before it is considered final.

### End State
**Database**: Fresh records in PostgreSQL for all geography/year combinations below.
**Excel**: One workbook per geography/year in `data/output/`:

| Output File | Geography | Year | Data Sources |
|-------------|-----------|------|-------------|
| `cria_results_county_2024.xlsx` | County | 2024 | ACS 2024, CBP **2023**, POP 2024 |
| `cria_results_tract_2024.xlsx` | Tract | 2024 | ACS 2024, CBP **2023**, POP 2024 (7 bins) |
| `cria_results_tribal_2024.xlsx` | Tribal | 2024 | ACS 2024 only (5 bins, non-ACS indicators NaN) |
| `cria_results_county_2023.xlsx` | County | 2023 | ACS 2022, CBP 2021, POP 2022 |
| `cria_results_county_2022.xlsx` | County | 2022 | ACS 2021, CBP 2020, POP 2021 |
| `cria_results_county_2021.xlsx` | County | 2021 | ACS 2021, CBP 2020, POP 2021 |
| Audit report | All | All | — |

---

## III. EXECUTION

### Phase 0: Reconnaissance (Go/No-Go)
**Purpose**: Verify CBP 2023 data availability. This is the hard gate.
**Agent**: data-engineer

1. **Test CBP 2023 API endpoint** with both NAICS codes:
   ```bash
   # Civil Org (813410)
   curl -s "https://api.census.gov/data/2023/cbp?get=NAME,GEO_ID,NAICS2017_LABEL,ESTAB&for=county:001&in=state:01&NAICS2017=813410&key=${CENSUS_API_KEY}"

   # Hospitals (622110)
   curl -s "https://api.census.gov/data/2023/cbp?get=NAME,GEO_ID,NAICS2017_LABEL,ESTAB&for=county:001&in=state:01&NAICS2017=622110&key=${CENSUS_API_KEY}"
   ```

2. **Decision matrix**:

   | Result | Action |
   |--------|--------|
   | Valid JSON with establishment counts | **GO** → Phase 1 |
   | Error mentioning NAICS2017 | Test NAICS2022. If works → **GO WITH MODIFICATION** (update NAICS_YEAR=2022). Escalate to commander for approval. |
   | 404 / empty / "dataset not found" | **ABORT**. Pause operation. Report to commander: "CBP 2023 not available on Census API as of [date]. Awaiting guidance." |

3. **Review deprecated tribal code**: While testing the API, review `deprecated/old_scripts/cria_create_indicators_tribal.py` and `deprecated/old_scripts/cria_pull_data.py` for tribal handling patterns. Document findings and recommendations for how the current pipeline should handle tribal geography. Specifically:
   - How were non-ACS indicators handled? (Expected: dropped before binning)
   - How were zero-population tribes handled? (Expected: excluded from binning)
   - Any tribal-specific binning exceptions? (Expected: Limited English, Medical)
   - Any other tribal-specific logic the current pipeline should replicate?

**Decision Authority**: Commander (user) — if anything other than clean GO.

### Phase 1: Environment Preparation
**Purpose**: Configure environment, clear stale DB records, prepare for fresh runs.
**Agent**: data-engineer

1. **Backup current `.env`**:
   ```bash
   cp .env .env.backup_$(date +%Y%m%d)
   ```

2. **Update `.env` for primary production run** (2024 with CBP 2023):
   ```
   ACS_YEAR=2024
   CBP_YEAR=2023              # MODIFIED — hard requirement
   NAICS_YEAR=2017            # Or 2022 if Phase 0 determined
   POP_YEAR=2024
   ASARB_YEAR=2020
   ACS_LABELS_YEAR=2024
   PIPELINE_TIMEOUT_MINUTES=240
   ```

3. **Clear existing 2024 DB records** (fresh run — avoid duplicate key violations):
   ```python
   # Clear all 3 tables for year 2024
   from src.db.session import get_session
   from src.db.models import SourceData, Indicator, AggregateIndicator

   db = next(get_session())
   for model in [AggregateIndicator, Indicator, SourceData]:
       count = db.query(model).filter_by(year=2024).delete()
       print(f"Cleared {count} records from {model.__tablename__} for year 2024")
   db.commit()
   ```

4. **Clear existing comparison year DB records** (2021, 2022, 2023) if fresh runs desired:
   ```python
   for year in [2021, 2022, 2023]:
       for model in [AggregateIndicator, Indicator, SourceData]:
           count = db.query(model).filter_by(year=year).delete()
           print(f"Cleared {count} records from {model.__tablename__} for year {year}")
   db.commit()
   ```

5. **Verify Docker PostgreSQL is running**:
   ```bash
   docker ps | grep postgres
   # If not running:
   cd docker && docker-compose up -d postgres
   ```

6. **Sync geographies** for all three levels:
   ```bash
   PYTHONPATH=. poetry run python3 scripts/sync_geographies.py --level county
   PYTHONPATH=. poetry run python3 scripts/sync_geographies.py --level tract
   PYTHONPATH=. poetry run python3 scripts/sync_geographies.py --level tribal
   ```

### Phase 2: Primary Production Run (2024 — MAIN EFFORT)
**Purpose**: Generate current-year outputs for all three geography levels. Both DB and Excel.
**Agents**: data-engineer (execution), cria-analyst (validation at checkpoints)

**.env for Phase 2**: ACS_YEAR=2024, CBP_YEAR=2023, POP_YEAR=2024, NAICS_YEAR=2017*, ASARB_YEAR=2020, ACS_LABELS_YEAR=2024

**Step 1: County** (estimated: 5-10 minutes)
```bash
PYTHONPATH=. poetry run python3 scripts/run_full_pipeline.py \
    --geography county \
    --year 2024 \
    --export-excel
```
**Checkpoint**:
- Verify `data/output/cria_results_county_2024.xlsx` exists with all 11 sheets
- Verify `years` sheet shows CBP=2023
- Verify 3,200+ counties in `agg` sheet
- Spot-check Connecticut counties: Civil Org and Hospitals should be NaN
- Verify DB records written (query `aggregate_indicators` table for year=2024, geography_level=county)

**Step 2: Tract** (estimated: 60-180 minutes)
```bash
PYTHONPATH=. poetry run python3 scripts/run_full_pipeline.py \
    --geography tract \
    --year 2024 \
    --export-excel \
    --bins 7 \
    --timeout 240
```
**Checkpoint**:
- Verify `data/output/cria_results_tract_2024.xlsx` exists
- Expect 70,000+ tracts in output
- Verify 7 bins used (check `bin_meta` sheet)
- Note: CBP indicators (Civil Org, Hospitals) will be NaN or zero for tracts since CBP data is county-level. Document observed behavior.

**Step 3: Tribal** (estimated: 5-15 minutes)
```bash
PYTHONPATH=. poetry run python3 scripts/run_full_pipeline.py \
    --geography tribal \
    --year 2024 \
    --export-excel
```
**Context**: Tribal geography uses a different Census geography predicate (`american%20indian%20area/alaska%20native%20area/hawaiian%20home%20land:*`). ACS data will pull correctly. Non-ACS indicators (CBP, EAVS, ARDA, POP) will be NaN — this matches the historical approach where the old tribal script dropped non-ACS columns entirely. 5 bins (default) is correct for tribal per historical convention.

**Checkpoint**:
- Verify `data/output/cria_results_tribal_2024.xlsx` exists
- Document which indicators populated vs. NaN
- Expected: ACS indicators populated; CBP (Civil Org, Hospitals), EAVS (Inactive Voter), ARDA (Community Capital), POP (Population Change) as NaN
- Note count of tribal areas in output
- Compare indicator availability against deprecated tribal script expectations

### Phase 3: Historical Comparison Runs (County Only)
**Purpose**: Generate fresh county outputs for 2021-2023 for year-over-year comparison. Both DB and Excel.
**Agent**: data-engineer

For each year, update `.env` data years per the baseline mapping table, then run. DB records were cleared in Phase 1.

**Year 2023**:
`.env`: ACS_YEAR=2022, CBP_YEAR=2021, POP_YEAR=2022, ASARB_YEAR=2020, ACS_LABELS_YEAR=2022
```bash
PYTHONPATH=. poetry run python3 scripts/run_full_pipeline.py \
    --geography county --year 2023 --export-excel
```

**Year 2022**:
`.env`: ACS_YEAR=2021, CBP_YEAR=2020, POP_YEAR=2021, ASARB_YEAR=2020, ACS_LABELS_YEAR=2021
```bash
PYTHONPATH=. poetry run python3 scripts/run_full_pipeline.py \
    --geography county --year 2022 --export-excel
```

**Year 2021**:
`.env`: ACS_YEAR=2021, CBP_YEAR=2020, POP_YEAR=2021, ASARB_YEAR=2020, ACS_LABELS_YEAR=2021
```bash
PYTHONPATH=. poetry run python3 scripts/run_full_pipeline.py \
    --geography county --year 2021 --export-excel
```

**After all runs**: Restore `.env` to 2024 production settings (CBP_YEAR=2023 as new baseline).

### Phase 4: Output Review and Year-over-Year Comparison
**Purpose**: Validate all outputs and identify trends/anomalies across years.
**Agents**: cria-analyst (analysis), statistical-tester (validation tests)

1. **Structural validation** (all 6 output files + corresponding DB records):
   - All expected sheets present (11 sheets in results workbook: ref, years, indicators, pos, scores, scores_percentiles, agg, bin_labels, bin_meta, agg_labels, agg_meta)
   - Row counts reasonable (3,200+ counties, 70K+ tracts, tribal count documented)
   - No unexpected all-NaN indicator columns (except tribal non-ACS — expected)
   - `years` sheet reflects correct data year configuration per run
   - DB record counts match Excel row counts

2. **Statistical validation** (county 2024 primary):
   - Aggregate CRI scores: check distribution (mean near 0, reasonable spread)
   - Indicator correlations: compare against baseline 0.94 average (county 2022)
   - Binning metadata: verify auto-select methods are reasonable (not all FisherJenks — would indicate center-scaling regression)
   - Z-scores: verify Population Change uses subset z-scores (not full dataset)
   - Center-scaled scoring: verify ADCM+TSS are z-scored across methods before combining

3. **Domain special case verification** (county 2024):
   - Connecticut: CBP indicators (Civil Org, Hospitals) are NaN for all CT counties (FIPS 09)
   - Puerto Rico: Limited English indicator excludes Spanish speakers
   - Population Change: present and using correct subset z-score methodology
   - CBP 2023: establishment counts are non-zero and plausible (compare against CBP 2022 values)

4. **Year-over-year comparison** (county 2021-2024):
   - Compare aggregate CRI score distributions across years
   - Identify counties with large year-over-year swings (>2 std dev) — flag for review
   - Compare indicator means and standard deviations across years
   - Check that indicator count is consistent (22 for all years, or document missing indicators and why)
   - CBP indicator trend: does advancing from CBP 2020→2021→2023 show reasonable establishment count changes?
   - Population Change availability: present in which years?

5. **Tribal assessment**:
   - Document which indicators populated vs. NaN — compare against deprecated script expectations
   - Provide count of tribal areas with valid data vs. zero-population areas
   - Assess whether binning results are reasonable for the reduced indicator set
   - Document any differences from historical tribal output
   - **Team recommendation**: Based on deprecated code review, what (if anything) should the current pipeline do differently for tribal? Should non-ACS indicators be explicitly dropped before aggregation? Should zero-population areas be excluded from binning?

### Phase 5: Quality Audit
**Purpose**: Adversarial review of all outputs, methodology, and team conclusions.
**Agent**: quality-auditor (MANDATORY — no output is final without this phase)

Apply the following audit checklists from `quality-auditor.md`:

1. **Statistical Correctness Audit** — verify formulas, orientation, z-scores, bin counts per geography
2. **Domain Special Cases Audit** — verify CT CBP, PR Limited English, Population Change, tribal non-ACS
3. **Bias Detection Audit**:
   - Selection bias: Are we only checking counties/indicators that look good?
   - Confirmation bias: Did Phase 4 actively search for problems, or just confirm expectations?
   - Survivorship bias: What indicators/geographies are MISSING and why? Is the tribal reduced indicator set hiding issues?
   - Recency bias: Are year-over-year trends evaluated across all 4 years, not just 2023→2024?
4. **Test Quality Audit** — assess whether any new tests from Phase 4 prove correctness vs. merely checking structure
5. **CBP 2023 Specific Audit**:
   - Are CBP 2023 values plausible? Compare Civil Org and Hospitals establishment counts against CBP 2022 baseline.
   - Did advancing the CBP year introduce any new edge cases (new states with zeros, changed NAICS classifications)?
   - Is the Connecticut special case still valid for CBP 2023?

**Audit deliverable**: Formal audit report per the quality-auditor report format:
- Findings (CRITICAL/HIGH/MEDIUM/LOW)
- Statistical Correctness assessment
- Domain Compliance assessment
- Bias Check results
- Year-over-year trend assessment
- Tribal viability assessment
- Verdict: PASS / PASS WITH CONCERNS / FAIL

---

## IV. SUSTAINMENT

### Environment Configurations Per Phase

| Phase | ACS_YEAR | CBP_YEAR | POP_YEAR | NAICS_YEAR | TIMEOUT | BINS | DB |
|-------|----------|----------|----------|------------|---------|------|----|
| 2.1 County 2024 | 2024 | **2023** | 2024 | 2017* | 60 | 5 | Write |
| 2.2 Tract 2024 | 2024 | **2023** | 2024 | 2017* | **240** | **7** | Write |
| 2.3 Tribal 2024 | 2024 | **2023** | 2024 | 2017* | 60 | 5 | Write |
| 3a County 2023 | 2022 | 2021 | 2022 | 2017 | 60 | 5 | Write |
| 3b County 2022 | 2021 | 2020 | 2021 | 2017 | 60 | 5 | Write |
| 3c County 2021 | 2021 | 2020 | 2021 | 2017 | 60 | 5 | Write |

*NAICS_YEAR may need to be 2022 if Phase 0 determines CBP 2023 requires it.

### Output Manifest (DB + Excel for each)

| File | Phase | Geography | Year | Bins | Expected Rows |
|------|-------|-----------|------|------|---------------|
| `cria_results_county_2024.xlsx` | 2.1 | County | 2024 | 5 | ~3,200 |
| `cria_results_tract_2024.xlsx` | 2.2 | Tract | 2024 | 7 | ~70,000 |
| `cria_results_tribal_2024.xlsx` | 2.3 | Tribal | 2024 | 5 | TBD |
| `cria_results_county_2023.xlsx` | 3a | County | 2023 | 5 | ~3,200 |
| `cria_results_county_2022.xlsx` | 3b | County | 2022 | 5 | ~3,200 |
| `cria_results_county_2021.xlsx` | 3c | County | 2021 | 5 | ~3,200 |
| Audit report | 5 | All | All | — | — |

---

## V. COMMAND AND SIGNAL

### Team Composition: Pipeline Validation (Full Team)

| Agent | Role | Phases Active |
|-------|------|---------------|
| **data-engineer** | Pipeline executor, environment config, DB management, deprecated code review | 0, 1, 2, 3 |
| **cria-analyst** | Domain validation, formula verification, trend analysis, tribal assessment | 2 (checkpoints), 4 |
| **statistical-tester** | Write regression tests for CBP 2023 behavior and tribal output | 4 |
| **quality-auditor** | Adversarial review of all outputs and conclusions | 5 (and spot-checks in 2, 4) |

### Coordination
- **Phase 0**: data-engineer tests API and reviews deprecated tribal code. Reports GO/NO-GO to commander.
- **Phase 1**: data-engineer prepares environment and clears DB. Solo execution.
- **Phase 2**: data-engineer executes each step sequentially. cria-analyst validates at each checkpoint before proceeding.
- **Phase 3**: data-engineer executes comparison runs (mechanical .env changes between runs).
- **Phase 4**: cria-analyst leads analysis with statistical-tester. Both provide tribal recommendations.
- **Phase 5**: quality-auditor operates solo. Audits all outputs, all conclusions, all team recommendations.

### Escalation Criteria (pause operation, report to commander)
1. Phase 0 returns NO-GO on CBP 2023 — **ABORT**
2. NAICS year change required (2017 → 2022) — needs approval
3. Calibration regression detected (county correlation drops below 0.90)
4. Quality auditor issues CRITICAL finding
5. Year-over-year comparison reveals anomalies exceeding 2 std dev in 10%+ of counties
6. Tribal output is fundamentally different from historical expectations

### Success Criteria
- [x] All 6 Excel workbooks generated with complete sheet structure
- [x] All 6 year/geography combinations written to PostgreSQL (98,956 aggregate records)
- [ ] County 2024 calibration within 0.05 of baseline (0.94 ± 0.05) — not re-run this session
- [x] Domain special cases verified (CT CBP restructuring documented, Pop Change zeros at tract/tribal)
- [x] Year-over-year trends are plausible (no unexplained discontinuities)
- [x] Tribal output documented with indicator availability and team recommendation
- [x] Deprecated tribal code reviewed and recommendations provided
- [x] Quality audit verdict: PASS WITH CONCERNS (CT restructuring, tract/tribal all-zero non-ACS)

---

## ANNEXES

### Annex A: .env Restore Procedure
After all runs complete, restore production configuration:
```bash
# Verify backup exists
ls .env.backup_*
# Set new production baseline:
ACS_YEAR=2024
CBP_YEAR=2023        # NEW baseline (advanced from 2022)
POP_YEAR=2024
NAICS_YEAR=2017      # Or 2022 if changed during op
ASARB_YEAR=2020
ACS_LABELS_YEAR=2024
PIPELINE_TIMEOUT_MINUTES=60    # Restore default
```

### Annex B: Rollback Procedure
If CBP 2023 produces suspect results after runs complete:
```bash
cp .env.backup_* .env
# Clear CBP 2023 records and re-run with CBP 2022
# (requires clearing DB records for affected year/geography first)
```

### Annex C: Connecticut Verification Query
Spot-check CT CBP handling in county output:
```python
import pandas as pd
df = pd.read_excel("data/output/cria_results_county_2024.xlsx", sheet_name="indicators")
ct = df[df.index.str.startswith("09")]  # CT FIPS = 09
print(ct[["Civil Org", "Hospitals"]])
# Expected: all NaN for CT counties
```

### Annex D: Tribal Historical Handling (from Deprecated Code)

**Source**: `deprecated/old_scripts/cria_create_indicators_tribal.py`

The old tribal pipeline was a separate script that diverged from the county/tract pipeline at the indicator calculation stage:

1. **Data pull**: Used the same `cria_pull_data.py` which pulled all sources. CBP data came back as county-level (hardcoded `county:*` in API URL), resulting in NaN when merged with tribal GEO_IDs. The NaN values were then filled with 0 by a global `fillna(0)` step.

2. **Indicator calculation**: The dedicated tribal script immediately dropped all non-ACS indicators:
   ```python
   cols_unknown = ref.loc[ref["Source"] != "ACS", "Indicator"]
   df = df.drop(cols_unknown, axis=1)
   ```
   This removed CBP (Civil Org, Hospitals), EAVS (Inactive Voter), ARDA (Community Capital), and POP (Population Change).

3. **Zero-population handling**: Tribes with 0 population were excluded from binning but kept in the final output:
   ```python
   ser_zero_pop = pd.Series(data["S0101_C01_001E"], index=...)
   bin_results = fit_data(df_fit=df_scale.loc[ser_zero_pop.loc[ser_zero_pop != 0].index, :], ...)
   ```

4. **Binning**: 5 bins. Exceptions: Limited English and Medical excluded from JenksCaspall (now moot since JenksCaspall was removed from the method pool).

5. **Special case exclusions**: PR Limited English exclusion was explicitly skipped for tribal (`if geography in ["state", "county", "tract"]`). Connecticut CBP fix was county-only.

**Current pipeline gap**: The current `run_full_pipeline.py` does NOT drop non-ACS indicators for tribal. The pipeline will attempt to calculate, aggregate, and bin all 22 indicators. Non-ACS indicators will be NaN (not zero — the old `fillna(0)` step is not in the current pipeline). The team should assess whether this produces acceptable output or whether tribal-specific handling needs to be added to the current codebase.
