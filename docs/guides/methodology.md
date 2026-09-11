# Methodology

How CRCI is constructed, why each design choice was made, and what the calibration targets do (and do not) validate.

For the *what* — file formats, tab-by-tab — see [outputs.md](outputs.md). For *limitations* — what CRCI can't tell you — see [limitations.md](limitations.md). For *terminology* — MAUT, ADCM, z-score — see [glossary.md](glossary.md).

---

## The pipeline in one diagram

```
Raw indicators (22 columns, mixed orientations)
        │
        ▼
  Reorient (apply 100 − x to "challenge" indicators)
        │   ──→ `pos` tab. All columns now point the same way: high = high resilience.
        ▼
  Mean-impute NaN (per indicator, using mean of available values)
        │
        ▼
  Z-score (per indicator)
        │   ──→ `scores` tab. Higher z = higher resilience.
        ▼
  Mean across indicators (equal weights)
        │   ──→ `agg` column. Higher = higher resilience.
        ▼
  Negate to produce challenge composite
        │   ──→ `cri` column = −`agg`. Higher = higher challenge.
        ▼
  Percentile-rank
            ──→ `cria_p` column. 0–1, higher = higher challenge percentile.

Then bin: indicators auto-selected (FisherJenks/EqualInterval/Quantiles/...);
the headline composite columns use manually-defined boundaries.
```

---

## Design choices and rationale

### Equal weights

All 22 indicators contribute equally to the composite. This is a **methodological choice**, not an oversight.

Rationale (from the FEMA partnership):
- No defensible empirical basis exists for a non-uniform weighting (no outcome variable to regress against).
- Equal weights are interpretable and politically neutral — every domain (housing, economics, healthcare, etc.) is treated as equally important.
- Sensitivity to weighting is bounded under z-score normalization: every indicator's marginal contribution is ±1σ per unit of input.

Consequence to be aware of: **correlated indicators implicitly double-count.** If three indicators all measure "economic distress" (e.g., Poverty, Unemployment, Median Income), the composite gives 3/22 of its weight to economic distress instead of 1/N-domains. Use the `corr` tab to see which indicators are highly correlated.

### Z-score normalization (not percentiles)

After reorientation, each indicator is z-scored: `(x − mean) / std`, computed across the geographies in scope. We use z-scores because:
- Z-scores preserve metric distance (a county 2σ above the mean really is twice as far as one 1σ above).
- Percentile rank discards distance information — the difference between the 90th and 95th percentile counties is invisible.
- Adding z-scores is statistically meaningful (their sum has known variance properties); adding percentiles is not.

Tradeoff: z-scores propagate outliers linearly into the composite. A single county with Z = +5 on Median Income shifts the composite measurably. The deprecated pipeline used z-scores; we preserve that for calibration reasons.

### Mean (not sum) for the composite

The composite (`agg`) is the **mean** of the 22 z-scores, not the sum. This matters because:
- Tribal output uses 17 indicators (not 22). A sum would not be comparable across geographies.
- The manual bin boundaries `MANUAL_BINS["agg"] = [-0.75, -0.25, 0.25, 0.75]` are unitless z-score offsets — only meaningful for a mean.

### Mean-imputation before z-scoring

Indicators with missing values for some geographies (e.g., Inactive Voter for non-reporting states) are mean-imputed with the indicator's average **before** z-scoring. This means missing values contribute z = 0 to the composite — they are treated as "average."

This is intentional but has a consequence: **a heavily-imputed indicator pulls the composite toward the mean.** The `n` tab shows pairwise sample counts; large gaps indicate where this matters most. For Inactive Voter specifically, ~14 states/territories don't report — their composite scores are biased toward the national mean for that indicator.

The display tab (`indicators`) preserves NaN so end-users see "no data" on the map. The internal composite uses imputed values. See the 2026-03-25 lesson in [`config/project.yaml`](../../config/project.yaml) for the implementation split.

### Orientation: high values = high resilience (then we flip for headline)

Indicators are stored in `config/indicators.yaml` in their natural direction (e.g., Poverty as "% in poverty"). The reference table's `Augment == "reverse"` column marks which 16 indicators need to be flipped via `100 − x` to produce the resilience-positive `pos` tab.

After this flip, all 22 columns point the same way: high = high resilience. The composite `agg` is computed in this resilience-positive space.

The headline columns (`cri`, `cria_p`) flip the polarity once more (`cri = −agg`) to express "challenge." The naming is historical — "CRI" originally stood for Community Resilience Index, but the column is now the challenge index (CRCI).

### Population Change is special-cased

`Population Change` (NETMIG) is treated differently from the other 21 indicators:
1. Z-score uses **subset stats** — only the geographies with non-NaN NETMIG values contribute to the mean and standard deviation. Otherwise the heavy NaN tail would skew the distribution.
2. The result is converted to `|z|` before contributing to the composite — so both rapid growth and rapid decline count as "instability."

