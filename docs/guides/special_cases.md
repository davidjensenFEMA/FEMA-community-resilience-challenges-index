# Special Cases

A consolidated reference for the domain quirks and exceptions handled inside the CRCI pipeline. Most of these were learned through bug fixes and now have automated handling — listed here so you don't waste time re-investigating them when reviewing source data, debugging output, or extending the pipeline.

For shorter "is this a bug?" answers, see [troubleshooting.md](troubleshooting.md). For why these special cases matter methodologically, see [methodology.md](methodology.md). The authoritative log of when each was discovered lives in [`config/project.yaml`](../../config/project.yaml) under `lessons_learned`.

---

## 1. Connecticut planning region restructuring (2022→)

### What

In 2022, Connecticut abolished county government and replaced it with **9 planning regions** (FIPS codes `09110`–`09190`). The Census API and CBP data sources are still mid-transition:
- The Census still emits the 9 *old* counties (`09001`–`09015`) for some endpoints, alongside the 9 new planning regions.
- CBP 2022 has 18 CT entries — 9 old + 9 new — for a total of 18 CT rows.
- CBP 2023 begins reporting actual data for the new planning regions.
- ARDA's religion data still uses the old county boundaries.

### How CRCI handles it

`scripts/run_full_pipeline.py:_impute_tract_from_county` deduplicates on `(state, county)` (`keep="first"`) so the merge does not expand rows. The implication: when a CT tract looks up its parent county for a non-ACS indicator, it inherits whichever CT row sorted first — which means old counties get state-level uniform CBP values for older years.

### Where to look

- Source data: `cria_inputs_county.xlsx` — CBP columns for CT have suspicious uniformity in 2022.
- Indicator output: Civil Org and Hospitals for old CT counties (`09001`–`09015`) will be identical in 2022; differentiation begins in CBP 2023.
- Code: `scripts/run_full_pipeline.py:120` (deduplication step).

### When this becomes a real problem

If you are doing a year-over-year diff on CT-specific Civil Org or Hospitals, expect a discontinuity at CBP year 2022→2023. This is the data, not a bug.

---

## 2. Connecticut CBP 2022 zeros

### What

The 2022 CBP file has *zero* values for old CT counties (instead of NaN) because CBP was migrating to the new planning regions and emitted empty cells as zeros. A literal zero would propagate as a real `0.0` indicator value, mistakenly suggesting "no businesses."

### How CRCI handles it

`src/api/cbp_client.py` converts CT 2022 zeros to NaN before the indicator is calculated. The Civil Org and Hospitals indicators for those counties become NaN (not zero) and are mean-imputed in the composite, displayed as blank in the `indicators` tab.

### Where to look

- Lesson date: 2025-10-30 (`config/project.yaml` lessons_learned).
- Code: search for `Connecticut` or `CT` in `src/api/cbp_client.py`.

---

## 3. Puerto Rico Limited English

### What

The ACS `Limited English` indicator measures the proportion of the population with limited English proficiency. In Puerto Rico, where Spanish is the primary language, the entire population would register as "limited English" by ACS criteria — which is meaningless as a community resilience signal.

### How CRCI handles it

PR's Limited English indicator is set to **NaN** (excluded from the calculation), not zero. The user sees blank for PR on the Limited English tab; the composite mean-imputes PR's missing value.

### Where to look

- Lesson date: 2025-10-30.
- Reference: `config/indicators.yaml` Limited English `notes` field.
- Code: handled in two places:
  - `src/core/aggregator.py:259-268` (`_clean_indicators` — sets PR rows to NaN before scoring; uses `state == 72`)
  - `src/core/data_puller.py:409-417` (post-process step on the Limited English source column)
