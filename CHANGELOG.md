# FEMA CRIA - Changelog

All notable changes to this project are documented here.

Format: `[date] [tag] description`

---

## 2026-05

### 2026-05-14
- `[fix][cli]` Refuse pipeline runs when `--year` disagrees with `settings.acs_year` — closes silent-mislabel mode where sponsor produced `cria_results_county_2024.xlsx` containing ACS 2023 data (env `ACS_YEAR=2023`, ran with `--year 2024`); the `--year` arg only flowed into the output filename and DB year column, while the actual ACS pull was driven by `settings.acs_year` (read from `.env`)
- `[fix][cli]` New `YearMismatchError(SystemExit)` + `preflight_year_consistency()` in `scripts/run_full_pipeline.py` — exits cleanly with code 1, error message names both years and lists three remediations (match the env, change the env, or pass `--allow-year-mismatch`)
- `[fix][cli]` Add `--allow-year-mismatch` CLI flag for legitimate divergence (back-dated tagging, vintage comparisons); when used, logs a loud warning naming both years so the divergence isn't invisible in logs
- `[test]` 607 → 612 tests (+5): matching year passes, mismatch aborts with code 1, error lists 3 fixes, override allows, override emits warning naming both years
- `[docs]` P1 task entry in `docs/tasks.md` capturing the root cause and file pointers (run_full_pipeline.py:660 — the `cria_results_{geography}_{year}.xlsx` filename construction; data_puller.py:55 — `CensusAPIClient()` instantiated with no year arg)
- Triggered by 2026-05-14 sponsor check-file comparison: their `cria_results_county_2024.xlsx` and ours had identical structure (16 sheets, 3,284 GEO_IDs, same columns) but every ACS-derived indicator differed; sponsor's `years` sheet correctly reported `acs=2023` while ours reported `acs=2024`. Empirically confirmed by recomputing from local DB `year=2023` indicator rows: 14 of 17 ACS indicators matched the sponsor's file bit-for-bit (max abs diff = 5.55e-17, machine epsilon) across 3,222 common counties

### 2026-05-08
- `[docs]` Lead README Quick Start with the two bootstrap scripts (`import_reference_data.py` + `sync_geographies.py --level county`) BEFORE the pipeline command — closes the upstream half of the silent-success cliff that 2026-05-06 fail-fast guards closed downstream
- `[docs]` Restructure README Usage > Command Line into 3 sub-blocks: one-time-per-clone setup (all 4 sync levels shown, tract-needs-county callout), pipeline runs, diagnostics (`doctor.py` with `--check-api` and `--json` variants)
- `[docs]` `docs/guides/getting_started.md` Section 3 renamed "Import reference data" → "Bootstrap the database" and now covers BOTH scripts; sync command matches the next-section pipeline target (`--level state`); adds preflight-halt note and `doctor.py` callout
- `[docs]` `getting_started.md` Section 6 (county run) gains explicit `sync_geographies --level county` step; tract callout updated to mention both `--level tract` AND `--level county` are required

