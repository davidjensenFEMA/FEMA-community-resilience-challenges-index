# Troubleshooting

Common errors and the special-case behaviors that look like bugs but aren't.

If you don't find your problem here, the authoritative list of known issues lives in [`config/project.yaml`](../../config/project.yaml) under `state.known_issues` and `lessons_learned`.

---

## Pipeline errors

### `UniqueViolation` on the second run for a year

The database rejects re-inserts for `(GEO_ID, year)` already present. Use `--no-db` to skip persistence:

```bash
poetry run python scripts/run_full_pipeline.py \
  --geography county --year 2024 --export-excel --no-db
```

If you actually need to overwrite, drop the year from the relevant tables manually and re-run, or restore from a backup.

### `Pipeline exceeded maximum runtime`

The hard timeout fired. Check the geography:

| Geography | Default timeout | Recommended `--timeout` |
|-----------|-----------------|-------------------------|
| state, county, tribal | 60 min | 60 |
| tract | 60 min | **240** |

Tract runs need at least 240 minutes — saving 88K source records to PostgreSQL alone takes ~63 minutes. Either pass `--timeout 240` or set `PIPELINE_TIMEOUT_MINUTES=240` in `.env`.

### `CENSUS_API_KEY` errors

The Census API silently returns errors as HTML if your key is missing or invalid:
- Verify `.env` has `CENSUS_API_KEY=<your_key>` (not `your_census_api_key_here`)
- Get a key: [api.census.gov/data/key_signup.html](https://api.census.gov/data/key_signup.html)
- Keys take a few minutes to activate after signup

### Census tract pull "hangs" or returns nothing

Tract queries cannot use a state wildcard. The pipeline iterates per state (52 calls, ~5–10 minutes). If you see no progress, check the logs for the per-state call sequence.

### `pytest: command not found`

Run `poetry install` first. If pytest is still missing:

```bash
poetry install --with dev
```

Then run via Poetry:

```bash
poetry run pytest
```

### Docker port conflict

CRCI uses **port 5433** for PostgreSQL (not the default 5432) to avoid colliding with a host PostgreSQL install. If the container won't start:

```bash
lsof -i :5433
docker compose -f docker/docker-compose.yml down
docker compose -f docker/docker-compose.yml up -d postgres
```

### `ModuleNotFoundError: No module named 'src'` when running scripts directly

Either run via Poetry (`poetry run python scripts/...`) or set `PYTHONPATH=.`:

```bash
PYTHONPATH=. python3 scripts/run_full_pipeline.py --geography county --year 2024
```

---

## Special cases (look like bugs, aren't)

These are documented domain quirks. The pipeline handles them automatically — listed here so you don't waste time investigating.

### Connecticut counties duplicated (18 entries instead of 9)

CT abolished county government in 2022 and replaced it with 9 planning regions (FIPS `09110`–`09190`). CBP data now has 18 CT entries: 9 old counties + 9 new planning regions. The pipeline keeps both:
- Old counties (`09001`–`09015`) get state-level CBP values (uniform across all 9)
- New planning regions get actual CBP data starting in CBP 2023
- The `_impute_tract_from_county` helper deduplicates on `(state, county)` to prevent merge expansion

You'll see this most clearly in the `cria_inputs_county.xlsx` Civil Org / Hospitals values for CT.

### Puerto Rico Limited English

Spanish speakers in PR are not "limited English speakers" by ACS definition — the indicator excludes PR entirely (NaN). Don't treat the missing PR row as a bug.

### Inactive Voter is NaN for many states

EAVS uses `-88` for "does not apply" and `-99` for "data not available." Both map to NaN, not zero. About 14 states/territories don't report; their `Inactive Voter` indicator is NaN. This was a 2026-03-25 fix — earlier outputs falsely showed `0` for non-reporters.

The `bin_labels` `Inactive Voter_bins` column is also nulled for any state where total votes (`A1a × A1c`) sum to zero across all counties.

### `Population Change` uses subset z-scores

For the `Population Change` (NETMIG) indicator, z-scores are computed against the **subset** of geographies that have non-NaN NETMIG data, not the full geography list. Otherwise the heavy NaN tail would skew the mean and standard deviation. This is documented in `config/indicators.yaml` notes.

### Connecticut CBP 2022 zeros

The 2022 CBP file has *zero* values for old CT counties (instead of NaN) because CBP was migrating to the new planning regions. The pipeline converts these to NaN to prevent false-zero indicator values.

### Tract bins look identical for some indicators

Tract-level data doesn't exist for non-ACS sources (CBP, EAVS, ARDA, POP). The pipeline imputes those values from the parent county — so all tracts in a given county get the same Civil Org, Hospitals, Pop Change, Inactive Voter, and Religion values. This is by design.

If the bins are identical across the *entire dataset* (not just within a county), check `bin_meta.selected_method` — `JenksCaspall` historically caused infinite loops on degenerate data and is excluded from the auto-select pool. The replacement is `FisherJenks`.

### Tribal output is missing columns

Tribal output drops all 5 non-ACS indicators entirely (Civil Org, Hospitals, Inactive Voter, Population Change, Religion). 17 indicators remain. Tribal also gets binning only — no z-scores, no composite CRCI. This matches the deprecated pipeline.

### `arctanh(1.0)` `RuntimeWarning` in correlation logs

The Fisher z transform of the diagonal (r = 1.0) is infinite. `tanh(inf) = 1.0` so the result is functionally correct. Just noisy.

---

## Calibration drift

If after a code change the calibration correlation drops below the targets:

| Geography | Target correlation |
|-----------|-------------------|
| County (vs 2022 baseline) | 0.94 |
| Tract (vs 2021 baseline) | 1.00 |

Likely culprits, in priority order:
1. **Indicator orientation** — check `pos` tab; reoriented indicators must invert direction
2. **NaN handling** — was an indicator that should be NaN getting filled with 0?
3. **Z-score scope** — `Population Change` uses subset stats, not full-dataset stats
4. **Manual bin override** — the 6 manually-binned columns must use the boundaries in `BinningEngine.MANUAL_BINS`, not auto-selected

Run the `decision-scientist` agent on the suspected change. It writes a methodological audit to `docs/reviews/`.

---

## Performance gotchas

| Symptom | Cause | Fix |
|---------|-------|-----|
| Database save takes hours | Using ORM `add_all()` instead of `bulk_create()` | Always use `bulk_create()` (2000× faster) |
| Census tract pull takes forever | State wildcard not supported | Iterate per state (already automated) |
| BinningEngine hangs | `JenksCaspall` infinite loop on degenerate data | Use `FisherJenks` instead (already excluded) |
| Pipeline OOMs on tract | 88K rows × source data | Run with PostgreSQL, not SQLite |

---

## Where to look when really stuck

1. **`config/project.yaml`** — `lessons_learned` section captures every hard-won bug fix
2. **`CHANGELOG.md`** — every change with a date and tag; grep for the symptom
3. **`docs/sessions/`** — session-by-session logs; the most recent ones often discuss known issues
4. **`docs/design/`** — architecture and design references (`testing_guide.md`, `pipeline_guide.md`, etc.)
5. **`.claude/agents/decision-scientist.md`** — methodological audit checklist; useful for "is this a calibration regression?" questions
