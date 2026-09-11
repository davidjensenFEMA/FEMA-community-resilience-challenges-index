# Indicator Catalog

The 22 CRCI indicators in detail: formula, source, function type, orientation, and notes.

The authoritative source remains [`config/indicators.yaml`](../../config/indicators.yaml) (and `data/cria_data_reference.xlsx` for orientation flags). This guide makes that data readable.

For methodology (why z-scores, what equal weights mean), see [methodology.md](methodology.md). For special-case behavior, see [special_cases.md](special_cases.md).

---

## How to read this catalog

Each indicator has:

- **Source**: the API/file the data comes from. ACS = American Community Survey; CBP = County Business Patterns; EAVS = Election Administration and Voting Survey; ARDA = Association of Religion Data Archives; POP = Population Estimates Program.
- **Function type**: the formula shape — see [Function types](#function-types-the-five-formula-shapes) below.
- **Numerator / Denominator**: column codes from the source data (Census variable IDs, NAICS codes, etc.).
- **Orientation**: `forward` = high values mean high challenge as collected (no flip needed); `reverse` = high values mean high resilience and the indicator is flipped via `100 − x` during aggregation. Stored in the reference's `Augment` column.
- **Notes**: special-case behavior or domain caveats.

After all 22 are reoriented to `pos` (resilience-positive), they are z-scored and averaged into the composite `agg`. See [methodology.md](methodology.md) for the full pipeline.

---

## Function types — the five formula shapes

| Type | Formula | Used for | Example |
|------|---------|----------|---------|
| `divide` | `numerator / denominator` (× 100 for %) | Most ACS proportions | Poverty: `S1701_C02_001E / S1701_C01_001E` |
| `reverse_divide` | `1 − (numerator / denominator)` | Inverted ACS proportions where the source measures resilience-positive but the indicator is the gap | Low Access to Communications: `1 − (broadband / total households)` |
| `divide_scalar` | `(numerator / denominator) × rate` | Per-capita rates with a unit multiplier | Civil Org: `civic_orgs / population × 10000` (per 10K pop) |
| `max` | `max(num_cols) / denominator` | "What's the largest single component?" | Lack of Economic Diversity: `max(industry shares) / total employed` |
| `mean` | `mean(num_cols) / denominator` | Multi-column rates averaged | Population Change: `mean(NETMIG cols) / population` |

Implemented in `src/core/indicators.py` as `_divide_function`, `_reverse_divide_function`, `_divide_scalar_function`, `_max_function`, `_mean_function`. All five except `_mean_function` mask NaN explicitly (see [methodology.md "Open audit issues"](methodology.md#open-methodological-audit-issues)).

---

## The 22 indicators (in `order` from `indicators.yaml`)

### 1. Mobile Homes
- **Source**: ACS  &nbsp;**Function**: `divide`  &nbsp;**Orientation**: reverse
- **Formula**: `DP04_0014E / DP04_0001E` (mobile-home units / total housing units)
- **Why it's a challenge**: Mobile homes are disproportionately damaged in severe weather and harder to insure.

### 2. Owner Occupied
- **Source**: ACS  &nbsp;**Function**: `divide`  &nbsp;**Orientation**: forward
- **Formula**: `DP04_0046E / DP04_0001E` (owner-occupied / total housing units)
- **Why it's a challenge**: Higher owner-occupancy generally signals community stability; lower owner-occupancy = more challenge. Stored as resilience-positive (no flip needed).

### 3. Education
- **Source**: ACS  &nbsp;**Function**: `divide`  &nbsp;**Orientation**: reverse
- **Formula**: `(S1501_C01_007E + S1501_C01_008E) / S1501_C01_006E` (population 25+ without HS diploma / total 25+)
- **Why it's a challenge**: Lower educational attainment correlates with reduced ability to navigate post-disaster recovery resources.

### 4. No Vehicle
- **Source**: ACS  &nbsp;**Function**: `divide`  &nbsp;**Orientation**: reverse
- **Formula**: `B08201_002E / B08201_001E` (no-vehicle households / total households)
- **Why it's a challenge**: Households without vehicles face evacuation difficulties.

### 5. Age (over 65)
- **Source**: ACS  &nbsp;**Function**: `divide`  &nbsp;**Orientation**: reverse
- **Formula**: `S0101_C01_030E / S0101_C01_001E` (65+ population / total population)
- **Why it's a challenge**: Elderly populations have elevated risk in disaster scenarios.

### 6. Disability
- **Source**: ACS  &nbsp;**Function**: `divide`  &nbsp;**Orientation**: reverse
- **Formula**: `S1810_C02_001E / S1810_C01_001E` (population with disability / total)
- **Why it's a challenge**: Disability raises evacuation and recovery difficulty.

### 7. Limited English
- **Source**: ACS  &nbsp;**Function**: `divide`  &nbsp;**Orientation**: reverse
- **Formula**: `S1602_C03_001E / S1602_C01_001E` (limited-English population / total)
- **Special case**: Puerto Rico is set to NaN. Spanish speakers are not "limited English" by ACS criteria. See [special_cases.md #3](special_cases.md#3-puerto-rico-limited-english).

### 8. Single Parent
- **Source**: ACS  &nbsp;**Function**: `divide`  &nbsp;**Orientation**: reverse
- **Formula**: `(B09005_004E + B09005_005E) / B09005_001E` (children in single-parent households / total children)
- **Why it's a challenge**: Single-parent households have less recovery bandwidth.

### 9. Low Access to Communications
- **Source**: ACS  &nbsp;**Function**: `reverse_divide`  &nbsp;**Orientation**: reverse
- **Formula**: `1 − (S2801_C01_005E / S2801_C01_001E)` — proportion of households *without* broadband
- **Note**: The source measures *with* broadband; we compute the gap.

### 10. Inactive Voter
- **Source**: EAVS  &nbsp;**Function**: `divide`  &nbsp;**Orientation**: reverse
- **Formula**: `A1c / A1a` (inactive registered voters / total registered)
- **Special cases**:
  - EAVS `-88` ("does not apply") and `-99` ("data not available") map to NaN. See [special_cases.md #4](special_cases.md#4-eavs--88-does-not-apply-and--99-data-not-available).
  - States with zero total votes get `Inactive Voter_bins = NaN` post-processing.
  - Uses fuzzy name matching for county lookup (EAVS uses county names, not FIPS).

### 11. Civil Org
- **Source**: CBP  &nbsp;**Function**: `divide_scalar`  &nbsp;**Orientation**: forward
- **Formula**: `(NAICS 813410 establishments / population) × 10000` — civic organizations per 10K pop
- **Notes**:
  - NAICS 813410 = Civic and Social Organizations.
  - Stored as resilience-positive (more orgs = more stability).
  - CT 2022 zeros mapped to NaN. See [special_cases.md #2](special_cases.md#2-connecticut-cbp-2022-zeros).

### 12. Population Change
- **Source**: POP  &nbsp;**Function**: `mean`  &nbsp;**Orientation**: forward (with special handling)
- **Formula**: `mean(NETMIG cols) / S0101_C01_001E` (net migration / population)
- **Special case**: Z-score uses **subset stats** (only non-NaN values), then `|z|` before contributing to composite. Treated as a dispersion penalty, not a directional signal. See [special_cases.md #5](special_cases.md#5-population-change-subset-z-scores).

### 13. Religion
- **Source**: ARDA  &nbsp;**Function**: `reverse_divide`  &nbsp;**Orientation**: reverse
- **Formula**: `1 − (TOTADH / POP)` — proportion *without* religious adherence
- **Notes**:
  - The source `POP` column is decade-specific (`POP2020`, `POP2010`); aliased to `POP` on load.
  - Decennial data — not updated annually.

### 14. Unemployment
- **Source**: ACS  &nbsp;**Function**: `divide`  &nbsp;**Orientation**: reverse
- **Formula**: `DP03_0005E / DP03_0003E` (unemployed / labor force)

### 15. Unemployed Women
- **Source**: ACS  &nbsp;**Function**: `reverse_divide`  &nbsp;**Orientation**: reverse
- **Formula**: `1 − (DP03_0013E / DP03_0012E)` — proportion of women *not employed*
- **Note**: The source measures *employed* women; we compute the gap.

### 16. Median Income
- **Source**: ACS  &nbsp;**Function**: `divide`  &nbsp;**Orientation**: forward
- **Formula**: `S1903_C03_001E / 1` (median household income, scalar denominator)
- **Special case**: Uses **manual bins** with dollar thresholds (`$25k / $50k / $75k / $100k` for 5-bin) rather than auto-selected bins. See [outputs.md](outputs.md#how-bins-work).

### 17. GINI
- **Source**: ACS  &nbsp;**Function**: `divide`  &nbsp;**Orientation**: reverse
- **Formula**: `B19083_001E / 1` (Gini coefficient of income inequality, scalar denominator)
- **Range**: 0 (perfect equality) to 1 (perfect inequality).

### 18. Lack of Economic Diversity
- **Source**: ACS  &nbsp;**Function**: `max`  &nbsp;**Orientation**: reverse
- **Formula**: `max(DP03_0033E..DP03_0045E) / DP03_0032E` — largest industry sector's share of employment
- **Notes**:
  - 13 industry sector columns evaluated; the largest is taken.
  - Lower diversity (one dominant industry) = higher challenge.

### 19. Poverty
- **Source**: ACS  &nbsp;**Function**: `divide`  &nbsp;**Orientation**: reverse
- **Formula**: `S1701_C02_001E / S1701_C01_001E` (population below poverty line / total population for whom poverty status is determined)

### 20. Hospitals
- **Source**: CBP  &nbsp;**Function**: `divide_scalar`  &nbsp;**Orientation**: forward
- **Formula**: `(NAICS 622110 establishments / population) × 10000` — hospitals per 10K pop
- **Notes**:
  - NAICS 622110 = General Medical and Surgical Hospitals.
  - Stored as resilience-positive.

### 21. Medical
- **Source**: ACS  &nbsp;**Function**: `divide_scalar`  &nbsp;**Orientation**: forward
- **Formula**: `(S2401_C01_016E / S0101_C01_001E) × 1.0` — healthcare practitioners per capita
- **Notes**: Scalar `rate=1.0` (effectively no scalar; left in for future flexibility).

### 22. Uninsured Population
- **Source**: ACS  &nbsp;**Function**: `divide`  &nbsp;**Orientation**: reverse
- **Formula**: `S2701_C04_001E / S2701_C01_001E` (uninsured / total for whom insurance status is determined)

---

## Orientation summary

After `_reorient_indicators` applies `100 − x` to indicators with `Augment == "reverse"`, all 22 columns face the same direction in the `pos` tab: **higher = higher resilience**.

| Forward (no flip) | Reversed (flipped via `100 − x`) |
|-------------------|----------------------------------|
| Owner Occupied | Mobile Homes, Education, No Vehicle, Age, Disability, Limited English, Single Parent, Low Access to Communications, Inactive Voter, Religion, Unemployment, Unemployed Women, GINI, Lack of Economic Diversity, Poverty, Uninsured Population |
| Civil Org, Hospitals, Medical, Median Income, Population Change | |

---

## Source coverage by indicator count

| Source | Count | Indicators |
|--------|-------|------------|
| ACS | 17 | Mobile Homes, Owner Occupied, Education, No Vehicle, Age, Disability, Limited English, Single Parent, Low Access to Communications, Unemployment, Unemployed Women, Median Income, GINI, Lack of Economic Diversity, Poverty, Medical, Uninsured Population |
| CBP | 2 | Civil Org, Hospitals |
| EAVS | 1 | Inactive Voter |
| ARDA | 1 | Religion |
| POP | 1 | Population Change |

For tribal output, the 5 non-ACS indicators are dropped entirely (only the 17 ACS-sourced indicators survive). See [special_cases.md #7](special_cases.md#7-tribal-pipeline-drops-non-acs-indicators).

---

## Function type usage by indicator

| Function | Count | Indicators |
|----------|-------|------------|
| `divide` | 14 | Mobile Homes, Owner Occupied, Education, No Vehicle, Age, Disability, Limited English, Single Parent, Inactive Voter, Unemployment, Median Income, GINI, Poverty, Uninsured Population |
| `reverse_divide` | 3 | Low Access to Communications, Religion, Unemployed Women |
| `divide_scalar` | 3 | Civil Org, Hospitals, Medical |
| `max` | 1 | Lack of Economic Diversity |
| `mean` | 1 | Population Change |

Total: 22.

---

## Adding a 23rd indicator

See [extending.md](extending.md#adding-a-new-indicator) for the full procedure. Quick checklist:

1. Pick a source — does it already have a client in `src/api/`?
2. Pick a function type — does the formula match one of the 5 shapes?
3. Identify the column codes — for ACS, use the [Census Variable Documentation](https://api.census.gov/data.html); for CBP, the NAICS code.
4. Decide orientation — does high value mean high challenge (forward) or high resilience (reverse)?
5. Add to `data/cria_data_reference.xlsx` Status sheet, then re-run `scripts/import_reference_data.py`.
6. Mirror the change in `config/indicators.yaml` for documentation parity.
7. Write a known-answer test ([contributing.md "Pattern: known-answer test"](contributing.md#pattern-known-answer-test)).
8. Run a calibration check ([contributing.md "Calibration check"](contributing.md#calibration-check)) — note that adding an indicator *will* change correlation against the 22-indicator baseline. Document the new baseline.

---

## Indicator definitions also live in

- [`config/indicators.yaml`](../../config/indicators.yaml) — YAML mirror, easier to grep
- `data/cria_data_reference.xlsx` (Status sheet) — authoritative source, includes `Augment`, `rate`, `Function`, label variants
- Database: the `indicators` reference table, populated by `scripts/import_reference_data.py`