### 2026-05-06
- `[feat][core]` Defense-in-depth fail-fast on empty DB bootstrap state — `save_to_database` in `data_puller`, `indicators`, and `aggregator` now raises `RuntimeError` (not silent warning) when `indicator_map` or `geo_id_map` is empty AND there is data to write; error names exact remediation script (`scripts/import_reference_data.py` / `scripts/sync_geographies.py --level X`); partial misses still warn-and-continue
- `[feat][cli]` Pipeline preflight in `scripts/run_full_pipeline.py` — counts `reference_indicators` + per-level `geographies` before any data pull; tract pulls also require county geographies (D1 imputation); raises `PipelinePreflightError` (a `SystemExit` subclass — clean exit 1, no traceback) listing every failure with remediation; pointer to `scripts/doctor.py` for full diagnosis
- `[fix][core]` Surface parquet engine missing as `RuntimeError` in `_load_geographies()` — old code caught `ImportError` and fell through to the Census API path, which returns a stripped geography reference (no `state_abbr`, `county_name`) and corrupts downstream EAVS/CBP joins; non-import exceptions still warn-and-fall-through (preserves transient-failure recovery)
- `[fix][core]` Drop-log rewrite in `_post_process_data` — old `Dropping 3496 rows with invalid index` (always WARNING, no kept-count) replaced with `Cleaning merge artifacts: dropped N NaN-indexed rows (X%), keeping M valid rows. Outer-merge artifact from per-source data pulls...`; INFO when drop ratio ≤ 60%, WARNING above (catches genuine regression like corrupted geography file producing 90% NaN-indexed rows)
- `[feat][cli]` Add `scripts/doctor.py` install diagnostic — paste-friendly report walks env → config → data files → database (incl. `reference_indicators` count, geography level counts) → optional Census API ping; `--json` for machine consumption; exit codes 0/1/2; designed to short-circuit Teams-thread debugging
- `[db]` Add `count()` to `GeographyRepository` (with optional `level` filter) and `ReferenceIndicatorRepository` (with `active_only`) — required for preflight, useful elsewhere
- `[test]` 583 → 607 tests (+24): parquet ImportError, drop-log threshold/message, fail-fast at all 3 sites, preflight (populated/empty/tract-cross-level/multi-failure/doctor-pointer)
- `[docs]` Capture teammate-setup-robustness work — proposer plan, data-engineer implementation, quality-auditor review, defense-in-depth audit (`docs/reviews/20260505_*.md`); session doc `docs/sessions/20260506_TEAMMATE_SETUP_ROBUSTNESS.md` covers the silent-success failure mode + sponsor diagnosis
- Triggered by sponsor report (2026-05-05): `Indicator not found in database: Mobile Homes` ×22, pipeline reported success but persisted nothing — root cause was empty `reference_indicators` table from skipped `import_reference_data.py` setup step

### 2026-05-04
- `[docs]` Operational reference doc — Census API diagnostics (reading `CensusAPIError` body text, "Invalid Key" vs unknown-variable, variable-as-canary trap, why anonymous Census fails for full pipeline) and git orientation (decorate-graph output, identifying hashes, HEAD vs origin/main); companion to the implementation session doc, lives at `docs/sessions/20260504_DIAGNOSTICS_AND_GIT_REFERENCE.md`
- `[fix][api]` Surface real Census error text on non-JSON 200 responses — Census returns plain-text/HTML error bodies (e.g. `error: error: unknown variable 'DP04_0014E'`) with HTTP 200 for unknown variables, datasets, or bad keys; previous code died with cryptic `Expecting value: line 2 column 1` JSONDecodeError and discarded the actual server message
- `[fix][api]` New `CensusAPIError` exception preserves redacted URL, HTTP status, content-type, requested variables, and 500-char body excerpt at all 3 `json.loads` sites (`fetch_acs_data`, by-state tract fetch, `fetch_labels`)
- `[fix][api]` `CensusAPIClient.__init__` fails fast on empty key, `your_census_api_key_here` placeholder; warns when `ACS_YEAR` is later than the most recent ACS 5-year release
- `[fix][api]` `base_client.py` redacts `key=` from all logged URLs (5 sites) — fixes a latent secret-in-logs problem
- `[feat][api]` Soft-validate `CENSUS_API_KEY` format at startup — `_normalize_api_key` strips `.env` paste artifacts (surrounding whitespace, matched quote pairs, line-wrap newlines); `validate_census_api_key_format` heuristic checks 40-char hex, returns reason string on mismatch (warning only, never blocks)
- `[feat][api]` `confirm_suspect_api_key` CLI helper prompts on TTY (`Continue anyway? [y/N]`) when key looks suspect; in CI/Docker/non-interactive contexts logs warning and continues
- `[feat][cli]` Added `--yes` / `-y` flag to `run_full_pipeline.py` and `sync_geographies.py` to skip the prompt explicitly
- `[test]` 42 new tests (541 → 583): non-JSON 200 handling, key normalization, format heuristics, key masking, TTY gating, end-to-end propagation, log redaction
- Triggered by sponsor report: `Failed to pull Mobile Homes: Expecting value: line 2 column 1 (char 1)` against `DP04_0014E`

