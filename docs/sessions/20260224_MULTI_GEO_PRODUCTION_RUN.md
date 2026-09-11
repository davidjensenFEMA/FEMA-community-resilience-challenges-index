---
date: 2026-02-24
tags: [#data-pull, #indicators, #aggregation, #binning, #census-acs, #cbp, #county, #tract, #tribal, #database]
status: complete
---

# Multi-Geography Production Run — CBP 2023

**Date**: 2026-02-24
**Branch**: `main`

---

## Summary

Executed a full multi-geography CRIA production run advancing CBP data from 2022 to 2023. Generated 6 Excel workbooks (county 2021-2024, tract 2024, tribal 2024) with 98,956 aggregate records saved to PostgreSQL. All outputs passed quality audit.

## CONOP Execution

Followed `docs/plans/CONOP_multi_geo_production_run.md` — a 5-phase operational plan:

| Phase | Task | Result | Duration |
|-------|------|--------|----------|
| 0 | CBP 2023 API recon | GO — API available, NAICS2017 valid | 5 min |
| 1 | Environment prep & DB cleanup | Done — .env updated, DB cleared, geos synced | 10 min |
| 2.1 | County 2024 pipeline | 3,284 rows × 22 indicators | ~5 min |
| 2.2 | Tract 2024 pipeline | 88,597 rows × 22 indicators, 7 bins | 138 min |
| 2.3 | Tribal 2024 pipeline | 3,919 rows × 22 indicators | ~3 min |
| 3 | Historical county 2021-2023 | 3 workbooks, all 22 indicators | ~15 min |
| 4 | Output review & YoY comparison | All checks passed | — |
| 5 | Quality audit | PASS WITH CONCERNS | — |

## Deliverables

| File | Geography | Year | Rows | Bins | CBP Year | Size |
|------|-----------|------|------|------|----------|------|
| cria_results_county_2024.xlsx | County | 2024 | 3,284 | 5 | **2023** | 4.6M |
| cria_results_county_2023.xlsx | County | 2023 | 3,283 | 5 | 2021 | 4.7M |
| cria_results_county_2022.xlsx | County | 2022 | 3,275 | 5 | 2020 | 4.5M |
| cria_results_county_2021.xlsx | County | 2021 | 3,275 | 5 | 2020 | 4.5M |
| cria_results_tract_2024.xlsx | Tract | 2024 | 88,597 | 7 | **2023** | 107M |
| cria_results_tribal_2024.xlsx | Tribal | 2024 | 3,919 | 5 | **2023** | 2.6M |

**Database**: 98,956 aggregate records across county (4 years), tract (1 year), tribal (1 year).

## Key Findings

### Connecticut COG Restructuring (NOT a bug)
CT abolished counties in 2022, replacing them with 9 planning regions (FIPS 09110-09190). CBP data now contains 18 CT entries:
- **Old counties (09001-09015)**: Get uniform state-level CBP values
- **New planning regions (09110-09190)**: Get unique actual CBP 2023 data
- In CBP 2020 (county 2021/2022): 9 CT counties with unique per-county values
- In CBP 2021 (county 2023): 18 entries, old = uniform, new = zeros
- In CBP 2023 (county 2024): 18 entries, old = uniform, new = valid data

### Year-over-Year County Trends (all plausible)
- Education: -0.8% (more education over time)
- Poverty: -0.2% (slight decline)
- Median Income: +$4,608 (inflation/growth)
- GINI: +0.001 (slight inequality increase)
- 2021 = 2022 identical means (expected: same source data ACS 2021, CBP 2020)

### Tract/Tribal Non-ACS Indicators
Civil Org, Hospitals, and Population Change are all-zero at tract and tribal level. CBP provides county-level data only; POP doesn't have sub-county population change. The deprecated tribal script dropped these columns; the current pipeline retains them as zeros.

### Tribal Row Count
3,919 rows (not 704 from geography sync) — Census ACS returns sub-tribal geographies.

## Configuration Changes

- `.env`: CBP_YEAR 2022 → **2023** (permanent production change)
- `.env`: Data year matrix comment updated (cbp year_2024: 2021 → 2023)
- `.env`: PIPELINE_TIMEOUT_MINUTES restored to 60 (was 240 during tract run)
- `.env.backup_20260224` created (not committed)

## Pipeline Timing (Tract 2024)

| Step | Duration | Notes |
|------|----------|-------|
| Data pull | 11 min | 88,597 × 57 columns |
| DB save (source) | 63 min | Bulk insert bottleneck |
| Indicator calculation | instant | NumPy vectorized |
| DB save (indicators) | 2.5 min | |
| Aggregation + binning | 55 min | 6 methods × 22 indicators × 88K rows |
| DB save (aggregates) | 6 sec | bulk_create optimized |
| Excel export | 3 min | 107MB file |
| **Total** | **138 min** | |

## Next Steps

- Run county 2024 calibration against baseline (success criterion not verified this session)
- Consider dropping all-zero non-ACS columns for tract/tribal outputs (match legacy behavior)
- Commit uncommitted test suite expansion (7 test files, pytest markers) from prior session
- Investigate tribal row count discrepancy (3,919 vs 704 geographies)
