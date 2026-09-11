# API Clients

Per-client documentation for each external data source. Quirks, rate limits, year configuration, and known issues.

For the indicators sourced from each, see [indicator_catalog.md](indicator_catalog.md). For a new-source extension procedure, see [extending.md](extending.md#adding-a-new-api-source).

---

## BaseAPIClient

`src/api/base_client.py`

All HTTP-based clients inherit from this. Provides:

- `requests.Session` with `HTTPAdapter` for connection pooling
- `Retry` from urllib3 for **automatic retry with exponential backoff** (transient network errors)
- Configurable timeout
- Logging integration

What it does NOT do:
- Handle HTTP 429 (rate-limit) explicitly — these will be retried per the standard `Retry` config but with no special backoff
- Validate response content — that's per-client
- Cache responses — every call hits the network

---

## CensusAPIClient (ACS)

`src/api/census_client.py` — sources 17 of the 22 indicators

### Endpoint

`https://api.census.gov/data/{year}/acs/acs5` (5-year estimates)

### Authentication

Required. `CENSUS_API_KEY` in `.env`. Sign up at [api.census.gov/data/key_signup.html](https://api.census.gov/data/key_signup.html). Keys take ~5 minutes to activate.

Without a valid key:
- The Census API silently returns errors as HTML instead of JSON
- Anonymous requests have a much lower rate limit (~500/day instead of higher)

### Rate limits

| Authenticated | Per-day |
|--------------|---------|
| Yes | ~500 calls per day per key |
| No | Substantially lower (Census doesn't publish exact figures) |

A single county pipeline run uses ~10–20 calls. A tract pipeline uses ~52 per indicator group (per-state iteration). One full year of geographies will not exhaust the quota.

### Year configuration

`ACS_YEAR` in `.env` — refers to the **end year** of the 5-year window.
- `ACS_YEAR=2023` → ACS 5-year 2019–2023, released December 2024 → **2024 deliverable**.
- ACS 5-year always lags by ~1 year.

### Geography support

| Level | Supported | Notes |
|-------|-----------|-------|
| State | Yes | Single call returns all 51 |
| County | Yes | Single call returns all ~3,200 |
| Tract | Yes — but per-state | **Cannot use state wildcard.** See [special_cases.md #14](special_cases.md#14-census-tract-api-does-not-support-state-wildcard) |
| Tribal (AIA/ANA) | Yes | Single call |

### Quirks

- **Per-state tract iteration**: ACS rejects `&for=tract:*&in=state:*`. The client iterates over each state — adds ~5–10 minutes to tract runs.
- **Variable codes**: Use codes like `S0101_C01_001E` (subject table 0101, column 01, row 001, estimate). Margin-of-error codes end in `M` (`S0101_C01_001M`). CRCI uses estimates only; MOEs are not propagated.
- **HTML error responses**: When the API rejects a request (bad key, bad URL), it may return an HTML error page instead of JSON. The client should fail fast on JSON parse errors with a clear message.

### Known issues

- Tract pulls take 5–10 minutes minimum due to per-state iteration. Not a bug.
- Some ACS variables disappear or get renamed across years; the indicator definitions in `data/cria_data_reference.xlsx` are pinned to specific column codes and may break on year changes.

---

## CBPClient (County Business Patterns)

`src/api/cbp_client.py` — sources Civil Org and Hospitals

### Endpoint

`https://api.census.gov/data/{year}/cbp`

### Authentication

Same Census API key as ACS.

### Year configuration

`CBP_YEAR` in `.env`. CBP is published annually with ~1–2 year lag.

### Geography support

County only. CBP does not publish at tract or tribal level — those geographies inherit from county via imputation (see [special_cases.md #10](special_cases.md#10-tract-pipeline-imputes-non-acs-indicators-from-parent-county)).

### Quirks

- **NAICS codes**: Identifies industries. CRCI uses:
  - `813410` — Civic and Social Organizations (→ Civil Org)
  - `622110` — General Medical and Surgical Hospitals (→ Hospitals)
  - `NAICS_YEAR=2017` is the latest stable revision used throughout
- **Connecticut 2022 zeros**: CBP 2022 has zero values for old CT counties (mid-restructuring). The client converts these to NaN. See [special_cases.md #2](special_cases.md#2-connecticut-cbp-2022-zeros).
- **Connecticut 18 entries**: From CBP 2022 onward, CT has 18 entries (9 old counties + 9 new planning regions). Deduplication happens downstream in `_impute_tract_from_county`. See [special_cases.md #1](special_cases.md#1-connecticut-planning-region-restructuring-2022).

---

## EAVSClient

`src/api/external_clients.py:EAVSClient` — sources Inactive Voter

### Source

ZIP file download from the U.S. Election Assistance Commission. Not a JSON API — the client downloads a ZIP, extracts a CSV, and parses it.

### Authentication

None.

### Year configuration

EAVS is biennial (election years). The current pipeline uses a fixed file from a specific election year. There is no `EAVS_YEAR` env variable — the file path is hardcoded or detected from `data/`.

### Geography support

State-level only. County-level matching uses **fuzzy name matching** (EAVS uses county names, not FIPS codes). Be cautious — fuzzy matching can fail for counties with non-standard names.

### Quirks

- **`-88` and `-99` sentinels**: `-88` = "does not apply" (state didn't conduct that program), `-99` = "data not available". Both must map to NaN, not zero. See [special_cases.md #4](special_cases.md#4-eavs--88-does-not-apply-and--99-data-not-available).
- **ZIP extraction**: The client must extract the ZIP and find the right CSV (usually one of several included files).
- **Non-reporting states**: ~14 states/territories don't report. Their Inactive Voter indicator is NaN.

### Known issues

- **Zero-vote post-processing**: Even after `-88`/`-99` mapping, some states report zero total votes (which divides to NaN). The pipeline post-processes `Inactive Voter_bins` to NaN for these states. Implemented in `scripts/run_full_pipeline.py:_nullify_zero_vote_states`.

---

## ARDAClient

`src/api/external_clients.py:ARDAClient` — sources Religion

### Source

Local Excel file in `data/`. Not an API — the client reads a file shipped with the repo.

### Authentication

None (local file).

### Year configuration

ARDA religion data is **decennial** (every 10 years). The file is shipped with the repo for the current decade. `ASARB_YEAR=2020` in `.env` (ASARB = Association of Statisticians of American Religious Bodies, ARDA's data source).

### Geography support

County only. Tracts/tribal inherit from county via imputation.

### Quirks

- **`POP{year}` column aliasing**: The file's population denominator column is decade-specific (`POP2020`, `POP2010`). The client renames it to a generic `POP` on load so indicator definitions don't have to change every decade. See [special_cases.md #6](special_cases.md#6-arda-pop-column-year-aliasing).
- **`TOTADH`**: Total adherents column. Used as the numerator for the Religion indicator.

---

## POPClient (Population Estimates Program)

`src/api/external_clients.py:POPClient` — sources Population Change

### Source

Decennial CSV file from the Census Population Estimates Program. The current default is `co-est2024-alldata.csv` (2024 vintage). Inherits from `BaseAPIClient` for HTTP download support but typically reads a local file.

### Authentication

None.

### Year configuration

`POP_YEAR` in `.env`. The file is decade-based — `co-est2024-alldata.csv` covers 2020–2024.

### Geography support

County (state/county-resolved estimates).

### Quirks

- **Year clamping**: The NETMIG column is named per year (`NETMIG2020`, `NETMIG2021`, `NETMIG2022`). Requesting a year outside the file's range raises a "missing column" error. The client clamps the requested year to the file's decade base. See [special_cases.md #12](special_cases.md#12-pop-year-clamping).
- **Multiple NETMIG columns**: The Population Change indicator uses `mean(NETMIG cols)`, averaging across years for stability. This is the only `mean` indicator.

---

## DataPuller (orchestrator)

`src/core/data_puller.py`

Not an API client itself — orchestrates calls to all five clients and merges results.

### Flow

1. Initialize all five clients with the configured years.
2. Call `client.fetch(geography)` on each.
3. **Outer-merge** all DataFrames on `GEO_ID`.
4. Persist to database (if enabled).

### Quirks

- **Outer-merge contamination**: Different sources emit different GEO_ID prefixes. The outer merge introduces cross-contamination — county-prefix rows in tract output, etc. This is filtered downstream by D9/D10 in `scripts/run_full_pipeline.py`. See [special_cases.md #9](special_cases.md#9-datapuller-outer-merge-contamination).

---

## Adding a new client

Step-by-step in [extending.md](extending.md#adding-a-new-api-source). Key points:

1. Inherit from `BaseAPIClient` (gives you retry + session pooling).
2. Add a `_YEAR` env variable to `.env.example` and `src/config/settings.py`.
3. Wire into `DataPuller`.
4. Document any sentinel codes, year quirks, or geography limits in this file.
5. Add to [special_cases.md](special_cases.md) if behavior is non-obvious.

---

## Quick reference

| Client | Source | Indicators | Geography | Auth | File or HTTP |
|--------|--------|------------|-----------|------|--------------|
| Census | ACS 5-year | 17 | All four | API key | HTTP JSON |
| CBP | County Business Patterns | 2 | County only | Same API key | HTTP JSON |
| EAVS | Election Admin | 1 | State (with fuzzy county lookup) | None | HTTP ZIP → CSV |
| ARDA | Religion | 1 | County only | None | Local Excel |
| POP | Population Estimates | 1 | County only | None | Local CSV |