---

## 2026-04

### 2026-04-30
- `[docs]` Add user guide system — 13 guides under `docs/guides/` (3,140 lines): generalist (getting_started, pipelines, outputs, troubleshooting, glossary), domain (methodology, limitations, indicator_catalog, special_cases), engineering (contributing, extending, api_clients, operations)
- `[fix][docs]` Correct README Python API code block — was importing from non-existent `src.core.calculator` and calling non-existent `aggregator.aggregate()` method
- `[fix][docs]` Replace fabricated 0.97/0.99/1.00 README validation table with project.yaml truth (0.94 county 2022, 1.00 tract 2021), add note distinguishing reproducibility from construct/predictive validity
- `[fix][config]` Bump `.env.example` per-source year defaults to 2024-deliverable values (ACS_YEAR=2023, CBP_YEAR=2023, POP_YEAR=2024, ACS_LABELS_YEAR=2023) — eliminates silent wrong-year hazard for new users
- `[docs]` Restructure README Documentation section into 3 subsections (generalist / domain / engineering) linking all 13 user guides
- `[docs]` Document the 5 indicator function types, MAUT terminology, GEO_ID prefixes, ADCM+TSS auto-select scoring, the agg/cri/cria_p polarity, mean-not-sum aggregation, manual bin overrides (1 indicator + 5 composite columns), 15 special cases, all consolidated from scattered project.yaml lessons and code comments
- `[docs]` Process: ran 4 parallel agent reviews (cria-analyst, data-engineer, decision-scientist, quality-auditor) followed by quality-auditor verification pass — 9 verified bugs fixed, 1 false-positive auditor claim flagged

### 2026-04-08
- `[docs]` Upstream Decision Science review: skip MAUTScorer/sensitivity/team/YAML, adopt decision-scientist agent
- `[config]` Add `decision-scientist` agent — CRIA-adapted methodological auditor for CRCI pipeline (read-only, audit checklist for implicit weights, z-scores, calibration, special cases)
- `[core]` Add `_save_correlation_report()` to aggregator — auto-generates formatted `Correlation Matrix {GEO}.xlsx` in `data/output/reports/`
- `[core]` Fix correlation column ordering dedup — prevent duplicate labels from reference Excel
- `[docs]` Update CLAUDE.md and `.claude/README.md` — 6 agents (was 5), updated scope matrix and catalog
- `[data]` Verified county/tract correlation reports auto-populated (22x22, labeled, formatted tables)

### 2026-04-07
- `[core]` Add `lowest_ind` tab — top 3 worst resilience indicators per geography via `np.argsort` on z-scores
- `[core]` Add full correlation matrix output — Pearson r, p-values, significance flags (Fisher z CI), pairwise sample sizes
- `[core]` Add `pearsonr_ci()` and `calc_full_corr_matrix()` to `transformations.py` — fixes deprecated bug (uses valid pair count, not raw array length)
- `[core]` Add `_compute_correlation()` to aggregator — reads `Label_Correlation`/`Order_Correlation` from reference Excel for relabeling
- `[fix]` Pop change and pop_p bin direction: `reverse: True` → `reverse: False` — bin 1 = least change, bin 5 = most change
- `[core]` Excel output now has 16 tabs (was 11): added `lowest_ind`, `corr`, `p`, `zero`, `n`
- `[test]` 37 new tests: pearsonr_ci (8), calc_full_corr_matrix (9), lowest_ind (7), correlation output (7), pop change bins (6)
- `[test]` Test suite: 504 → 541 tests (+37)
- `[data]` Regenerated county/tract/tribal 2024 output with all 3 features
- `[data]` County 2024: 3,284 counties × 22 indicators, 16 tabs, pop change bins ascending
- `[data]` Tract 2024: 85,382 tracts × 22 indicators, 16 tabs, 7-bin ascending pop change
- `[data]` Tribal 2024: 704 rows, 17 indicators, binning-only (unchanged — no aggregation)

