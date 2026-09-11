# Glossary

Terms that appear across the CRCI codebase, configs, and docs without always being defined inline.

---

## Methodology

### MAUT (Multi-Attribute Utility Theory)

A decision-theoretic framework for combining multiple attributes (indicators) into a single score, typically `score = Σ wᵢ · vᵢ(xᵢ)` where `wᵢ` are weights and `vᵢ` are value functions mapping each attribute to a [0,1] utility.

CRCI is a **degenerate MAUT model**: equal weights (`wᵢ = 1/22`), z-score normalization instead of value functions, and additive aggregation. "Degenerate" here means the structure is MAUT but the parameters are stripped to the minimum — there is no meaningful weighting decision and no value-function elicitation. The methodological consequence is that CRCI cannot answer "how much does Poverty matter relative to Hospitals?" — every indicator gets equal weight by design.

See [methodology.md](methodology.md#equal-weights) for the rationale.

### Z-score

The number of standard deviations a value lies from the mean of its reference distribution: `z = (x − μ) / σ`. A z-score of 0 = exactly average; ±1 = one standard deviation above/below; ±2 = two SD. CRCI z-scores are computed across the geographies in scope (counties, tracts, etc.) for each indicator separately.

A z-score is **dimensionless** — it discards the original units. This is why z-scores can be averaged across indicators with different units (% poverty, $ income, hospitals/10k pop) to produce the composite.

### Center-scaled ADCM + TSS

The binning method auto-select scoring function. ADCM = "Absolute Deviation around Class Median" (lower is better — measures how compact each bin is). TSS = "Total Sum of Squares" (lower is better — measures how well the bins discriminate).

Both are computed per candidate method, then **z-scored across methods** ("center-scaled"). The chosen method minimizes the combined `z(ADCM) + z(TSS)`. Without the z-scoring step, FisherJenks would win every binning decision because it optimizes for ADCM by design — the center-scaling forces a fair comparison.

See `src/core/binning.py:_auto_select_method`.

### Fisher z transform

A statistical transformation `z = arctanh(r)` used to compute confidence intervals around correlation coefficients. The transform makes the sampling distribution of `r` approximately normal, enabling the standard `r ± 1.96 · SE` interval construction.

In CRCI: used to compute the `zero` tab (significance flags) in the correlation report. `arctanh(1.0) = ∞`, so the diagonal of any correlation matrix produces a `RuntimeWarning` — functionally correct (`tanh(∞) = 1.0`), just noisy.

### Bin

An integer category assigned to a value based on which range it falls into. CRCI uses 5 bins for county/state/tribal and 7 for tract. The convention after orientation: **1 = least challenge, max = most challenge**.

### Mean-impute

Replacing NaN values with the column mean before further calculation. Used in CRCI before z-scoring so that geographies missing one indicator can still receive a composite score (their missing indicator contributes z = 0). The display tab (`indicators`) preserves NaN; the internal composite uses mean-imputed values.

---

## Pipeline

### CRCI / CRI / CRIA

- **CRCI** = Community Resilience Challenges Index. The current product name and what the published deliverable measures.
- **CRI** = Community Resilience Index. The legacy code name (still used as a column: `cri = -agg`). The legacy name is misleading — the column actually measures *challenge*, not resilience.
- **CRIA** = Community Resilience Indicator Analysis. The codebase / project name (FEMA CRIA). Refers to the toolkit, not the index.

When in doubt: the *product* is CRCI; the *toolkit* is CRIA; the *legacy column* is `cri`.

### Indicator

One of the 22 numerical measures computed per geography. Defined in [`config/indicators.yaml`](../../config/indicators.yaml). Each indicator has a name, source (ACS/CBP/EAVS/ARDA/POP), function type (`divide`/`reverse_divide`/`divide_scalar`/`max`/`mean`), numerator and denominator columns, and orientation (whether `Augment == "reverse"`).

### Composite

The single-number summary across all 22 indicators per geography. Stored in the `agg` tab as five derived columns: `agg`, `cri`, `cria_p`, `pop change`, `pop_p`. See [outputs.md "Composite columns"](outputs.md#composite-columns-the-agg-tab).

### Orientation / Augment

Whether an indicator's natural direction matches the resilience axis. Indicators where higher = more challenge (Poverty, Unemployment, etc.) are flagged `Augment == "reverse"` in the reference and get flipped via `100 − x` during aggregation, so all 22 columns end up pointing the same way (higher = higher resilience).

### Manual bin

A bin assignment that uses hard-coded boundaries (`pd.cut`) instead of the auto-select method pool. Used for `Median Income` (domain-meaningful dollar thresholds) and the five composite columns (`agg`, `cri`, `cria_p`, `pop change`, `pop_p`) — six columns total — to preserve cross-year comparability of map color schemes.

### Auto-select binning

The default — try multiple methods (`equal_interval`, `fisher_jenks`, `headtail_breaks`, `maximum_breaks`, `quantiles`, `std_mean`), score each by center-scaled ADCM+TSS, pick the winner. Recorded in `bin_meta.selected_method`.

---

## Geography

### GEO_ID prefixes

CRCI uses the Census Bureau's GEO_ID convention: a Summary Level prefix + `US` + the FIPS code.

| Prefix | Geography | Example | Note |
|--------|-----------|---------|------|
| `0500000US` | County | `0500000US01001` (Autauga, AL) | 5 bins by default |
| `1400000US` | Census Tract | `1400000US01001020100` | 7 bins by default |
| `0400000US` | State | `0400000US01` | 5 bins |
| `2500000US` | Tribal area (American Indian Area / Alaska Native Area) | `2500000US0010` | 5 bins, ACS-only |

The prefixes are critical for the D9/D10 filters in `scripts/run_full_pipeline.py` that strip cross-contamination from the DataPuller's outer merge.

### FIPS code

Federal Information Processing Standards code for a geographic area. State codes are 2 digits (`01` = Alabama, `06` = California). County codes are 5 digits (state + 3-digit county). Tract codes are 11 digits (county + 6-digit tract). Embedded inside the GEO_ID.

### Reference geography (`geo_reference`)

The DataFrame loaded from the per-level parquet files in `data/geographies/` (one per level: county, state, tract, tribal). Provides metadata columns (state name, county name, state_abbr) used for special-case lookups (e.g., CT planning regions, PR Limited English).

---

## Data sources

### ACS

American Community Survey (Census Bureau). The dominant data source — 17 of 22 CRCI indicators come from ACS. Released annually as 5-year rolling averages. The `ACS_YEAR` env variable refers to the *end year* of the 5-year window. Tract-level data requires per-state iteration.

### CBP

County Business Patterns (Census Bureau). Annual establishment counts by NAICS code. Used for Civil Org (NAICS 813410, civic organizations) and Hospitals (NAICS 622110). 1-2 year publication lag.

### EAVS

Election Administration and Voting Survey (U.S. Election Assistance Commission). Biennial state-level voter administration data. Used for Inactive Voter only. Returns a ZIP file containing CSVs (not direct CSV — see [special_cases.md #4](special_cases.md#4-eavs--88-does-not-apply-and--99-data-not-available)).

### ARDA

Association of Religion Data Archives (Penn State). Decennial (every 10 years) religious congregation membership counts. Used for Religion only. Local Excel file, not an API.

### POP

Population Estimates Program (Census Bureau). Annual population estimates including net migration (NETMIG). Used for Population Change only. Decade-based data files; year-clamping required.

---

## NAICS

North American Industry Classification System. Numeric codes for industry sectors. CRCI uses two specific NAICS codes from CBP:
- `813410` — Civic and Social Organizations
- `622110` — General Medical and Surgical Hospitals

`NAICS_YEAR=2017` is the latest stable revision used throughout.

---

## Database / infrastructure

### bulk_create

`src/db/repositories.py:bulk_create()` — SQLAlchemy Core `insert()` with batched executemany. Required for any large insert (88K tract rows). Direct ORM `session.add_all()` is dramatically slower (hours vs. seconds for tract scale).

### Alembic

The SQLAlchemy migration tool. CRCI uses it for schema versioning. `alembic upgrade head` applies pending migrations; `alembic revision --autogenerate -m "..."` creates a new migration from model changes.

### Pydantic settings

`src/config/settings.py` uses pydantic-settings to load `.env` into a typed `Settings` object. All CRCI configuration goes through this — there is no direct `os.getenv()` use in the pipeline code.

---

## Project / process

### CONOP

Concept of Operations. A short structured planning document used in CRCI for medium-complexity tasks. Lives in `docs/plans/`. Format adapted from military doctrine.

### TCS

Task-Condition-Standard. A universal task spec format. Used for individual tasks within a CONOP or as standalone work units. See `/task` slash command.

### Calibration

The validation that the current pipeline reproduces the deprecated reference pipeline's output. Targets: county 0.94 (2022), tract 1.00 (2021). See [methodology.md "Calibration targets"](methodology.md#calibration-targets--what-they-do-and-do-not-validate).

### Lesson learned

A documented insight from a past bug or design choice. Stored in [`config/project.yaml`](../../config/project.yaml) under `lessons_learned`, with date and rationale. The authoritative log of "things we know that are not obvious from the code."

---

## Quick reference

| Term | One-liner |
|------|-----------|
| MAUT | Multi-Attribute Utility Theory; CRCI is a degenerate version |
| z-score | `(x − μ) / σ`, dimensionless, used for indicator normalization |
| ADCM | Absolute Deviation around Class Median (binning quality metric) |
| TSS | Total Sum of Squares (binning quality metric) |
| Fisher z | `arctanh(r)`, used for correlation confidence intervals |
| CRCI | Community Resilience Challenges Index (the product) |
| CRI / cri | Legacy column name = `−agg` (high = high challenge) |
| CRIA | Community Resilience Indicator Analysis (the toolkit) |
| Augment | Reference column flagging which indicators need orientation flip |
| GEO_ID prefix | Summary Level code: `0500000US`=county, `1400000US`=tract, `0400000US`=state, `2500000US`=tribal |
| ACS / CBP / EAVS / ARDA / POP | The five data sources |
| NAICS | Industry classification codes (813410=civic, 622110=hospitals) |
| bulk_create | Fast batched DB insert (vs. slow ORM `add_all`) |
| Alembic | DB migration tool |
| CONOP | Concept of Operations (planning doc) |
| TCS | Task-Condition-Standard (task spec format) |
