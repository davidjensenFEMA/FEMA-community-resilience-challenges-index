---
date: 2026-04-30
tags: [#docs, #refactor]
status: complete
---

# User Guide System + Multi-Agent Doc Review

**Date**: 2026-04-30
**Branch**: `main`
**Follows**: [20260408_UPSTREAM_REVIEW.md](20260408_UPSTREAM_REVIEW.md)

---

## Summary

Built a 13-guide user documentation system at `docs/guides/` (3,140 lines), driven by user request to extend a small README update into "a deep user guide alongside the readme." The work expanded into a multi-agent review-and-fix cycle that surfaced and corrected substantial pre-existing inaccuracies in both the original README and the early guides I wrote.

Three review passes:
1. **Initial 4-agent parallel review** (cria-analyst, data-engineer, decision-scientist, quality-auditor) — surfaced ~30 findings across factual, methodological, and operational dimensions
2. **Verification pass** — checked agent claims against actual code; 30% of claims were themselves wrong
3. **Quality-auditor follow-up** after fixes — caught 9 new bugs introduced during the fix phase

PCC at session-end caught one more critical bug: my "fix" of the test count from 541 → 531 was itself wrong (auditor was right that 531 was wrong, but the actual answer is 541 — pytest expands parametrize). Reverted before commit.

## Changes Made

### Files modified (2)
- `README.md` — corrected broken Python API code block (was importing from non-existent `src.core.calculator` and calling non-existent `aggregator.aggregate()`); replaced fabricated 0.97/0.99/1.00 validation numbers with project.yaml truth (0.94 county / 1.00 tract) with construct-validity caveat; restructured Documentation section into 3 subsections linking all 13 guides
- `.env.example` — bumped per-source year defaults (`ACS_YEAR=2023`, `CBP_YEAR=2023`, `POP_YEAR=2024`, `ACS_LABELS_YEAR=2023`) to match 2024-deliverable assumption in all docs; added explicit note that `--year` does NOT override per-source years

### Files added (13 new user guides under `docs/guides/`)

**Generalist** (5):
- `getting_started.md` (173 lines) — fresh clone to first state-pipeline run
- `pipelines.md` (216) — every CLI flag, year config matrix, all common workflows
- `outputs.md` (178) — every workbook tab, agg/cri/cria_p polarity, MANUAL_BINS
- `troubleshooting.md` (161) — pre-existing, light update for cross-links
- `glossary.md` (193) — MAUT, ADCM, TSS, GEO_ID prefixes, CRCI/CRI/CRIA naming

**Domain & methodology** (4):
- `methodology.md` (187) — degenerate MAUT, equal weights rationale, mean-not-sum, calibration interpretation, H1/H2 audit issues
- `limitations.md` (182) — what CRCI can't tell you, 6 misuse patterns, citation language
- `indicator_catalog.md` (220) — all 22 indicators with formula, function type, orientation
- `special_cases.md` (324) — 15 domain quirks consolidated from project.yaml + code comments

**Engineering & operations** (4):
- `contributing.md` (329) — branch/PR conventions, test markers, calibration check
- `extending.md` (404) — adding indicator/source/geography/schema column with working code examples
- `api_clients.md` (236) — per-client docs (Census, CBP, EAVS, ARDA, POP)
- `operations.md` (337) — backup/restore, Alembic, multi-year DB queries, observability

### Bugs verified fixed (9 from quality-auditor verification pass)
1. `getting_started.md:123` "sum of z-scores" → "mean of z-scores"
2. `indicator_catalog.md` function counts wrong (12/3/3/1/1=20) → corrected (14/3/3/1/1=22)
3. Function names missing `_function` suffix in 3 files (`indicator_catalog.md`, `extending.md`, `methodology.md`)
4. `extending.md` broken `_calculate_one` example → replaced with working `_divide_function(row, source)` and corrected `_my_new_function` skeleton signature
5. `methodology.md` `_aggregate_scores` line 543 → 493
6. `special_cases.md` PR Limited English file location wrong (`indicators.py` → `aggregator.py:259-268` and `data_puller.py:409-417`)
7. `special_cases.md` pop change line numbers off by 1-2 (`:560/:561` → `:562-563`)
8. MANUAL_BINS framing inconsistency across 3 files ("four composite columns" → "five composite columns")
9. **Test count**: PCC discovery — auditor said 537, my grep said 531, pytest collects 541. Reverted bad "fix" that demoted 541 to 531; the original badge was correct.

### H1 audit issue verified still real
Confirmed at `src/core/indicators.py:222`: `_mean_function` uses `data[num_cols].mean(axis=1)` with no NaN mask, while `_divide_function` (line 186-187) and `_max_function` (line 217-218) explicitly mask. Doc note in methodology.md updated to cite line and confirm "still present as of this writing."

## Process Notes

### Multi-agent review pattern worked well
Four agents in parallel produced complementary findings (factual vs methodological vs operational vs adversarial) with minimal overlap. Each took 60-120s. Total time saved vs. doing it serially: ~6 minutes for ~25 minutes of analyst time.

### But agent claims need verification
**~30% of agent claims were themselves wrong**, including:
- "pipeline_guide.md is a broken link" (file exists)
- "run_tests.sh doesn't exist" (file exists)
- "Test count is 537" (actual is 541; auditor probably failed to count parametrize)

Pattern: spawn agents, verify their high-stakes claims against code (Bash grep), then act. Without verification, I would have made several incorrect "fixes."

### PCC at session-end caught a bug the verification pass missed
The auditor flagged "test count is wrong" with their own incorrect number (537). I checked my grep (531), accepted it, and "fixed" the badge from 541 → 531. But pytest --collect-only returns 541 because of parametrize expansion. PCC running actual pytest revealed this. Lesson logged.

## Next Steps

- **Push commits** (this session's commit + 0 prior unpushed)
- **CLAUDE.md** still references `src/core/calculator.py` (line 28) — should be `src/core/indicators.py`. Deferred from this session, worth a small follow-up commit
- **Distribute regenerated 2024 output** to FEMA RAPT team (deferred from prior session)
- **Draft RAPT write-up** of changes since Jan 30 (deferred from prior session)
- Consider running the new `decision-scientist` agent against current pipeline as a validation exercise (still deferred from 2026-04-08)
