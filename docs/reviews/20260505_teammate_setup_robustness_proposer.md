# Pipeline Setup Robustness: Entry Points, Diagnostics, and Failure Doctrine

**Author**: proposer
**Date**: 2026-05-05
**Type**: Investigation

---

## Problem Statement

A teammate pulled the FEMA CRIA repo, ran `scripts/run_full_pipeline.py --geography county --year ...`, and reached a silent-but-broken state: the `reference_indicators` table was empty (they had never run `scripts/import_reference_data.py`), so the pipeline pulled all data, post-processed it, calculated indicators, then logged "Indicator not found in database: <name>" 22 times — once per indicator — and persisted nothing to the database. The run appeared to complete successfully. The teammate also saw "Dropping 3496 rows with invalid index" and could not interpret it.

Two bugs in one: the pipeline cannot detect its own unconfigured state, and its warnings are opaque to anyone not already inside the codebase.

This document explores three questions:

1. Should "running the pipeline" be a single command? What does the ideal first-run UX look like?
2. What diagnostic artifacts would make remote debugging (Teams, copy-paste) trivial?
3. When should CRIA refuse to start, refuse to write, vs. continue with degraded output?

---

## What the Code Actually Does

### The three-script bootstrap sequence

The current model requires three scripts run in order:

```
import_reference_data.py   # populates reference_indicators, data_years
sync_geographies.py        # populates geographies table
run_full_pipeline.py       # pulls data, calculates, aggregates
```

Only `run_full_pipeline.py` has prominent README placement. The other two are listed in the "Import reference data only (one-time setup...)" note tucked inside the command-line reference block. `getting_started.md` does cover Step 3 (import reference data) explicitly, but it is step 3 of 6, easy to miss when a first-timer jumps straight to what looks like the main command.

### What actually breaks when reference_indicators is empty

In `src/core/indicators.py:440`, the `save_to_database()` method of `IndicatorCalculator` does:

```python
db_indicator = ref_repo.get_by_name(indicator_name)
if db_indicator:
    indicator_map[indicator_name] = db_indicator.id
else:
    logger.warning(f"Indicator not found in database: {indicator_name}")
```

`indicator_map` ends up empty. Later in the loop, `indicator_id = indicator_map.get(indicator_name)` is always `None`, so every record is silently skipped. The database write function returns successfully. The pipeline logs "Indicators saved to database" and proceeds to the next step. Zero rows are committed. No exception is raised.

The same pattern appears at `src/core/data_puller.py:491` for source data persistence.

### The "Dropping 3496 rows with invalid index" message

This comes from `data_puller.py:396`:

```python
idx_issues = pd.isna(data.index)
if idx_issues.sum() > 0:
    logger.warning(f"  Dropping {idx_issues.sum()} rows with invalid index")
    data = data.loc[~idx_issues, :].copy()
```

This fires because the outer `merge()` calls across API sources (Census ACS, CBP, EAVS, ARDA, POP) produce NaN index rows when data frames don't align. For county-level runs, ~3,496 is a consistent artifact of how CBP/EAVS outer merges expand the index with non-GEO_ID rows. The pipeline handles it correctly by dropping those rows before returning. But the warning is emitted at the same log level as a real data loss event. A user reading it has no way to distinguish "expected housekeeping" from "you lost 3,496 counties."

---

## Angle 1: The Shape of "Running the Pipeline"

### The current three-script model: feature or bug?

The argument for keeping them separate: `import_reference_data.py` is genuinely a one-time migration step that touches different concerns (Excel parsing, schema seeding) from the pipeline itself. `sync_geographies.py` is similarly a one-time Census API call that can be decoupled from production runs. Collapsing them would couple the pipeline's hot path to idempotency logic that normally runs once per deployment, and would hide the conceptual distinction between "setup" and "run."

That argument is technically sound and operationally wrong.

The conceptual distinction matters to the maintainer who understands the codebase. It is invisible to a teammate running the pipeline for the first time on a new machine. From the outside, there is one goal: produce CRIA output. The user does not experience "setup" as a separate intent — they experience it as "the pipeline failed for a reason I don't understand."

