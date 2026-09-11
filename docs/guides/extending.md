# Extending CRCI

How to add a new indicator, API source, geography level, or schema column without breaking the calibration baseline.

Prerequisites: read [methodology.md](methodology.md) (so you understand what you're preserving), [special_cases.md](special_cases.md) (so you don't reintroduce a fixed bug), and [contributing.md](contributing.md) (for branch and test conventions).

For the architectural rationale behind the current OOP/Docker/PostgreSQL structure (which Phases 1–8 of the original refactor established), see [`docs/plans/refactor_plan.md`](../plans/refactor_plan.md). For the database schema you'll be extending, see [`docs/design/database_schema.md`](../design/database_schema.md).

---

## Adding a new indicator

The most common extension. Adds a 23rd indicator using the existing five function types.

### Step 1: Identify the source

Pick from the five existing sources or [add a new client](#adding-a-new-api-source).

| Source | Existing client | What it provides |
|--------|----------------|------------------|
| ACS | `src/api/census_client.py` | Census ACS 5-year demographics |
| CBP | `src/api/cbp_client.py` | County Business Patterns |
| EAVS | `src/api/external_clients.py:EAVSClient` | Election admin |
| ARDA | `src/api/external_clients.py:ARDAClient` | Religion data |
| POP | `src/api/external_clients.py:POPClient` | Population estimates |

For an ACS indicator, find the variable code at [api.census.gov/data.html](https://api.census.gov/data.html). For CBP, identify the NAICS code.

### Step 2: Pick a function type

| Type | When to pick |
|------|--------------|
| `divide` | Single-numerator proportion (most common) |
| `reverse_divide` | The source measures the resilience-positive value; the indicator is the gap |
| `divide_scalar` | Per-capita rate with a unit multiplier (e.g., per 10K pop) |
| `max` | "What's the largest single component?" — only used by Lack of Economic Diversity |
| `mean` | Multi-column rate averaged — only used by Population Change |

If your indicator doesn't fit one of these, you'll need to add a new function — see [Adding a new function type](#adding-a-new-indicator-function-type).

### Step 3: Decide orientation

Does a high value mean **high challenge** (`forward`) or **high resilience** (`reverse`)?

- Poverty is `reverse` — high poverty means high challenge, but stored as the challenge value, so we flip via `100 − x` during aggregation.
- Civil Org is `forward` — high org count means high resilience; no flip needed.

When in doubt, look at similar existing indicators in [indicator_catalog.md "Orientation summary"](indicator_catalog.md#orientation-summary).

### Step 4: Update the reference

The authoritative source is `data/cria_data_reference.xlsx` (Status sheet). Add a row with these columns:

| Column | Value |
|--------|-------|
| `Indicator` | Display name (e.g., `Food Insecurity`) |
| `Label` | Short label for output tabs |
| `Label_Correlation` | Label for the correlation matrix tab |
| `Source` | One of `ACS`, `CBP`, `EAVS`, `ARDA`, `POP` |
| `numerator` | Source column code (or comma-separated for multi-column) |
| `denominator` | Source column code or `1` |
| `Function` | One of `divide`, `reverse_divide`, `divide_scalar`, `max`, `mean` |
| `Augment` | `reverse` if needed; otherwise blank |
| `rate` | Multiplier for `divide_scalar` (e.g., `10000`); blank otherwise |
| `Units` | `%`, `count`, `$`, etc. (display only) |
| `NAICS` | NAICS code for CBP indicators |
| `notes` | Domain caveats |

Then mirror to `config/indicators.yaml` for documentation parity:

```yaml
- name: Food Insecurity
  source: ACS
  function: divide
  numerator: "S2201_C03_001E"
  denominator: "S2201_C01_001E"
  description: Proportion of households receiving SNAP benefits
  notes: Used as a food insecurity proxy
  order: 23
```

### Step 5: Re-import the reference data

```bash
poetry run python scripts/import_reference_data.py
```

The script is idempotent — it upserts based on `Indicator` name.

### Step 6: Verify the API client returns the new column

If you're using ACS, the column needs to be in the request. Check `src/api/census_client.py` — the request URL is built from the reference data's `numerator`/`denominator` columns, so this should be automatic for ACS.

For CBP/EAVS/ARDA/POP, you may need to update the source-specific client to fetch the new column.

### Step 7: Run a smoke test

```bash
poetry run python scripts/run_full_pipeline.py \
  --geography state --year 2024 --export-excel --no-db
```

Open `cria_indicators_state_2024.xlsx` and confirm the new indicator column exists with non-NaN values.

### Step 8: Write a known-answer test

The dispatch is `_calculate_indicator(idx, row, data)` in `src/core/indicators.py` — it reads the reference `row` to pick the function. For a unit test, it's easier to call the function directly:

```python
# tests/unit/test_indicators.py
import pandas as pd
from src.core.indicators import IndicatorCalculator

def test_food_insecurity_indicator():
    """Food Insecurity = SNAP households / total households."""
    source = pd.DataFrame({
        "S2201_C03_001E": [100, 50, 0],
        "S2201_C01_001E": [1000, 1000, 100],
    }, index=["A", "B", "C"])

    calc = IndicatorCalculator(geography="county")
    # Build a reference-row dict matching what the YAML/Excel produces
    row = pd.Series({
        "Indicator": "Food Insecurity",
        "Function": "divide",
        "numerator": "S2201_C03_001E",
        "denominator": "S2201_C01_001E",
    })
    result = calc._divide_function(row, source)

    assert result.loc["A"] == 0.10   # 100/1000
    assert result.loc["B"] == 0.05   # 50/1000
    assert result.loc["C"] == 0.0    # 0/100 — genuine zero, not NaN
```

### Step 9: Calibration check

Adding an indicator changes the composite. The old 0.94/1.00 calibration targets won't hold. You must:

1. Run the new pipeline against the calibration year (2022 county or 2021 tract).
2. Decide what the new baseline is (e.g., "0.95 with 23 indicators against the 23-indicator deprecated baseline" — but there is no 23-indicator deprecated baseline, so you're establishing a new one).
3. Update [`config/project.yaml`](../../config/project.yaml) `calibration` block.
4. Document the change in `CHANGELOG.md`.

If the goal is just to *evaluate* a new indicator without changing the deliverable, run the pipeline twice (with and without) and compare composite scores externally.

### Step 10: Update docs

- [`docs/guides/indicator_catalog.md`](indicator_catalog.md) — add the new indicator's entry
- [`config/project.yaml`](../../config/project.yaml) `lessons_learned` — add a note if anything was non-obvious
- `CHANGELOG.md` — `[feature][core] Added Food Insecurity indicator (ACS)`

---

## Adding a new function type

If your indicator doesn't fit `divide`, `reverse_divide`, `divide_scalar`, `max`, or `mean`, you need a new function.

### Where to add it

`src/core/indicators.py` — alongside `_divide_function`, `_max_function`, `_mean_function`, `_divide_scalar_function`, `_reverse_divide_function`. All five take `(self, row: pd.Series, data: pd.DataFrame) -> pd.Series` and read column codes from the `row` argument.

### Required behavior

Every indicator function MUST:
1. Take `(row: pd.Series, data: pd.DataFrame)` and return `pd.Series` indexed like `data.index`.
2. Read column codes from the `row` (e.g., `row["numerator"]`, `row["denominator"]`).
3. Return NaN for zero denominators (not 0). See the 2026-03-25 lesson.
4. Mask NaN explicitly across input columns to prevent partial-row calculations. (Currently `_mean_function` doesn't — open audit issue H1.)
5. Handle the source-data-missing case (column not in DataFrame) gracefully, not crash.

### Example skeleton

```python
def _my_new_function(self, row: pd.Series, data: pd.DataFrame) -> pd.Series:
    """
    My new function: <one-line description>.
    """
    num = row["numerator"]
    denom = row["denominator"]

    if num not in data.columns or denom not in data.columns:
        logger.warning(f"My new function: missing columns {num} or {denom}")
        return pd.Series(np.nan, index=data.index)

    numerator = data[num]
    denominator = data[denom]

    # Compute
    result = numerator / denominator

    # Zero-denominator → NaN (not 0)
    result.loc[denominator == 0] = np.nan

    # Mask NaN — propagate missing inputs to missing outputs
    missing_mask = numerator.isna() | denominator.isna()
    result.loc[missing_mask] = np.nan

    return result
```

### Wiring

Add an `elif function == "my_new":` branch in `IndicatorCalculator._calculate_indicator` (around line 141) that dispatches to your new function. Then add `function: my_new` to the indicator's row in `data/cria_data_reference.xlsx` and `config/indicators.yaml`. Finally update [indicator_catalog.md "Function types"](indicator_catalog.md#function-types--the-five-formula-shapes) and [glossary.md](glossary.md).

---

## Adding a new API source

If your indicator's data isn't in any of the existing five sources.

### Step 1: Inherit from `BaseAPIClient`

`src/api/base_client.py` provides retry logic, timeouts, and session management. New clients should subclass it:

```python
# src/api/my_new_client.py
from src.api.base_client import BaseAPIClient

class MyNewClient(BaseAPIClient):
    def __init__(self, year: int):
        super().__init__(base_url="https://api.example.com")
        self.year = year

    def fetch(self, geography: str) -> pd.DataFrame:
        # Implement fetch logic
        # Return a DataFrame indexed by GEO_ID
        ...
```

### Step 2: Wire into `DataPuller`

`src/core/data_puller.py` is the orchestrator. Add the new client to the source list:

```python
# DataPuller.__init__
self.my_new_client = MyNewClient(year=year)

# DataPuller.pull_all_data
my_new_data = self.my_new_client.fetch(geography=self.geography)
# Outer-merge into the combined source DataFrame
```

### Step 3: Add a year variable to `.env.example`

```
MY_NEW_YEAR=2024  # Year for MyNew API
```

And to `src/config/settings.py`:

```python
my_new_year: int = 2024
```

### Step 4: Document the client's quirks

Add a section to [api_clients.md](api_clients.md) describing:
- Authentication (key required? rate-limited?)
- File format (JSON / CSV / ZIP / Excel)
- Year availability (annual? decennial?)
- Sentinel codes ("does not apply", "no data")
- Geography support (state? county? tract?)
- Retry behavior

### Step 5: Add to special cases if needed

Any source-specific handling (column aliasing, missing-value codes, year clamping) goes in [special_cases.md](special_cases.md).

### Step 6: Test

Mock the HTTP calls in unit tests; have at least one integration test that hits the real API (marked `@pytest.mark.requires_api`).

---

## Adding a new geography level

The existing four are `state`, `county`, `tract`, `tribal`. To add a fifth (e.g., `congressional_district`):

### Step 1: Update the CLI

`scripts/run_full_pipeline.py:639`:

```python
parser.add_argument(
    "--geography",
    choices=["state", "county", "tract", "tribal", "congressional_district"],
    default="county",
    ...
)
```

### Step 2: Update geography defaults

`scripts/run_full_pipeline.py:46`:

```python
DEFAULT_BINS = {
    "county": 5, "tract": 7, "tribal": 5, "state": 5,
    "congressional_district": 5,  # New
}

BINNING_EXCEPTIONS = {
    ...
    "congressional_district": {},  # New, can be populated as needed
}
```

### Step 3: Sync geography reference

```bash
poetry run python scripts/sync_geographies.py --level congressional_district
```

This pulls from the Census `/geo` API and writes to `data/geographies/congressional_district.parquet`. You'll need to extend `sync_geographies.py` to handle the new level.

### Step 4: Verify each API client supports the new level

Some sources don't publish at all geography levels:
- ACS: most levels supported
- CBP: county only
- EAVS: state only
- ARDA: county only
- POP: county-ish (state/county estimates)

For unsupported sources, decide: (a) drop the indicator (like tribal does for non-ACS) or (b) impute from a parent geography (like tract does from county).

### Step 5: Add special-case handling

Add filters analogous to D9/D10 in `scripts/run_full_pipeline.py` if the DataPuller's outer merge will introduce contaminating GEO_IDs.

### Step 6: Update bin configuration

If the new geography needs a bin count other than 5, update `DEFAULT_BINS` and the `MANUAL_BINS` dict in `src/core/binning.py` if any of the manual-bin columns need new boundary configurations for the new bin count.

### Step 7: Calibration

There's no existing baseline for a new geography. Establish one by running the deprecated pipeline (if it supported the level) or by careful manual review.

---

## Adding a column to an existing model

If you need a new column on `source_data`, `indicators`, etc.

### Step 1: Update the SQLAlchemy model

`src/db/models.py`:

```python
class SourceData(Base):
    ...
    new_column = Column(String, nullable=True)
```

### Step 2: Generate a migration

```bash
poetry run alembic revision --autogenerate -m "Add new_column to source_data"
```

Review the autogenerated script in `alembic/versions/`. For SQLite compatibility, wrap ALTER statements in `op.batch_alter_table`:

```python
def upgrade():
    with op.batch_alter_table("source_data") as batch_op:
        batch_op.add_column(sa.Column("new_column", sa.String, nullable=True))
```

### Step 3: Apply and test

```bash
poetry run alembic upgrade head
poetry run pytest -m "requires_db"
```

### Step 4: Update the repository

`src/db/repositories.py` — if the new column needs to be populated by the pipeline, update the `bulk_create` and `update` methods.

### Step 5: Backup before applying to production

```bash
./scripts/database_backup.sh pre_migration_new_column
poetry run alembic upgrade head
```

If the migration fails, restore: `./scripts/database_restore.sh backups/cria_backup_pre_migration_new_column_*.sql.gz`.

---

## Anti-patterns to avoid

These have been tried and reverted; see `lessons_learned`:

- **Returning 0 for zero-denominator indicators.** Always NaN. (2026-03-25)
- **Treating EAVS `-88` / `-99` as numbers.** Map to NaN. (2026-03-25)
- **Using `mean()` of full-dataset z-scores for Population Change.** Use the subset. (Pre-2025-12)
- **Auto-selecting `JenksCaspall`.** It hangs on degenerate data. (2025-12-05)
- **ORM `session.add_all()` for >100 rows.** Use `bulk_create()`. (2025-12-03)
- **Using a state wildcard for Census tract queries.** Iterate per state. (2025-12-03)
- **Treating ARDA's `POP{year}` columns as static names.** Alias to generic `POP`. (2025-12-03)
- **Ignoring CT 2022 zeros in CBP data.** Convert to NaN. (2025-10-30)
- **Including Puerto Rico in Limited English calculations.** Exclude (NaN). (2025-10-30)

When in doubt, run the `decision-scientist` agent before committing.
