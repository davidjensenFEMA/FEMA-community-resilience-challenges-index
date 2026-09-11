# Proposal: Upstream Decision Science Module Review

**Date**: 2026-04-08
**Author**: proposer agent
**Task**: Upstream Review #1 — evaluate shared MAUT/MCDA module against CRIA architecture

---

## Problem

The shared `utils` repo has published a Decision Science module (MAUT scorer, sensitivity analysis, visualization, a decision-scientist agent, and a team template). The upstream update asks repos to assess whether they do MAUT/MCDA and, if so, whether to migrate.

CRIA computes a Community Resilience Composite Index (CRCI) from 22 indicators using z-score normalization and equal-weight additive aggregation. The question is not just "does CRIA do MAUT?" — it is: **what is the correct characterization of CRCI's aggregation math, and does the shared module improve anything that matters?**

---

## Codebase Context

### CRCI Aggregation Pipeline (`src/core/aggregator.py`)

The pipeline runs 10 steps:
1. Clean indicators (impute missing values, apply CT CBP / PR Limited English special cases)
2. Rescale fractions/indexes to 0–100
3. Bin individual indicators (5 bins county, 7 bins tract)
4. Reorient so higher = more resilient (reverse polarity for negative indicators)
5. Calculate z-scores across geographies
6. Aggregate: `agg = mean(z-scores)` — equal weights, no value function transformation
7. Bin aggregate scores (manual bins for `agg`, `cri`, `cria_p`)
8. Calculate percentile ranks
9. Identify lowest 3 resilience indicators per geography
10. Compute full 22×22 Pearson correlation matrix

Final CRCI outputs: `agg`, `cri = -agg`, `cria_p` (percentile), `pop change`, `pop_p`.

### What the Weights Are

Equal weights: each of the 22 indicators contributes 1/22 ≈ 0.0455 to `agg`. This is not stored as explicit weights anywhere in code or config — it is implicit in `pd.DataFrame.mean(axis='columns')` at `aggregator.py:544`.

### What Value Functions Are

None. Raw z-scores go directly into the additive sum. The reorientation step (negation for "reverse" indicators) is the only transformation applied before aggregation, and that is a sign flip to a z-score, not a utility function.

### Calibration Targets

- County: 0.94 average correlation (22 indicators, validated)
- Tract: 1.0 average correlation (17 indicators, perfect)

These are hard constraints. Any change to the aggregation step must not disturb these.

---

## Is CRCI Technically MAUT?

Partially. CRCI is additive aggregation with equal weights, but it **does not use value functions** — it aggregates z-scores directly. MAUT proper requires `U = Σ wᵢ × uᵢ(xᵢ)` where `uᵢ` maps raw values to utility in [0, 1]. CRCI skips the `uᵢ` step. The z-score normalization acts as an implicit standardization, not a deliberate utility elicitation.

This distinction matters because it determines which parts of the shared module are applicable and which would require fundamental changes to the pipeline.

---

## Approaches Considered

### Approach A: No adoption — status quo

Leave CRCI's pipeline untouched. The shared module is designed for scoring-and-ranking decisions (e.g., "which tactic to select"); CRCI is a measurement composite index, not a ranking decision.

**Pros**:
- Zero risk to calibration targets
- Zero implementation cost
- Honest: CRCI is not doing MAUT, so wrapping it in a MAUT scorer would be cosmetic
- The implicit equal-weight mean is FEMA's methodological choice, not a CRIA implementation decision — replacing it with explicit MAUT infrastructure would misrepresent the pipeline's character

**Cons**:
- Misses legitimate utility of sensitivity analysis and the decision-scientist agent
- Does not adopt the decision-scientist agent for auditing the existing implicit weighting

**Risk level**: None  
**Calibration impact**: None

---

### Approach B: Adopt sensitivity analysis + decision-scientist agent only (bold selective adoption)

Adopt two specific components without touching `aggregator.py`:

1. **`sensitivity.py` → CRIA-specific indicator sensitivity analysis** — adapt `one_at_a_time()` and `monte_carlo()` to answer: "if this indicator's weight increased from 1/22 to 2/22 (at the expense of another), which county rankings would flip?" This is a read-only diagnostic, not a pipeline change.

2. **`decision-scientist.md` → copy as a CRIA-adapted audit agent** — the agent's audit checklist is directly applicable: validate that implicit weights sum to 1.0 (they do, trivially), check whether reorientation is semantically correct (does `reverse` polarity always mean higher = more resilient?), and flag missing sensitivity coverage for production decisions.

**Pros**:
- Sensitivity analysis fills a genuine CRIA gap: we have a full correlation matrix but no analysis of how rank orderings change under weight perturbation
- The decision-scientist audit checklist catches exactly the class of issue in Audit H1 and H2 (`config/project.yaml` known_issues): silent NaN behavior in `_mean_function`, z-score divergence between DataFrame/Series paths
- No changes to the aggregation pipeline — calibration targets unaffected
- The agent is read-only — it cannot break anything

**Cons**:
- `sensitivity.py` cannot be used as-is: CRCI doesn't have alternatives in the MAUT sense (counties are observations, not decision options). An adaptation is needed
- The adaptation is non-trivial: must reframe sensitivity as "what if indicator weights varied?" not "which alternative ranks highest?"
- `decision-scientist.md` would need CRIA-specific language added — auditing z-score pipelines is not the same as auditing MAUT decision models

**Risk level**: Low (no pipeline changes; only new diagnostic tooling)  
**Calibration impact**: None if implemented as read-only diagnostics

---

### Approach C: Full MAUT migration — replace z-score aggregation with MAUTScorer

Replace `_aggregate_scores()` in `aggregator.py` with a `MAUTScorer` instance loaded from YAML. Define a value function for each of the 22 indicators, set explicit weights to 1/22, and use the `linear` value function with `[min_zscore, max_zscore]` bounds per indicator.

**Pros**:
- CRIA's aggregation would be config-driven and auditable by `decision-scientist`
- Enables non-equal weighting in the future (no code change needed, just YAML update)
- `explain()` on `DecisionResult` gives per-indicator breakdown for any geography — useful for stakeholder reporting

**Cons**:
- **Calibration risk is high**: z-score normalization and linear value function normalization are mathematically equivalent only when the min/max bounds match the observed data range — and those bounds shift every year as new data comes in. The current pipeline achieves 0.94 county correlation partly through consistent normalization across years.
- The existing `reverse` polarity handling (negate z-score for negative indicators) has no direct analog in MAUT: negative indicators need monotone-decreasing value functions, which must be configured in YAML. Getting this wrong silently would flip indicator contributions.
- Population Change is explicitly excluded from the normal z-score flow (`-abs(z-score)`) — this special case does not map to standard MAUT value functions without a custom implementation.
- Implicit weights are FEMA's methodological decision. Externalizing to YAML changes governance: someone now has to maintain and approve that YAML as part of FEMA's methodology, not just the code.
- Migration would require re-validating calibration targets from scratch — significant effort.

**Risk level**: High  
**Calibration impact**: Direct and substantial — calibration re-validation required

---

### Approach D: Adopt team template only

Copy `decision-science.md` team template into `.claude/teams/`. Use it for any future indicator development or weight-scheme experiments.

**Pros**:
- Zero risk — pure documentation
- Decision-science team provides domain correctness gating if CRIA ever adds weighted indicators
- Low effort (copy, CRIA-adapt descriptions)

**Cons**:
- Narrow value: CRIA doesn't currently have decisions in the MAUT sense
- The existing `indicator-development` team template already includes a proposer-led analysis step and quality-auditor review

**Risk level**: None  
**Calibration impact**: None

---

## Recommendation

**Adopt Approach B (selective adoption: sensitivity analysis + decision-scientist agent).**