The deeper problem is that `run_full_pipeline.py` already contains setup intent in its own docstring header:

```
This script orchestrates the complete CRIA workflow:
1. Import reference data (if not already done)
2. Sync geographies from Census API (if not already done)
...
```

Steps 1 and 2 are described as pipeline steps, not prerequisites. The pipeline is describing itself as the unified entry point while not behaving like one.

### Approach A: Idempotent Bootstrap Inside run_full_pipeline.py

Add a `_bootstrap_if_needed(db_session)` function called at the top of `run_pipeline()` when `use_database=True`. It checks `SELECT COUNT(*) FROM reference_indicators` and `SELECT COUNT(*) FROM geographies WHERE geography_level = ?`. If either is zero, it runs the import/sync inline before proceeding.

**Pros**: Matches what the docstring already promises. First-run UX becomes one command. Idempotent — day-2 runs skip the bootstrap entirely (counts are nonzero). No new CLI surface.

**Cons**: Bootstrap entangles three concerns (Excel parsing, Census API, pipeline) in one call stack. If `import_reference_data.py` fails mid-import (e.g., malformed Excel), the error surface expands. The Census API call inside `sync_geographies` adds ~30 seconds to every cold-start that will never be needed again. The pipeline becomes harder to unit-test in isolation.

**Stronger objection**: "Idempotent bootstrap inside the pipeline" is the same design that leads to framework bloat. Rails `db:migrate` is not inside `rails server`. The distinction between setup and run is architecturally meaningful, and collapsing it here makes the right trade-off for the wrong reasons.

**Calibration impact**: None. Bootstrap reads Excel and populates reference tables; it does not touch indicator calculation or binning.

**Risk level**: Low. The bootstrap path is gated on empty tables and can be made opt-out with `--skip-bootstrap`.

### Approach B (bold): A Single `cria` Entry Point That Handles Everything

Replace the three scripts with a single `cria` CLI verb tree:

```
cria bootstrap                    # runs import_reference_data + sync_geographies
cria run --geography county --year 2024 --export-excel
cria diagnose                     # (see Angle 2)
```

Implemented as a `scripts/cria.py` (or `pyproject.toml` console script entry point) that dispatches. `run` calls `_bootstrap_if_needed()` as a pre-check that hard-fails with a clear message rather than auto-fixing.

**Pros**: Discoverable. `cria --help` shows all verbs. README's Quick Start becomes two commands: `cria bootstrap` then `cria run`. The error message for an un-bootstrapped DB is "Run `cria bootstrap` first" rather than 22 silent warnings and a missing database write. Day-2 experience is unchanged — `cria run` is idempotent on an already-bootstrapped DB because the pre-check detects non-empty tables and skips. Adds `cria diagnose` as a natural verb (see Angle 2).

**Cons**: Adds a new CLI layer. Breaks existing scripts/ invocations that teammates may already have in their notes or documentation. Requires updating README, `getting_started.md`, and any automation that calls the scripts directly.

**Stronger objection**: "We already have a three-script model that the docs explain. The problem is documentation, not architecture. Adding a fourth abstraction layer doesn't fix the root cause." This is legitimate. The README's Quick Start already says `poetry run python scripts/run_full_pipeline.py` — if we add `cria run`, we have four possible entry points, not three.

**Rebuttal**: The objection assumes the docs are the problem. They are not. Docs can explain ordering requirements; they cannot enforce them. The reason the teammate hit this failure mode is that they read the README Quick Start, which shows only one command, and ran it. The docs that explain the three-script sequence are in `getting_started.md` step 3, which they did not read because the Quick Start implied they didn't need to.

**Calibration impact**: None. CLI reshaping does not touch calculation logic.

**Risk level**: Medium (breaking change to existing invocation patterns, but strictly additive if old scripts remain).

### Approach C: Run_full_pipeline.py Refuses to Continue Without Bootstrapped Tables (Pre-flight Guard)