- The `exceptions` parameter passed to `AggregateIndicator.create_aggregate()` is unrelated — see `BINNING_EXCEPTIONS` in `scripts/run_full_pipeline.py:49` (that's per-indicator binning method exclusions, not PR handling).

---

## 4. EAVS `-88` (does not apply) and `-99` (data not available)

### What

The Election Administration and Voting Survey (EAVS) uses sentinel codes:
- `-88` means "does not apply" (state didn't conduct that program)
- `-99` means "data not available"
- Genuine zeros mean zero.

A naive pipeline would treat `-88` as a numeric `-88`, producing nonsense indicator values. An earlier version mapped `-88 → 0`, which produced false "Inactive Voter = 0%" values for ~14 non-reporting states/territories (`0/0` arithmetic).

### How CRCI handles it

`src/api/eavs_client.py` maps both `-88` and `-99` to **NaN**. The Inactive Voter indicator is NaN for non-reporting states; their bin labels are NaN; the composite mean-imputes them.

Additionally, `scripts/run_full_pipeline.py:_nullify_zero_vote_states` post-processes `bin_labels` to set `Inactive Voter_bins` to NaN for any state where the sum of `A1a × A1c` (registered × inactive) is zero — catching another flavor of "no data" not caught by the `-88`/`-99` mapping alone.

### Where to look

- Lesson date: 2026-03-25.
- Code: `src/api/eavs_client.py` and `scripts/run_full_pipeline.py:150` (`_nullify_zero_vote_states`).
- Affected states (typical): AL, HI, ME, MD, NH, OK, OR, RI, SC, UT, VT, WA, WI, WY plus territories. Exact set varies by EAVS year.

---

## 5. Population Change subset z-scores

### What

The `Population Change` indicator is sourced from POP (Population Estimates Program) NETMIG data. NETMIG availability is sparse — many geographies have NaN. Computing z-scores against the full geography list (with most NaN) would produce a degenerate distribution centered near zero and bias the indicator's contribution to the composite.

### How CRCI handles it

Z-scores for Population Change are computed against the **subset** of geographies with non-NaN NETMIG values, not the full geography list. The result is then converted to **`|z|`** before contributing to the composite — so both rapid growth and rapid decline contribute equally as "instability."

### Implication

Population Change is a **dispersion penalty**, not a directional signal. You cannot interpret its z-score the same way as the other 21 indicators. A county with `Population Change = 2.5` is not "2.5σ less resilient" — it's "in the unstable tail by 2.5σ."

This three-step transformation (subset z-score → `|z|` → equal-weight contribution) is acknowledged in the methodology audit as a known asymmetry. See [methodology.md](methodology.md#population-change-is-special-cased) and `_aggregate_scores` in `src/core/aggregator.py:493` (the `pop change` and `pop_p` columns are computed at lines 562–563).

### Where to look

- Lesson date: pre-2025-12 (deprecated pipeline behavior preserved).
- Code: `src/core/aggregator.py:562-563` (`pop change` and `pop_p` columns), `src/core/transformations.py` (z-score subset logic).
- Reference: `config/indicators.yaml` Population Change `notes` field.

---

## 6. ARDA `POP` column year-aliasing

### What

The ARDA religion data file has a `POP{year}` column (e.g., `POP2020`, `POP2010`) for the population denominator. The column name changes by decennial release.

### How CRCI handles it

`src/api/external_clients.py` (ARDAClient) renames the year-specific `POP{year}` to a generic `POP` alias on load. Indicators reference `POP` regardless of decade.

### Where to look

- Lesson date: 2025-12-03.
- Code: `src/api/external_clients.py` ARDA section.
- Reference: `config/indicators.yaml` Religion `notes` field.

---

## 7. Tribal pipeline drops non-ACS indicators

### What

Tribal areas (GEO_ID prefix `2500000US*`) only have ACS-derived data at scale. CBP, EAVS, ARDA, and POP do not publish at the tribal level. The deprecated pipeline simply dropped those 5 indicators for tribal output.

### How CRCI handles it

In `scripts/run_full_pipeline.py:478`, when `geography == "tribal"`, the pipeline drops the 5 non-ACS indicator columns entirely (Civil Org, Hospitals, Inactive Voter, Population Change, Religion). Only **17 ACS indicators** survive.

Tribal also runs with `skip_aggregation=True` — no z-scores, no composite CRCI. Output is binning-only (6 tabs: ref, years, indicators, bin_labels, bin_meta, data).

### Where to look

- Lesson date: 2026-03-05.
- Code: `scripts/run_full_pipeline.py:478` (drop) and `:530` (`skip_aggregation`).
- Output: `cria_results_tribal_*.xlsx` — note the 17-column indicators tab.

---

## 8. Tribal zero-population GEO filtering

### What

The tribal pipeline historically included zero-population tribal GEOs (places with no ACS data at all). When mean-imputed, these became identical to the global mean — making 82% of tribal rows fall into the same bin (degenerate output).

### How CRCI handles it

Before binning, `scripts/run_full_pipeline.py:494` filters tribal indicators to non-zero-population rows (using `S0101_C01_001E` from ACS Age & Sex). The filtered rows are removed from binning, then re-indexed back to NaN in the final output (so the workbook still has every tribal GEO_ID, with bins set to NaN for the dropped rows).

### Where to look

- Lesson date: 2026-03-04 (D8).
- Code: `scripts/run_full_pipeline.py:494` (filter) and `:541` (re-index).

---

## 9. DataPuller outer-merge contamination

### What

`DataPuller.pull_all_data()` does an outer merge across all source DataFrames. Because some sources (CBP, ARDA) emit county-format GEO_IDs and others (Census ACS) emit tract-format, the outer merge introduces mixed rows — county-format GEO_IDs end up in tract output, and tribal output gets county-format rows from ARDA POP.

### How CRCI handles it

Two filters in `scripts/run_full_pipeline.py`:
- **D9 (line 444)**: For `tract`, keep only GEO_IDs starting with `1400000US`.
- **D10 (line 461)**: For `tribal`, keep only GEO_IDs starting with `2500000US`.

Without these filters, tract output had ~88,597 rows (3,215 contaminated); after filtering, ~85,382 tract-only rows.

### Where to look

- Lesson date: 2026-03-04 session 2.
- Code: `scripts/run_full_pipeline.py:444` (tract) and `:461` (tribal).
- GEO_ID prefix reference: see [glossary.md](glossary.md#geo_id-prefixes).

---

## 10. Tract pipeline imputes non-ACS indicators from parent county

### What

CBP, EAVS, ARDA, and POP do not publish at the tract level. To produce tract-level CRCI scores that include all 22 indicators, the pipeline imputes the 5 non-ACS indicators from the parent county.

### How CRCI handles it

`scripts/run_full_pipeline.py:_impute_tract_from_county` (line 68) does a left join: for each tract, look up its `(state, county)` parent in the county-level indicators DataFrame and copy the 5 non-ACS values.

### Implication

All tracts in a given county will have **identical** Civil Org, Hospitals, Inactive Voter, Population Change, and Religion values. This is by design. The tract-level signal in those indicators is at the county granularity.

### Where to look

- Lesson date: 2026-03-04 (D1).
- Code: `scripts/run_full_pipeline.py:68`.

---

## 11. JenksCaspall infinite loop on degenerate data

### What

The `mapclassify.JenksCaspall` algorithm enters an infinite loop on data with many duplicate values (degenerate distributions). Bug #8 from the December 2025 calibration testing.

### How CRCI handles it

`jenks_caspall` is **excluded** from the binning method auto-select pool. `BinningEngine._auto_select_method` uses `equal_interval, fisher_jenks, headtail_breaks, maximum_breaks, quantiles, std_mean`. `FisherJenks` is a drop-in replacement.

### Where to look

- Lesson date: 2025-12-05.
- Code: `src/core/binning.py:423` (the methods list).

---

## 12. POP year clamping

### What

The POP (Population Estimates Program) NETMIG data is published as `NETMIG{year}` columns inside a per-decade file. Requesting `NETMIG2018` from a file released for 2024 causes a "missing column" error if the year isn't clamped to the file's decade.

### How CRCI handles it

`src/api/external_clients.py` POPClient clamps the requested year to the decade base before constructing the column name.

### Where to look

- Lesson date: 2026-02-17.
- Code: `src/api/external_clients.py` POPClient `_resolve_year` or similar.

---

## 13. Manual bin boundaries (one indicator + five composite columns)

### What

Six columns bypass the binning method auto-select and use hard-coded `pd.cut` boundaries. This preserves bell-curve distributions from the deprecated pipeline (important for cross-year visual comparability of map color schemes).

### How CRCI handles it

`src/core/binning.py:MANUAL_BINS` defines boundaries for: `Median Income, agg, cri, cria_p, pop change, pop_p`. `BinningEngine._apply_manual_bins` (line 336) detects these column names and routes to manual bins.

### Where to look

- Lesson date: 2026-03-19.
- Code: `src/core/binning.py:20-47`.
- See: [outputs.md "How bins work"](outputs.md#how-bins-work) for the boundary values.

---

## 14. Census tract API does not support state wildcard

### What

The Census ACS tract endpoint requires you to specify a state explicitly — `&for=tract:*&in=state:*` is not allowed. Returns no data, no error.

### How CRCI handles it

`src/api/census_client.py` iterates over each state and concatenates results for tract pulls. ~52 calls per indicator group. Adds ~5–10 minutes to the tract pipeline.

### Where to look

- Lesson date: 2025-12-03.
- Code: `src/api/census_client.py` — search for state iteration loop.

---

## 15. Database bulk inserts must use SQLAlchemy Core

### What

ORM `session.add_all()` is dramatically slower than SQLAlchemy Core `insert()` with batches for the 88K-tract source data load. The deprecated approach took ~6.5 hours; bulk Core inserts take ~2.7 seconds.

### How CRCI handles it

`src/db/repositories.py:bulk_create()` uses Core `insert()` with batched executemany. All production code paths use this method. ORM `add_all()` is reserved for ad-hoc dev use only.

### Where to look

- Lesson date: 2025-12-03.
- Code: `src/db/repositories.py:bulk_create`.

---

## Quick lookup index

| Concern | Section |
|---------|---------|
| CT counties duplicated | [#1](#1-connecticut-planning-region-restructuring-2022) |
| CT zero CBP values | [#2](#2-connecticut-cbp-2022-zeros) |
| PR Limited English NaN | [#3](#3-puerto-rico-limited-english) |
| Inactive Voter NaN | [#4](#4-eavs--88-does-not-apply-and--99-data-not-available) |
| Population Change asymmetric | [#5](#5-population-change-subset-z-scores) |
| ARDA POP year aliasing | [#6](#6-arda-pop-column-year-aliasing) |
| Tribal output missing 5 indicators | [#7](#7-tribal-pipeline-drops-non-acs-indicators) |
| Tribal degenerate bins | [#8](#8-tribal-zero-population-geo-filtering) |
| Mixed GEO_IDs in tract/tribal output | [#9](#9-datapuller-outer-merge-contamination) |
| All tracts in a county have identical CBP values | [#10](#10-tract-pipeline-imputes-non-acs-indicators-from-parent-county) |
| BinningEngine hangs | [#11](#11-jenkscaspall-infinite-loop-on-degenerate-data) |
| POP missing column error | [#12](#12-pop-year-clamping) |
| Some bin boundaries are hard-coded | [#13](#13-manual-bin-boundaries-one-indicator--five-composite-columns) |
| Tract pull "hangs" or returns nothing | [#14](#14-census-tract-api-does-not-support-state-wildcard) |
| DB writes are slow | [#15](#15-database-bulk-inserts-must-use-sqlalchemy-core) |