Do not adopt Approach C. CRCI is a measurement index, not a decision ranking system, and migrating to MAUTScorer carries calibration risk with no methodological gain — FEMA's equal-weight additive index is already working.

Approach B is worth doing for two concrete reasons:

1. **The `lowest_ind` tab (added 2026-04-07) already surfaces the 3 worst resilience drivers per county.** The natural next question from FEMA stakeholders will be "how sensitive is this ranking to indicator weights?" One-at-a-time sensitivity analysis on indicator contributions directly answers that question and does not require pipeline changes.

2. **The decision-scientist audit checklist aligns precisely with CRIA's known open audits** (H1: NaN masking in `_mean_function`; H2: z-score DataFrame/Series divergence). A CRIA-adapted decision-scientist agent would approach these as correctness issues — which they are — rather than general code quality issues.

For the team template (Approach D): copy it if we ever need it, but do not add it now. `indicator-development` already covers the use case.

---

## Per-Component Adoption Decision

| Component | Adopt? | Rationale |
|-----------|--------|-----------|
| `scorer.py` (MAUTScorer) | No | CRCI is not a MAUT model; calibration risk not justified |
| `value_functions.py` | No | No value functions in CRCI pipeline; not applicable |
| `sensitivity.py` | Yes (adapted) | Fills genuine gap: indicator weight sensitivity for county rankings |
| `visualization.py` | Partial (tornado only) | `tornado_plot()` is directly useful for sensitivity results; radar/heatmap require ranking, not applicable |
| `decision-scientist.md` | Yes (adapted) | Audit checklist directly applicable to implicit-weight z-score pipelines |
| `decision-science.md` (team) | No | `indicator-development` template already covers this; low marginal value |
| YAML config schema | No | No YAML decision model to define; equal weights are implicit in pipeline |

---

## Open Questions

1. **Sensitivity reframing**: The shared `one_at_a_time()` expects alternatives (decision options), not geographies (observations). The CRIA adaptation must ask: "if indicator X had weight 2/22 and all others had weight 1/21 of the remainder, which county rankings flip?" Is this the right sensitivity question, or does FEMA care more about "which indicators contribute most to high/low CRCI scores" — which is already answered by `lowest_ind` and the correlation matrix?

2. **Scope approval**: Adapting `sensitivity.py` for CRIA requires new code in `src/core/` or a new `src/core/sensitivity.py`. This is out of scope for the proposer (read + `docs/` write only) and would need a `cria-analyst` + `statistical-tester` implementation wave.

3. **Decision-scientist agent scope**: The upstream agent audits YAML decision models. CRIA has no YAML decision model — it has implicit equal weights in Python code. A CRIA-adapted version should audit `_aggregate_scores()` and `_reorient_indicators()` for correctness, not YAML config. The audit checklist needs rewriting for this context before the agent is useful here.

4. **Population Change treatment**: If sensitivity analysis is ever adapted for CRCI, the `pop change` column's `−|z|` special case must be handled explicitly — it's excluded from the standard aggregation path and appears as a separate output column, not as an indicator weight in the CRCI composite.

---

## Validation Plan

If Approach B is approved:

1. **CRIA-adapted decision-scientist agent**: Before writing the agent, review `_aggregate_scores()`, `_reorient_indicators()`, and `_calc_z_scores()` line by line against the audit checklist. Document findings. Only then write the adapted agent definition.

2. **Sensitivity analysis adaptation**: Implement `sensitivity.py` adaptation as a standalone module with its own tests before integrating with the aggregator. Test against synthetic county data where the expected sensitivity is known analytically (e.g., a county where one indicator dominates its z-score).

3. **Calibration guard**: After any sensitivity module is added, run the full county pipeline and verify the `agg`/`cri`/`cria_p` outputs are bit-identical to pre-change outputs. The sensitivity module must be purely diagnostic — no side effects on the CRCI scores.

4. **Tornado plot validation**: Verify `tornado_plot()` renders correctly for CRIA's sensitivity output before committing matplotlib as a dependency.