Not "add a pre-flight check" in the generic sense, but specifically: when `use_database=True` and `reference_indicators` count is zero after `init_db()`, the pipeline raises a clear error before pulling any data.

```
ERROR: reference_indicators table is empty.
Run: poetry run python scripts/import_reference_data.py
Then re-run the pipeline.
```

**Why this specific check matters more than other checks**: The empty `reference_indicators` table is the single failure mode that produces a complete false-positive run — all computation succeeds, all logs say "saved to database," zero data is persisted. Every other error class in the pipeline (Census API failure, bad key, timeout) either raises an exception or logs a hard error. This one is uniquely silent. The check costs one `SELECT COUNT(*)` query at startup and converts a 30-minute false-positive run into an immediate actionable error.

**Pros**: Minimal surface change. Preserves three-script model. Actionable error message.

**Cons**: Doesn't help with the discovery problem — the teammate still has to know to run import first; the check just fails loudly instead of silently. Does not fix the 22-warning UX for future cases where some but not all indicators are missing from the DB (e.g., a schema migration added new indicators but re-import wasn't run).

**Calibration impact**: None.

**Risk level**: Very low.

### Recommendation on Angle 1

Approach B (unified `cria` CLI) is the right long-term direction, but it is scope that exceeds the immediate problem. The immediate fix is Approach C (pre-flight guard on empty `reference_indicators`). Implement C now. Plan B is a separate CONOP.

The one strong argument for Approach A (auto-bootstrap inside run_pipeline) over Approach C is that it converts "fail loudly" into "just work." But auto-bootstrap hides the fact that setup happened, making subsequent debugging harder when the auto-bootstrap itself fails for a non-obvious reason. Loud failure with an actionable message is strictly better for a team debugging over Teams.

---

## Angle 2: Diagnostics for Remote Debugging

### The problem is information asymmetry, not distance

When a teammate pastes terminal output into Teams, the maintainer is reconstructing a state they cannot observe. The current logs tell you what the pipeline tried to do but not what the environment contains. "Indicator not found in database: Poverty" tells you the lookup failed, not whether the table is empty, has the wrong schema version, or has a name mismatch from a prior import with different Excel data.

### Approach A: Structured `--report` Flag on run_full_pipeline.py

Add `--report` to `run_full_pipeline.py`. On completion (success or failure), write `data/output/pipeline_report_<geography>_<year>_<timestamp>.json` containing:

```json
{
  "run_id": "county_2024_20260505T143200",
  "geography": "county",
  "year": 2024,
  "status": "complete" | "failed",
  "error": null | "...",
  "env": {
    "census_api_key_set": true,
    "census_api_key_format_valid": true,
    "database_url": "sqlite:///./cria.db",
    "acs_year": 2024
  },
  "db_state": {
    "reference_indicators_count": 22,
    "data_years_count": 6,
    "geographies_county_count": 3143,
    "source_data_rows": 0,
    "indicators_rows": 0
  },
  "pipeline": {
    "source_data_shape": [3143, 85],
    "indicators_shape": [3143, 22],
    "indicators_persisted": 0,
    "warnings": [
      "Indicator not found in database: Poverty",
      "..."
    ]
  }
}
```

The key insight: `indicators_persisted: 0` alongside `indicators_shape: [3143, 22]` is an immediately interpretable signal. A teammate pastes the JSON; the maintainer spots the divergence in 10 seconds.

**Pros**: Actionable, shareable, timestamped. Does not require real-time interaction — the report is written after the run. Catches the empty-table failure mode even if the pre-flight guard is not yet implemented (defense in depth). The `db_state` block is the key addition: it captures what the DB contained at run time, not just what the pipeline tried to do.

**Cons**: Adds an output file format to maintain. If the JSON structure changes, scripts that parse it break. `--report` is opt-in, so teammates have to know to use it.

**Stronger objection**: "This is documentation of a failure, not prevention of it. The teammate still ran a broken pipeline; the report just tells you it was broken faster." True. But a report-based approach has one advantage the pre-flight guard lacks: it tells you *how* broken in a structured, shareable form. The pre-flight guard and the report are not alternatives; they are layers.