---

## 2026-03

### 2026-03-25
- `[fix]` Indicators tab now shows true values — NaN (blank/gray on map) for missing data instead of imputed national average
- `[fix]` CRCI pipeline still uses mean-imputed values internally for composite score calculation (unchanged behavior)
- `[fix]` Aggregator calls `_clean_indicators()` twice: `impute=False` for display tab, `impute=True` for CRCI pipeline
- `[fix]` EAVS `-88` ("does not apply") now maps to NaN instead of `0` — eliminates false Inactive Voter values for 14 non-reporting states/territories
- `[fix]` All 5 indicator calculation functions (`_divide`, `_max`, `_mean`, `_divide_scalar`, `_reverse_divide`) now return NaN for zero denominators (was falsely returning `0`)
- `[test]` 19 new imputation split tests (`test_imputation_split.py`): NaN preservation, CRCI pipeline, CT/PR special cases, tribal, edge cases
- `[test]` 30 new no-data handling tests (`test_nodata_handling.py`): EAVS -88/-99, zero-denom for all function types, guard tests, end-to-end aggregator
- `[test]` 6 existing tests updated for new NaN behavior (was asserting false zeros)
- `[test]` Test suite: 455 → 504 tests (+49)
- `[data]` Regenerated county/tract/tribal 2024 output with both fixes applied
- `[data]` County 2024: 677 Inactive Voter NaN (was 0 — all imputed), 3,284 CRCI scores intact
- `[data]` Tract 2024: 85,382 geographies, 11,666 Inactive Voter NaN, all CRCI scores intact
- `[data]` Tribal 2024: 704 rows, 17 indicators, binning-only (no imputation, unchanged)

### 2026-03-24
- `[infra]` Sync upstream doctrine from utils repo — wave terminology, TCS universal task spec, doctrine propagation
- `[infra]` Add `proposer` agent — CRIA-adapted problem analyst (sonnet model, docs/-only write, pre-implementation exploration)
- `[infra]` Add `.claude/skills/` directory — 5 Level 0 skills (configuration-management, python-venv-management, shift-left-testing, session-end, SKILLS_FRAMEWORK)
- `[infra]` Add `bug-fix` and `code-review` team templates, update `indicator-development` with proposer workflow
- `[infra]` Update `session-start.md` — Step 5 checks for `.claude/upstream-update.md` (doctrine propagation)
- `[infra]` Update `task.md` — "Terminology: Phases vs Waves" section, TCS universal language, military origin
- `[docs]` Update `CLAUDE.md` — 5 agents, 6 team templates, proposer in agent list
- `[docs]` Update `agents/README.md` — proposer in catalog/scope matrix, design principle #6, Level 0/1 guidance, model note

### 2026-03-20
- `[docs]` Add `/task` command — project work tracker with escalation ladder (Task → TCS → CONOP → OPORD)
- `[docs]` Add `/sitrep` command — team-facing status reports with scope filtering
- `[docs]` Add `.claude/teams/` directory with 4 team templates: data-pipeline, indicator-development, test-validation, full-pipeline-validation
- `[docs]` Update agents/README.md with escalation framework and team template references
- `[docs]` Update session-start/session-end to include `docs/tasks.md` in workflow
- `[docs]` Update CLAUDE.md with slash commands table, agent teams section
- `[docs]` Create `docs/tasks.md` persistent task tracker
- `[data]` Regenerated county/tract/tribal 2024 output with manual bins

