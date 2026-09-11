# Outputs

What every workbook, tab, and column means.

If you just want to find the file, see [pipelines.md](pipelines.md). If something looks wrong, see [troubleshooting.md](troubleshooting.md).

---

## Where outputs land

```
data/output/
├── cria_inputs_<geo>.xlsx              # Raw source data
├── cria_indicators_<geo>_<year>.xlsx   # Calculated indicators
├── cria_results_<geo>_<year>.xlsx      # Indicators + bins + composite (the deliverable)
└── reports/
    └── Correlation Matrix <GEO>.xlsx   # Auto-generated, formatted correlation
```

`<geo>` is one of `county`, `state`, `tract`, `tribal`. `<year>` is the value of `--year`.

---

## `cria_inputs_<geo>.xlsx`

One tab per source API. The columns are the raw Census/CBP/EAVS/ARDA/POP variables — typically opaque IDs like `S0101_C01_001E` (Census ACS variable codes).

Useful when you need to:
- Verify the API actually returned what you expected
- Investigate a suspect indicator value (trace back to source)
- Re-derive an indicator with a different formula

You normally don't ship this file — it's an intermediate artifact.

---

## `cria_indicators_<geo>_<year>.xlsx`

The 22 indicator values per geography. One row per GEO_ID, one column per indicator.

Two important behaviors:

1. **NaN means "no data."** Missing values are intentionally not imputed in this file. If a state didn't report to EAVS, its `Inactive Voter` cell is blank. This is what FEMA wants for the public-facing display tab — blank cells render gray on the map.
2. **The CRCI pipeline uses a separate, mean-imputed copy internally** for composite scoring. So the same raw indicator value can be NaN here and a mean-fill value inside the `agg` calculation. This split is intentional ([2026-03-25 lesson](../../config/project.yaml)).

---

## `cria_results_<geo>_<year>.xlsx` — the deliverable

For county/state/tract this workbook has **16 tabs**. For tribal it has **6 tabs** (binning only — no z-scores, no composite).

### Tab-by-tab

| Tab | Content | Notes |
|-----|---------|-------|
| `ref` | The 22 indicator definitions, sources, function types, and per-source years | First tab — orientation for analysts |
| `years` | The full year configuration (`acs`, `cbp`, `pop`, `naics`, `asarb`, `acs_labels`) | Lets you reproduce the run from the file alone |
| `indicators` | Raw indicator values as collected, NaN preserved | The display tab — what shows on the map |
| `pos` | Reoriented indicators: **higher = higher resilience** | "Challenge" indicators (Poverty, Unemployment, etc.) are flipped via `100 − x` so all 22 columns point the same direction |
| `scores` | Z-scores of `pos` (mean-imputed first) | Higher z = higher resilience. See [methodology.md](methodology.md) for why z-scores not percentiles |
| `scores_percentiles` | Percentile rank of each z-score | Easier to read than raw z-scores |
| `lowest_ind` | Top 3 highest-challenge contributors per geography | Computed via `np.argsort` on z-scores; "lowest" means lowest resilience |
| `agg` | Composite columns: `agg`, `cri`, `cria_p`, `pop change`, `pop_p` | See "Composite columns" below |
| `bin_labels` | Each indicator binned 1–5 (or 1–7 for tract) | After orientation: 1 = least challenge, max = most challenge |
| `bin_meta` | Bin boundaries and method per indicator | Includes `selected_method` and `selected_score` for auto-selected binning |
| `agg_labels` | The composite columns binned 1–5 (or 1–7) | The headline "challenge tier" per geography |
| `agg_meta` | Composite binning boundaries and method | |
| `corr` | 22×22 Pearson correlation matrix between indicators | Human-readable labels |
| `p` | 22×22 p-values | Two-sided test; sample size is per-pair (NaN-aware) |
| `zero` | 22×22 significance flags | `1` if Fisher z 95% CI excludes zero, else `0` |
| `n` | 22×22 pairwise sample sizes | Reflects NaN handling per pair |

### Composite columns (the `agg` tab)

The `agg` tab contains five derived columns — read carefully, the polarities differ:

| Column | Definition | Polarity | Use for |
|--------|------------|----------|---------|
| `agg` | **Mean** of the 22 z-scores (after orientation) | High = high resilience | Internal — input to `cri` |
| `cri` | `−agg` (Community Resilience Index, named for legacy reasons) | **High = high challenge** | Headline raw composite |
| `cria_p` | Percentile rank of `cri` (0–1) | **High = high challenge percentile** | Headline ranked composite |
| `pop change` | `\|z(Population Change)\|` | High = unstable (either direction) | Population stability proxy |
| `pop_p` | Percentile rank of `pop change` | High = unstable percentile | Population stability proxy |

Notes on polarity:
- The composite is a **mean** of z-scores, not a sum. This makes the composite scale-invariant to the number of indicators — important for the manual bin boundaries (`MANUAL_BINS["agg"] = [-0.75, -0.25, 0.25, 0.75]`) to be meaningful.
- The naming is historical: "CRI" = "Community Resilience Index" but the column actually measures *challenge* (because of the `-agg` flip). The product is now called CRCI to reflect this.
- For ranking counties: use `cri` or `cria_p`. For mapping bins: use `agg_labels` (which uses `MANUAL_BINS["agg"]` with `reverse: True` so a label of 5 = highest challenge tier).