### Approach B (bold): `cria diagnose` as a First-Class Command

A standalone `scripts/diagnose.py` (or `cria diagnose` verb) that, when run, captures the full machine state into a single shareable file:

```
CRIA Diagnostic Report — 2026-05-05T14:32:00
==============================================
Environment
  Python:           3.11.9
  Platform:         linux (Ubuntu 22.04)
  DATABASE_URL:     sqlite:///./cria.db [accessible: YES]
  CENSUS_API_KEY:   set, format VALID (40-char hex)
  ACS_YEAR:         2024

Reference Data
  reference_indicators:  0 rows  [PROBLEM: table is empty — run import_reference_data.py]
  data_years:            0 rows  [PROBLEM: table is empty — run import_reference_data.py]

Geographies
  county:   0 rows  [PROBLEM: run sync_geographies.py --level county]
  state:    0 rows
  tract:    0 rows
  tribal:   0 rows

Parquet Cache
  data/geographies/county.parquet:   EXISTS (3143 rows)
  data/geographies/state.parquet:    EXISTS (51 rows)
  data/geographies/tract.parquet:    EXISTS (84,414 rows)
  data/geographies/tribal.parquet:   EXISTS (575 rows)

Census API
  Status check (state-level canary):  [not tested — use --test-api to run live check]

Recent Pipeline Outputs
  data/output/cria_results_county_2024.xlsx:  NOT FOUND
```

The output is human-readable (paste-into-Teams) and machine-readable (write to `diagnostic_<timestamp>.txt`). The `[PROBLEM:]` tags are the key: they are actionable directives, not raw facts.

**Pros**: Solves the information asymmetry problem directly. A teammate runs `cria diagnose`, pastes the output, and the maintainer sees the exact state without inference. The Census API canary check (optional `--test-api` flag to avoid rate-limiting in routine use) catches key validity without a full pipeline run. The parquet cache section explains why the pipeline can still pull data even when the geographies table is empty — a common source of confusion.

**Cons**: Must be kept in sync with the actual DB schema and settings model. If a new table or env var is added, `diagnose.py` silently omits it unless updated. Requires discipline to maintain.

**Stronger objection**: "Runbooks and diagnostic commands are a maintenance burden. The real fix is making the pipeline fail loudly so the diagnosis is obvious." This is the correct philosophical objection. A `diagnose` command is an escape hatch for complexity that should not exist. But CRIA's complexity is not optional — the multi-table bootstrap, Census API key format issues, and year configuration are intrinsic. The question is not whether complexity exists but whether the user needs a mental model of the internals to debug it. `cria diagnose` answers "no."

**Rebuttal to the strongest objection**: The pre-flight guard (Angle 1, Approach C) makes the specific empty-table case fail loudly. `cria diagnose` covers every other state — wrong year, correct table counts but wrong data vintage, parquet cache present but DB geographies missing, Census API key valid but wrong format. These cases cannot all be caught by pre-flight guards without making the startup path as complex as the diagnostic command itself.

### Approach C: Structured Logging Mode

Add a `--log-json` flag or `LOG_FORMAT=json` env var that emits every log line as a JSON record rather than free text. Enables `grep '"level":"WARNING"'` on pasted output.

**Assessment**: Useful as an eventual infrastructure improvement but does not help the immediate Teams-paste use case. Structured logs require tooling to read; the teammate is pasting into a chat window. Pass on this for the immediate problem.

### Recommendation on Angle 2

Implement `cria diagnose` (Approach B) as the primary diagnostic artifact. The structured `--report` flag (Approach A) is a lower-priority complement that adds persistent evidence after a run. Do `diagnose` first; it solves the asymmetric-debugging problem at the root.

The `--report` flag should be automatic (always written) rather than opt-in, to ensure the artifact exists for post-mortem analysis even when a teammate didn't know to request it. Make the file path logged prominently at the end of every run.

---

## Angle 3: Fail-Loud vs. Fail-Gracefully Doctrine

### The tension is real