### 2026-03-19
- `[core]` Restore manual bin boundaries from deprecated code for 6 columns: cria_p, cri, agg, pop change, pop_p, Median Income
- `[core]` Add `MANUAL_BINS` constant and `_apply_manual_bins()` to BinningEngine — uses `pd.cut()` with domain-specific boundaries
- `[core]` Manual bins bypass auto-select, preserving deprecated bell-curve distributions and label reversal
- `[test]` 15 new manual bin tests (TestManualBins): bell curve verification, reversed labels, 7-bin tract, NaN, fallthrough
- `[test]` Fix synthetic Median Income data to span realistic range (was 0-1, now 10k-150k)
- `[test]` All 455 tests passing (was 438)

### 2026-03-05
- `[fix]` Remove aggregation/CRCI from tribal output — tribal gets binning only (matches deprecated behavior)
- `[fix]` D10: Filter 3,215 county-format GEO_IDs from tribal output (DataPuller outer merge contamination)
- `[core]` Add `skip_aggregation` parameter to `AggregateIndicator.create_aggregate()` — skips z-scores, aggregation, CRCI
- `[core]` Add `impute` parameter to `_clean_indicators()` — tribal uses `impute=False` matching deprecated
- `[data]` Regenerated tribal output: 6 tabs (was 11), 704 tribal-only GEO_IDs, bins visible on first row
- `[test]` 28 new tribal-specific tests (test_tribal_output.py): skip_aggregation, D10 filtering, bin structure, regression guards
- `[test]` All 438 tests passing (was 410)
- `[docs]` CONOP: Tribal output fix plan (Task-Condition-Standard format, 6 phases)

### 2026-03-04 (session 2)
- `[fix]` D9: Filter 3,215 county-format GEO_IDs from tract output (DataPuller outer merge contamination)
- `[fix]` D8: Filter 3,301 zero-population tribal GEO_IDs before aggregation (prevents degenerate mean-imputed bins)
- `[fix]` CT dedup: Deduplicate Connecticut county lookup (9 old + 9 new planning regions) to prevent merge expansion
- `[data]` Regenerated tract output: 85,382 tract-only GEO_IDs (was 88,597 with county contamination)
- `[data]` Regenerated tribal output: 618 non-zero-pop GEO_IDs (was 3,919 with zero-pop rows)
- `[test]` All 410 tests passing

### 2026-03-04 (session 1)
- `[fix]` Fix tract/tribal bin_labels degenerate output — 5/22 indicators showed identical bins ("same numbers")
- `[fix]` D1: Add county-to-tract imputation for non-ACS indicators (Civil Org, Hospitals, Pop Change, Inactive Voter, Religion)
- `[fix]` D2: Tribal drops non-ACS indicators entirely (matches deprecated pipeline behavior)
- `[fix]` D4: Pass geo_reference + exceptions to create_aggregate() — enables CT CBP and PR Limited English special cases
- `[fix]` D6: Add vote data post-processing with min_count=1 NaN safety for Inactive Voter_bins
- `[fix]` D7: Auto-set bins by geography (tract=7, others=5) via DEFAULT_BINS constant
- `[test]` Test suite expansion: 353 → 410 tests (+38 regression, +19 pipeline helper)
- `[docs]` Added CONOP bin_labels diagnosis plan
- `[config]` Updated quality-auditor agent definition: added Write/Edit permissions to prevent agent freezing

---

## 2026-02

### 2026-02-24 (session 2)
- `[test]` Test suite expansion: 147 → 353 tests via agent team CONOP execution
- `[test]` Phase 1: 7 new unit test files — indicators, transformations, API clients, data puller, settings, paths (171 tests)
- `[test]` Phase 2: Smoke tests (pipeline E2E) and cross-component integration (14 tests)
- `[test]` Phase 3: Calibration tests with synthetic data fixtures (21 tests)
- `[test]` Code coverage: 81% overall (target >70%), critical modules 89-100%
- `[config]` Added smoke/calibration pytest markers, auto-marking in conftest.py
- `[docs]` Added CONOP test suite expansion plan

