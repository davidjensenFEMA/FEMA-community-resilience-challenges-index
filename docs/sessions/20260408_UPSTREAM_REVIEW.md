---
date: 2026-04-08
tags: [#docs, #config, #feature]
status: complete
---

# Upstream Decision Science Review + Correlation Report Verification

**Date**: 2026-04-08
**Branch**: `main`
**Follows**: [20260407_RAPT_FEATURES.md](20260407_RAPT_FEATURES.md)

---

## Summary

Reviewed upstream Decision Science module (MAUT scorer, sensitivity analysis, decision-scientist agent, team template) from shared utils repo. Ran a 2-agent team (proposer + cria-analyst) to assess fit against CRIA's aggregation pipeline. Adopted one component (decision-scientist agent, heavily adapted for CRCI). Verified that yesterday's correlation matrix reports auto-populated correctly for county and tract.

## Upstream Review Decision

**Key finding**: CRCI is a degenerate MAUT model — equal weights, z-score normalization, additive aggregation. Full MAUTScorer adoption would add complexity without methodological gain and risk breaking calibration (0.94 county, 1.0 tract).

| Component | Decision | Rationale |
|-----------|----------|-----------|
| MAUTScorer | Skip | CRCI is a measurement index, not a decision model; calibration risk |
| value_functions.py | Skip | Z-scores are unbounded by design, not [0,1] |
| sensitivity.py | Defer | Real gap (no weight-perturbation analysis) but partially covered by lowest_ind + correlation matrix; lighter alternatives exist |
| visualization.py | Skip | CRIA outputs to Excel, not matplotlib |
| decision-scientist agent | **Adopt & adapt** | Audit checklist maps to open issues H1/H2; CRIA-specific rewrites for calibration, special cases, implicit weights |
| decision-science team | Skip | indicator-development template already covers this |
| YAML config schema | Skip | Equal weights are FEMA's methodological choice, implicit in code |

Full analysis: `docs/plans/upstream_decision_science_review.md`

## Changes Made

### Decision-Scientist Agent (`.claude/agents/decision-scientist.md`)

New CRIA-adapted agent — methodological auditor for the CRCI pipeline. Rewritten from the upstream generic MAUT auditor with:

- CRCI-specific audit checklist: implicit weight integrity, z-score normalization, indicator orientation, Population Change double-transformation, calibration regression
- All 5 special cases as domain constraints (CT CBP, PR Limited English, EAVS -88/-99, Pop Change subset z-scores, manual bins)
- Known issues H1 (NaN masking in _mean_function) and H2 (z-score DataFrame/Series divergence) as warning-level checks
- Read-only scope — audit agent never modifies code
- Clear role boundaries with quality-auditor (code quality) and cria-analyst (pipeline owner)

### Infrastructure Updates

- `.claude/README.md` — Added decision-scientist to agent catalog, scope matrix (6 columns), agent levels, directory tree
- `CLAUDE.md` — Updated agent count (5→6) and roster
- Deleted `.claude/upstream-update.md` after review

### Correlation Report Verification

Confirmed both formatted correlation reports auto-populated from yesterday's pipeline run:

| File | Sheets | Size | Sample |
|------|--------|------|--------|
| `data/output/reports/Correlation Matrix COUNTY.xlsx` | corr, p, zero, n | 22x22 | n=3,284 |
| `data/output/reports/Correlation Matrix TRACT.xlsx` | corr, p, zero, n | 22x22 | n=85,382 |

Both have human-readable labels (e.g., "Age over 65", "Low Educational Attainment"), formatted tables (TableStyleMedium2), and correct diagonal values (r=1.0).

## Agent Team Execution

### Team: upstream-review

| Agent | Type | Task | Result |
|-------|------|------|--------|
| proposer | proposer | Analyze upstream module vs CRIA architecture | Proposal with per-component decisions, open questions, validation plan |
| analyst | cria-analyst | Evaluate CRIA domain fit for MAUT concepts | Assessment: CRCI is degenerate MAUT, 60% of generic checks irrelevant, 5 CRIA-specific checks needed |
| team-lead | (self) | Synthesize and write adapted agent | decision-scientist.md with CRIA-specific audit checklist |

## Next Steps

- Push commits to origin/main (2 from last session + 1 from this session)
- Draft high-level write-up of code changes since Jan 30 (RAPT question #3 — still deferred)
- Investigate 3 county Inactive Voter values showing old imputed value
- Consider running decision-scientist agent against current pipeline as a validation exercise