The pipeline's "log warning and skip" pattern is intentional in at least one well-motivated case: if an indicator is removed from the active set, a running pipeline should not crash because its `indicator_id` lookup returns None. A partial run that produces 21 of 22 indicators is better than a crash that produces zero.

But the teammate's experience reveals that "log and skip" applied to the wrong class of failures converts a catastrophic outcome (zero database persistence) into an apparent success. The question is where to draw the lines.

### A Proposed Doctrine

**Class 1 — Refuse to Start (hard fail before any computation)**

These are configuration failures that make the entire run meaningless. The pipeline should raise a hard error before pulling data:

- `reference_indicators` table is empty when `use_database=True`
- `DATABASE_URL` is set but the database cannot be reached
- `CENSUS_API_KEY` is absent or fails the format heuristic AND `--skip-pull` is not set (already implemented as a soft warning; should be a hard fail if the key is clearly wrong)

*Rationale*: In these cases, 100% of the pipeline's work is wasted. There is no recoverable degraded output. Failing fast saves 15–30 minutes of API calls.

**Class 2 — Refuse to Write, Continue Computing (soft fail at persistence)**

These are data integrity failures where the computation succeeds but DB write semantics are violated:

- `indicator_map` is entirely empty after the DB lookup loop (zero indicators found in reference table)
- `geo_id_map` returns zero entries for the target geography level
- Any `bulk_create()` call that would insert zero rows after processing 3,000+ geographies

*The current behavior*: log a warning per indicator and return silently. *Proposed behavior*: after building `indicator_map`, check its length. If `len(indicator_map) == 0` and `len(self.reference) > 0`, that is a contradiction — the pipeline calculated 22 indicators but found zero corresponding DB records. Raise a `PipelineDataIntegrityError` with actionable text rather than swallowing it.

*Rationale*: Silently writing zero rows while logging "saved to database" is a correctness violation. The user has no feedback that the write failed. The pipeline should refuse to emit false-positive success messages.

**Class 3 — Continue with Degraded Output (logged clearly)**

These are expected partial-data cases that have legitimate interpretations:

- An indicator has no data for a specific geography (e.g., EAVS non-reporting states produce NaN for Inactive Voter) — continue, NaN is the correct value
- `Dropping N rows with invalid index` — continue, this is housekeeping from the outer merge; **but log it at DEBUG level, not WARNING**, and add a comment explaining it is expected
- A single indicator's API call fails — log ERROR for that indicator, continue with the remaining 21
- Tribal geography drops non-ACS columns — this is by design; log at INFO, not WARNING

*The key principle*: degraded output is acceptable when the degradation is bounded (one indicator out of 22, one state out of 50) and the user receives an accurate accounting. It is not acceptable when the degradation is total (zero DB writes) and the signal is ambiguous.

**Class 4 — Warn and Note in Report (informational)**

These are benign artifacts that look alarming but are correct behavior:

- `arctanh(1.0) RuntimeWarning` on the correlation diagonal — suppress or document
- Connecticut 18-entry duplication — log at DEBUG, it is handled
- Puerto Rico Limited English NaN — log at DEBUG

*The current behavior promotes these to WARNING or INFO*, where they compete with real warnings for attention. In a 30-minute county run, a teammate sees dozens of log lines. Real warnings drown in the noise.

### The Strongest Objection to a Hard-Fail Doctrine

"Hard failing on empty `indicator_map` will break `--no-db` runs, which intentionally bypass the database. Those runs are valid and should not require a populated `reference_indicators` table."

This is a real constraint. The `--no-db` flag exists precisely to allow pipeline runs without database setup. The pre-flight guard and the "refuse to write" check must both be conditional on `use_database=True`. When `use_database=False`, the pipeline should operate exactly as today — no DB checks, no DB writes, no DB errors.

A secondary objection: "What about partial indicator sets? If someone adds an indicator to `indicators.yaml` but forgets to re-import `reference_indicators`, should the whole write fail?" The answer is no — a partially populated `indicator_map` (20 of 22 found) should log a WARNING for the missing 2 and proceed. The hard fail applies only to the case where `len(indicator_map) == 0`, i.e., the entire reference table is missing.