### 2026-02-24 (session 1)
- `[data]` Multi-geography production run: advanced CBP from 2022 to 2023
- `[data]` Generated 6 workbooks: county 2021-2024, tract 2024, tribal 2024
- `[data]` County 2024: 3,284 counties × 22 indicators (CBP=2023)
- `[data]` Tract 2024: 88,597 tracts × 22 indicators, 7 bins (138-min pipeline)
- `[data]` Tribal 2024: 3,919 tribal areas × 22 indicators
- `[data]` Historical county: 2021, 2022, 2023 for year-over-year comparison
- `[db]` 98,956 aggregate records saved to PostgreSQL
- `[config]` Updated .env: CBP_YEAR=2023 (production), data year matrix updated
- `[docs]` Added CONOP multi-geography production run plan

### 2026-02-17
- `[core]` Added ref and years tabs to output spreadsheets (indicator reference + year config)
- `[core]` Added binning method selection metadata (selected_method, selected_score) to bin_meta/agg_meta
- `[fix]` Fixed auto-select binning to use center-scaled ADCM+TSS scoring (replicates original fit_data methodology)
- `[core]` Restored headtail_breaks and std_mean to candidate method pool (6 methods)
- `[test]` Added 12 new tests for method metadata and ref/years tabs (147 total)
- `[fix]` Fixed POPClient year clamping — clamp NETMIG years to decade base to prevent missing column errors
- `[api]` Updated POP_YEAR to 2024, restoring Population Change indicator with co-est2024-alldata.csv
- `[docs]` Added pipeline guide (docs/design/pipeline_guide.md) — commands, options, output file reference
- `[data]` Generated 2024 county results with all 22 indicators (3,283 counties)

---

## 2025-12

### 2025-12-22
- `[config]` Added pytest-timeout (300s) to prevent runaway tests (18-day incident)
- `[docs]` Created /pcc skill (Pre-Code Check) - fast, same checklist every push
- `[docs]` Created /pci skill (Pre-Code Inspection) - context-aware, based on diff
- `[docs]` Integrated PCC/PCI into session-end workflow

### 2025-12-10
- `[docs]` Centralized project organization: added config/project.yaml, config/indicators.yaml
- `[docs]` Moved design docs from sessions/ to design/
- `[docs]` Added YAML frontmatter with tags to all session docs
- `[docs]` Created workplan.md and changelog.md

### 2025-12-05
- `[bugfix]` Fixed JenksCaspall infinite loop on degenerate data (Bug #8)
- `[binning]` Removed jenks_caspall from auto-select methods, using FisherJenks instead

### 2025-12-03
- `[bugfix]` Fixed 7 critical bugs during calibration testing (Bugs #1-7)
- `[performance]` Database save performance: 6.5hrs → 2.71s (2000x improvement)
- `[database]` Added bulk_create() and get_geo_id_map() for batch operations
- `[calibration]` County-level validation: 22/22 indicators, avg correlation 0.94

---

## 2025-11

### 2025-11-08
- `[deployment]` Phase 7 complete: Docker Compose with PostgreSQL on port 5433
- `[docs]` Production deployment guide (24 pages)
- `[database]` Alembic migrations validated
- `[database]` Reference data import: 22 indicators, 6 data years

### 2025-11-07
- `[feature]` Phase 6 complete: Full database integration
- `[database]` All core classes now save to database
- `[scripts]` Created sync_geographies.py and run_full_pipeline.py
- `[test]` 128 tests passing (120 unit, 8 integration)

---

## 2025-10

### 2025-10-30
- `[refactor]` Phases 1-4 complete: Foundation, API clients, core classes, database layer
- `[config]` Poetry dependency management, Pydantic settings
- `[database]` 7 SQLAlchemy models, repository pattern
- `[docker]` Docker Compose configuration
- `[api]` CensusAPIClient, CBPClient, EAVSClient, ARDAClient, POPClient
- `[core]` DataPuller, IndicatorCalculator, AggregateIndicator, BinningEngine

### 2025-10-23
- `[docs]` Testing guide created

---

## Project Status

**Current Version**: 1.0.0
**Status**: Production Ready
**Last Updated**: 2026-02-17