This means `Population Change` is a **dispersion penalty**, not a directional signal. It cannot be interpreted on the same axis as the other 21 indicators. See [special_cases.md](special_cases.md#population-change-subset-z-scores) for details.

---

## The composite tab columns explained

| Column | Definition | Direction | When to use |
|--------|------------|-----------|-------------|
| `agg` | Mean of 22 z-scores | High = high resilience | Don't expose to end users; internal |
| `cri` | `−agg` | **High = high challenge** | Headline raw composite for ranking |
| `cria_p` | Percentile rank of `cri` | **High = high challenge percentile** | Headline ranked composite for mapping |
| `pop change` | `\|z(Population Change)\|` | High = unstable | Population stability proxy |
| `pop_p` | Percentile rank of `pop change` | High = unstable percentile | |

**Always sort by `cri` or `cria_p`** for "which counties are most challenged." Sorting by `agg` gives the *least* challenged.

---

## Calibration targets — what they do and do not validate

| Geography | Year | Target correlation | Source |
|-----------|------|--------------------|--------|
| County | 2022 | **0.94** | vs. deprecated reference pipeline (Argonne legacy) |
| County | 2023 | validated | (no correlation number; 3,222 counties match) |
| Tract | 2021 | **1.00** | vs. deprecated reference pipeline (perfect reproduction) |

### What calibration validates

- **Refactor reproducibility**: the current pipeline produces the same numbers as the deprecated original on the same input year. A code change that drops correlation below the target is a regression.
- **Numerical stability**: indicator formulas, orientation, NaN handling, z-score normalization, and aggregation are reproducible.

### What calibration does NOT validate

- **Construct validity**: that the 22 indicators actually measure community resilience. (No external validation exists.)
- **Predictive validity**: that high-CRCI counties experience worse disaster outcomes. (Out of scope; would require an outcome dataset.)
- **Selection bias**: that these 22 are the *right* 22. The set inherits from the original Argonne work; rationale lives in academic and FEMA-internal documents not in this repo.
- **Cross-year comparability**: see "Limitations" below.

A "0.94 correlation vs. baseline" should not be cited as evidence the methodology measures real resilience. It only evidences that we didn't break the math.

---

## Cross-year comparability

CRCI z-scores are recomputed each year against that year's distribution of geographies. A county's `cria_p` is a **within-year rank**, not an absolute level. Year-over-year changes in `cria_p` could reflect *other counties moving*, not the focal county.

If you need year-over-year comparison:
- Compare raw indicators (`indicators` tab), not z-scores or composites.
- Or compute z-scores against a fixed baseline year's distribution.
- Or use a longitudinal panel approach outside this pipeline.

The pipeline has no built-in cross-year normalization.

---

## Sensitivity to weighting

Equal weights are not perturbable through configuration. To run a leave-one-out or weight-perturbation analysis, you must use the Python API directly with a custom `weights` dict:

```python
from src.core.aggregator import AggregateIndicator

agg = AggregateIndicator(geography="county", bins=5)
results = agg.create_aggregate(
    indicators=indicators,
    reference=reference,
    geo_reference=geo_ref,
    weights={"Poverty": 2.0, ...},   # default is None = equal weights
)
```

The `weights` parameter is implemented in `src/core/aggregator.py:_aggregate_scores` (line 493) but is **not exposed** by `scripts/run_full_pipeline.py`. There is no built-in sensitivity report.

---

## Open methodological audit issues

These are tracked in [`config/project.yaml`](../../config/project.yaml) under `state.known_issues`:

### H1: `_mean_function` has no NaN mask

The other four indicator functions (`_divide_function`, `_max_function`, `_divide_scalar_function`, `_reverse_divide_function`) explicitly mask NaN to prevent partial-row calculations. `_mean_function` (in `src/core/indicators.py:222`) does not — it just calls `data[num_cols].mean(axis=1)`, which silently skips NaN. For Population Change with partial NETMIG availability across a row's columns, this means the mean is computed across whatever's available without warning. Affects only Population Change (the only `mean` indicator). Verified still present as of this writing.

### H2: `calc_z_scores` DataFrame vs. Series divergence

When called on a Series with zero standard deviation, `calc_z_scores` returns a Series of zeros. When called on a DataFrame with a zero-std column, that column returns NaN. The two paths diverge in undocumented ways. Affects degenerate distributions only.

Both issues are flagged for a future audit run via the `decision-scientist` agent.

---

## Further reading

- [outputs.md](outputs.md) — every workbook tab in detail
- [limitations.md](limitations.md) — what to be careful about when using CRCI in practice
- [special_cases.md](special_cases.md) — domain quirks (CT planning regions, PR Limited English, EAVS -88, Population Change handling)
- [glossary.md](glossary.md) — methodology terminology
- [`config/project.yaml`](../../config/project.yaml) — `lessons_learned` (every methodologically-relevant fix has a date and rationale)
- `.claude/agents/decision-scientist.md` — formal audit checklist used by the methodological-audit agent