### Recommended Doctrine Summary

| Condition | Behavior | Log Level | Why |
|-----------|----------|-----------|-----|
| `reference_indicators` empty + `use_database=True` | **Refuse to start** | ERROR | 100% of DB work is wasted |
| Census API key absent/invalid + not `--skip-pull` | **Refuse to start** | ERROR | 100% of pull work is wasted (already soft-implemented) |
| `indicator_map` empty after reference lookup + `use_database=True` | **Refuse to write** | ERROR | False-positive "saved to database" is a correctness violation |
| Single indicator API call fails | Continue, log per-indicator | ERROR per indicator | 21 of 22 indicators is recoverable |
| EAVS non-reporting states → NaN | Continue | DEBUG | Expected, bounded, documented |
| "Dropping N rows with invalid index" | Continue | DEBUG | Expected merge artifact |
| Zero-vote state Inactive Voter nullification | Continue | INFO | Expected domain logic |
| arctanh(1.0) RuntimeWarning | Continue | DEBUG | Mathematical artifact, functionally correct |

---

## Cross-Cutting: The "Dropping 3496 rows" Message Specifically

This message is emitted in `DataPuller._post_process_data()` when NaN index rows are dropped after outer merges. It fires every run on every county pipeline run. It is expected and correct behavior. But it is logged at WARNING level and contains no context.

The fix is two-character: change `logger.warning` to `logger.debug` and append `(expected merge artifact — not data loss)`. This does not require any of the architectural changes above and eliminates one of the two confusing signals the teammate saw. It should be a quick standalone fix independent of the larger robustness work.

---

## Open Questions

1. **Does `--no-db` mode warrant its own pre-flight logic?** Currently, `--no-db` bypasses all database checks and writes. Should `cria diagnose` still run and report on the DB state even when the current run is `--no-db`? (Recommendation: yes — the user may be in `--no-db` mode because the DB is broken, making the diagnose output more valuable.)

2. **Should pipeline_report.json be written even on success?** The case for "always write": it creates an audit trail of every run's DB state, useful for retroactive debugging. The case against: it creates file clutter in `data/output/` and may confuse users who interpret the presence of a report file as a problem indicator. Recommendation: write on failure always; write on success only with `--report` flag.

3. **What is the right threshold for "refuse to write" on partial indicator_map?** Zero-of-22 is clear. What about 1-of-22? The proposed doctrine uses `len(indicator_map) == 0` as the threshold, which avoids over-blocking on legitimate partial indicator scenarios. This should be explicitly documented.

4. **Does `cria diagnose` need to test the Census API live?** A live API test catches key validity definitively but costs a network call and rate-limit exposure. Recommended: test by default using the cheapest possible endpoint (e.g., a single state-level ACS variable), with `--no-api-test` flag to skip for environments without outbound access.

---

## Validation Plan

For any implementation that emerges from this investigation:

- **Pre-flight guard**: Verify that an empty `reference_indicators` table causes a hard fail with actionable message, not silent success. Verify that `--no-db` mode bypasses the guard entirely. Verify that a populated table passes through with no behavior change.
- **Refuse-to-write check**: Verify that `len(indicator_map) == 0` raises `PipelineDataIntegrityError`. Verify that a partial map (some indicators missing) logs WARNING but continues. Verify that a fully populated map (22/22) writes all records as before.
- **Debug-level "Dropping N rows"**: Verify the message no longer appears at WARNING in a standard county run's console output. Verify it is still accessible at DEBUG level (`--log-level debug`).
- **cria diagnose**: Verify it runs without starting the pipeline. Verify it reports correct counts for both empty and populated DB states. Verify `[PROBLEM:]` markers appear for empty tables. Verify the Census API canary test fires with `--test-api` and is skipped without it.
- **Calibration**: None of these changes touch indicator calculation, binning, or aggregation. No calibration re-run needed. Confirm by checking that `run_pipeline()` with a populated DB produces identical output before and after.
