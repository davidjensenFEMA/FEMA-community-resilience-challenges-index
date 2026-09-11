---
date: 2026-02-17
tags: [#fix, #pop, #data-pull, #county, #docs]
status: complete
---

# POPClient Year Clamping Fix and Pipeline Guide

**Date**: 2026-02-17
**Branch**: `main`

---

## Summary

Fixed the POPClient to correctly clamp NETMIG year requests to the Census decade base, updated POP_YEAR to 2024 (newly available data), and generated fresh 2024 county results with the Population Change indicator restored. Also wrote a pipeline usage guide.

## Problem

The POPClient requested the last 5 years of NETMIG data regardless of what the Census popest file actually contains. For `POP_YEAR=2022`, it asked for `NETMIG2018`-`NETMIG2022`, but the `co-est2022-alldata.csv` file (from the 2020 decade) only contains 2020-2022. This caused a `ValueError: Usecols do not match columns` crash, making Population Change unavailable for any recent year.

## Changes Made

### 1. POPClient Fix (`src/api/external_clients.py`)

- Moved decade base calculation (`year_base`) before the year list generation
- Default years now clamp to `max(pop_year - 4, year_base)` instead of blindly going back 5
- Explicitly provided years are filtered to remove anything before `year_base`
- Raises `ValueError` if no valid years remain after clamping

| POP_YEAR | Before | After |
|----------|--------|-------|
| 2024 | N/A | [2024, 2023, 2022, 2021, 2020] |
| 2022 | Crash (NETMIG2018/2019 missing) | [2022, 2021, 2020] |
| 2030 | Would request 2025-2030 | [2030, 2029, ..., 2020] |

### 2. Updated POP_YEAR to 2024

- `.env`: `POP_YEAR=2022` → `POP_YEAR=2024`
- New data source: `co-est2024-alldata.csv` (2020-2024 population estimates)
- Provides NETMIG2020 through NETMIG2024

### 3. Generated 2024 County Results

Ran pipeline with `--export-excel --no-db`:

| Metric | Previous (no POP) | With POP fix |
|--------|-------------------|--------------|
| Counties | 3,232 | 3,283 |
| Source columns | 52 | 57 |
| Population Change valid | 0 | 3,144 / 3,283 |

Output files:
- `data/output/cria_results_county_2024.xlsx` (4.7 MB, 9 sheets)
- `data/output/cria_indicators_county_2024.xlsx` (1.7 MB)
- `data/output/cria_inputs_county.xlsx` (906 KB)

### 4. Pipeline Guide (`docs/design/pipeline_guide.md`)

New guide covering:
- Fresh pull vs re-run commands
- `--no-db` for when data already exists in database
- All CLI options
- Output file and worksheet descriptions
- Known issues and workarounds

## Files Changed

| File | Change |
|------|--------|
| `src/api/external_clients.py` | POPClient year clamping fix |
| `.env` | POP_YEAR=2022 → 2024 (not committed) |
| `docs/design/pipeline_guide.md` | New pipeline usage guide |

## Next Steps

- Refresh 2024 records in PostgreSQL (current DB records lack Population Change)
- Pull tract-level data for 2022-2024 (increase PIPELINE_TIMEOUT_MINUTES)
- Consider adding year-over-year comparison for 2023 vs 2024