### How bins work

The `bin_labels` columns assign each row an integer category. After orientation, the convention is **1 = least challenge, max = most challenge**. So:
- A county with `Poverty_bins = 5` is in the highest-poverty quintile.
- A county with `Owner Occupied_bins = 5` is in the highest-challenge quintile, which (after the orientation flip) means the *lowest* owner-occupancy quintile.

For the composite: `agg_labels` column 5 = highest-challenge tier (the manual `agg` bin uses `reverse: True` to invert the natural ordering of the resilience-positive `agg` value).

**Manual bins** are used for one indicator (`Median Income`) and the five derived composite columns (`agg`, `cri`, `cria_p`, `pop change`, `pop_p`) — six columns total:

| Column | Type | Why manual |
|--------|------|------------|
| `Median Income` | Indicator | Domain-meaningful dollar thresholds (`25k / 50k / 75k / 100k`) |
| `agg` | Composite | Preserves bell-curve distribution from the deprecated pipeline |
| `cri` | Composite | Same |
| `cria_p` | Composite | Same |
| `pop change` | Composite | Domain-meaningful dispersion thresholds |
| `pop_p` | Composite | Same |

These columns bypass auto-select and use `pd.cut` with the hard-coded boundaries in `BinningEngine.MANUAL_BINS`.

For everything else, the binning engine auto-selects from a candidate pool of six methods: `equal_interval`, `fisher_jenks`, `headtail_breaks`, `maximum_breaks`, `quantiles`, `std_mean`. (`jenks_caspall` is excluded — historic infinite-loop bug; `natural_breaks` is excluded — non-deterministic; `percentiles` is excluded — always-zero scores in the deprecated original.) Methods are scored by **center-scaled ADCM + TSS** (z-scored across methods so no single method wins by default). The selected method is recorded in `bin_meta.selected_method`. See [methodology.md](methodology.md) for the rationale.

### What's *not* in `cria_results_*.xlsx`

- Geography metadata (state, county names) is merged in via the `include_geo=True` flag in `save_to_excel`. By default it's on.
- Population counts are not included as a column — pull them from the `cria_inputs_*.xlsx` if needed (`S0101_C01_001E`).

---

## Tribal output is different

Tribal runs produce a 6-tab workbook with:
- `ref`, `years`, `indicators`, `bin_labels`, `bin_meta`
- A `data` tab with the source data (replicates the deprecated tribal pipeline)

Reasons:
- **No aggregation** — tribal areas don't get a composite CRCI score (deprecated convention).
- **No non-ACS indicators** — CBP, EAVS, ARDA, POP indicators are dropped entirely. Only the 17 ACS-sourced indicators survive.
- **Zero-population GEOs are filtered out** before binning to prevent degenerate bins, then re-indexed to NaN in the final output.

---

## Correlation report (`data/output/reports/Correlation Matrix <GEO>.xlsx`)

Auto-generated whenever `cria_results_*.xlsx` contains correlation data (county and tract runs). Four tabs:

| Tab | Content |
|-----|---------|
| `corr` | 22×22 Pearson r |
| `p` | p-values |
| `zero` | significance flags (1 if 95% CI excludes 0) |
| `n` | pairwise sample sizes |

All four use human-readable indicator labels (e.g. "Age over 65", not `S0101_C01_030E`) and are formatted as Excel tables (`TableStyleMedium2`) for easy filtering.

The diagonal is always r = 1.0 by construction. You may see an `arctanh(1.0)` `RuntimeWarning` in the logs from the Fisher z transform on the diagonal — functionally correct (`tanh(inf) = 1.0`), just noisy.

---

## Reading the workbook in Python

```python
import pandas as pd

# Load the deliverable
results = pd.read_excel("data/output/cria_results_county_2024.xlsx", sheet_name=None, index_col=0)

# results is a dict of DataFrames keyed by tab name
indicators = results["indicators"]      # raw values, NaN preserved
agg = results["agg"]                    # has columns: agg, cri, cria_p, pop change, pop_p
agg_labels = results["agg_labels"]      # composite columns binned 1–5

# Top 10 highest-challenge counties (use cri — high cri = high challenge)
top10 = agg.sort_values(by="cri", ascending=False).head(10)

# Or use percentile rank (cria_p), which is bounded 0–1
top10_pct = agg.sort_values(by="cria_p", ascending=False).head(10)
```

For programmatic indicator-by-indicator analysis, prefer the `indicators` tab. For headline rankings, sort by `cri` (raw) or `cria_p` (percentile). Do NOT sort by `agg` for "highest challenge" — `agg` is resilience-positive (high `agg` = high resilience).

---

## Older outputs

Files named `cria_indicators_<geo>_<year>.pkl` are pickled DataFrames from earlier sessions. Treat them as historical artifacts — the canonical format is `.xlsx`. Use `pd.read_pickle()` if you need to compare against an older run.

The `data/output/archive_pre_fix/` and `data/output/archive_pre_tribal_fix/` directories contain pre-bug-fix outputs preserved for regression comparison. Don't overwrite them.
