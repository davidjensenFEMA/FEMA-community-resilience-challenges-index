# Limitations

What CRCI can't tell you. Common misuses. Things to be careful about when citing CRCI scores in policy or planning.

For the methodology that produces these limitations, see [methodology.md](methodology.md).

---

## What CRCI is

CRCI is a **descriptive composite index** that summarizes 22 community resilience challenge indicators into a single per-geography score. It is:

- Reproducible (calibration against a frozen baseline)
- Standardized (same indicator definitions across geographies and years)
- Comparable within a year (z-scored against that year's distribution)

CRCI is constructed on the assumption that aggregating well-validated indicators produces a useful summary signal. That assumption has not been independently tested against disaster outcomes within this project.

---

## What CRCI is NOT

### A predictor of disaster outcomes

CRCI was not validated against any outcome variable (disaster damage, recovery time, casualties). A "high CRCI" county is not statistically associated with worse outcomes in any test internal to this project. The composite is a summary of *measured challenges*, not a forecast.

### A measure of risk

Risk = hazard × exposure × vulnerability. CRCI captures **vulnerability** indicators (poverty, age, disability, broadband access, etc.) but does not include hazard exposure (flood zones, earthquake faults, hurricane paths). A low-CRCI county on the Florida coast is not "low risk" — it is "low vulnerability."

### A causal model

The composite is additive and equal-weighted. It cannot answer "which intervention would most reduce challenge?" — adding a hospital does not deterministically lower a county's CRCI by a known amount.

### Cross-year comparable (without caveat)

Z-scores are recomputed each year against that year's distribution. A county's CRCI percentile (`cria_p`) is a **within-year rank**. Year-over-year changes reflect both the focal county's movement *and* the rest of the country's movement. See [methodology.md "Cross-year comparability"](methodology.md#cross-year-comparability).

If you need year-over-year comparison, prefer:
- Raw indicator values (the `indicators` tab) — these are directly comparable
- A fixed-baseline z-scoring (compute z-scores against a single reference year's stats; not built into the pipeline)

### A precise estimate

The underlying ACS variables carry margins of error (MOEs) that are not propagated through CRCI. A county's `cria_p = 0.83` is reported as a fact but the underlying inputs may have ±10% MOEs. Treat CRCI as a **rough quintile/septile signal**, not a precise rank.

The `corr` and `n` tabs in the output workbook show pairwise sample sizes — heavily-imputed indicators contribute less reliable signal but are weighted equally with well-measured ones.

---

## Common misuses

### Misuse 1: Sub-bin ranking

> "Within the top quintile, our county is ranked 47th — we should target counties 40–50."

The top quintile is statistically indistinguishable internally — all those counties had the same bin assignment for a reason. Ranking within a bin treats noise as signal. **Use CRCI to identify the high-challenge bin; use other criteria to prioritize within it.**

### Misuse 2: Causal interpretation

> "Our CRCI dropped from 0.82 to 0.79 after the 2023 broadband expansion — the program worked."

CRCI changes year-over-year because:
- The focal county's indicators changed (any number of factors)
- The rest of the population's indicators changed (rebasing the z-score distribution)
- ACS data was revised
- Methodology was tweaked

A single-year delta is not evidence of a causal effect. You need a counterfactual comparison group and a designed evaluation.

### Misuse 3: Treating CRCI as an outcome variable

> "We regressed disaster recovery time on CRCI and got a strong relationship."

CRCI is itself a composite of input indicators (poverty, education, etc.), which independently predict recovery time. Regressing recovery on CRCI is regressing on the inputs collapsed into one number — it discards the very information you need for causal inference. Use the underlying indicators, not the composite.

### Misuse 4: Cross-deliverable comparison

> "County X is in the 90th percentile this year but the 75th percentile in last year's release."

Different release years use different ACS vintages, may have schema changes, may have indicator changes (e.g., adding a 23rd indicator), and rebase the z-score distribution. Cross-release comparisons of percentiles are not meaningful without knowing the deliverable history.

### Misuse 5: Tribal-county comparison

> "Tribal area X has a higher Hospitals score than County Y."

Tribal output drops the 5 non-ACS indicators (Hospitals included). Tribal CRCI cannot be directly compared to county CRCI — the indicator sets are different. See [special_cases.md #7](special_cases.md#7-tribal-pipeline-drops-non-acs-indicators).

### Misuse 6: Citing the calibration target as construct validity

> "CRCI has a 0.94 correlation with the FEMA baseline — so it's well-calibrated."

The 0.94 figure validates that the current pipeline reproduces the deprecated reference pipeline's output. It does NOT validate construct validity (do the indicators measure resilience?), predictive validity (do CRCI scores forecast outcomes?), or selection validity (are these the right 22 indicators?). See [methodology.md "Calibration targets"](methodology.md#calibration-targets--what-they-do-and-do-not-validate).

---

## Known methodological asymmetries

### Population Change is a dispersion penalty

`Population Change` is the only indicator processed asymmetrically — z-scored against a non-NaN subset, then converted to `|z|`. It penalizes both rapid growth and rapid decline as "instability." See [special_cases.md #5](special_cases.md#5-population-change-subset-z-scores).

This means Population Change cannot be interpreted on the same axis as the other 21 indicators. A county with `Population Change = 2.5` is "unstable by 2.5σ in either direction," not "less resilient by 2.5σ."

### Heavily-imputed indicators pull toward the mean

If an indicator is missing for ~15% of geographies (e.g., Inactive Voter for non-reporting states), those geographies' missing values are mean-imputed before z-scoring. They contribute z = 0 to the composite — i.e., "average."

For a state where Inactive Voter is one of 22 indicators, this means ~1/22 of the composite is hard-coded to "average" regardless of actual conditions. The `n` tab in the output workbook shows pairwise sample sizes — heavily-imputed indicators show up with smaller `n` values.

### Tract non-ACS indicators are county-imputed

The 5 non-ACS indicators (Civil Org, Hospitals, Inactive Voter, Population Change, Religion) don't exist at tract level. They are **imputed from the parent county** — every tract in a given county has identical values for those 5. See [special_cases.md #10](special_cases.md#10-tract-pipeline-imputes-non-acs-indicators-from-parent-county).

This means tract-level CRCI variation within a county is driven entirely by the 17 ACS indicators. The 5 non-ACS indicators are a constant per county.

### Equal weights mean correlated indicators double-count

Three indicators measuring economic distress (Poverty, Unemployment, Median Income) collectively contribute 3/22 of the composite weight, even though they share substantial variance. The composite is biased toward whichever conceptual domain has the most indicators.

To check this in your data, look at the `corr` tab. Highly correlated pairs (|r| > 0.7) signal that the composite is implicitly over-weighting that domain.

---

## Open audit issues

These are tracked in [`config/project.yaml`](../../config/project.yaml) under `state.known_issues` and have not yet been resolved:

### H1: `_mean_function` no NaN mask

`_mean_function` (used only by Population Change) does not explicitly mask NaN across input columns. Partial-row NETMIG uses whatever's available, silently. Could produce subtle bias in counties with partial NETMIG data.

### H2: `calc_z_scores` DataFrame/Series divergence

Zero-std columns return NaN in DataFrame mode but zero in Series mode. Affects degenerate distributions. Documented divergence; impact bounded but undocumented.

### CT planning region tract attribution

When a tract looks up its parent county for non-ACS indicator imputation, the dedup keeps the first matching `(state, county)` row. For CT, this means tracts in old counties may pick up state-level CBP values rather than the new planning region's actual data.

These issues are logged for review by the `decision-scientist` agent in a future audit pass.

---

## When to NOT use CRCI

CRCI is not the right tool for:

- **Hazard-specific risk assessment** — no exposure data
- **Acute crisis response** — composite is too coarse for tactical decisions
- **Causal evaluation** — additive composites don't support causal inference
- **Sub-bin ranking** — within-bin differences are noise
- **Cross-year point estimates** — z-scores rebase annually
- **Predicting individual outcomes** — population-level signal, not individual-level

Use CRCI for:

- Identifying broad geographic patterns of community challenge
- Stratifying counties/tracts into intervention priority tiers (top-bin vs. bottom-bin)
- Communicating composite challenge to non-technical stakeholders (with caveats)
- Year-over-year comparison of *raw indicator values* (NOT composites)

---

## How to cite CRCI responsibly

Recommended citation form:

> Community Resilience Challenges Index (CRCI), {year} release. FEMA Community Resilience Indicator Analysis toolkit, version {version}. https://[repo URL].

Recommended caveat language for any external use:

> CRCI is a composite of 22 community resilience challenge indicators with equal weights and z-score normalization. Scores are within-year ranks against the national distribution and are not directly comparable across years or against external indices without normalization. CRCI does not predict disaster outcomes; see methodology documentation for limitations.

---

## Further reading

- [methodology.md](methodology.md) — design choices and rationale
- [special_cases.md](special_cases.md) — domain quirks
- [`config/project.yaml`](../../config/project.yaml) — `lessons_learned` (every methodologically-relevant fix)
- `.claude/agents/decision-scientist.md` — formal methodological audit checklist
