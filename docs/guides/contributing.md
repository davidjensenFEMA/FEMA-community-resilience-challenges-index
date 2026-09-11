# Contributing to CRCI

How to make a code change without breaking calibration, the test suite, or the team.

For domain context first, read [methodology.md](methodology.md) and [special_cases.md](special_cases.md). For terminology, see [glossary.md](glossary.md).

---

## Before you change code

A 60-second pre-flight checklist:

1. **Pull latest `main`.** `git pull origin main`.
2. **Check open work.** [`docs/tasks.md`](../tasks.md) — is your area already in flight?
3. **Read the relevant lesson.** [`config/project.yaml`](../../config/project.yaml) `lessons_learned` — search for keywords related to your change. Many "obvious" improvements were already tried and reverted.
4. **Check special cases.** [special_cases.md](special_cases.md) — does your change touch one of the 15 known quirks?

---

## Branch and PR conventions

There is no enforced format yet, but a working convention has emerged from CHANGELOG style:

### Commit messages

Tag the area in brackets:

```
[fix][core] Brief description of the change
[feature][api] What was added
[docs] What changed in the docs
[test] What tests were added/updated
[refactor][db] What was restructured
[config] What configuration changed
```

Common tags: `fix`, `feature`, `docs`, `test`, `refactor`, `config`, `data`, `infra`, `bugfix`, `performance`.

Use the body to explain *why*. The diff already shows *what*.

### Branches

- `main` is the trunk; production-ready at all times.
- Feature branches: `feature/<short-name>` or `fix/<short-name>`.
- The currently active long-lived branch is `pipeline-dev` (per `git branch -v`).

### PRs

No template exists yet. A useful structure:

```markdown
## What
1-line summary of the change.

## Why
The motivation. Reference an issue, a project.yaml lesson, or a CHANGELOG entry if applicable.

## Calibration check
- [ ] Ran `--geography county --year 2024` against this branch
- [ ] Spot-checked the `agg` tab against the previous output
- [ ] No bin distributions shifted unexpectedly

## Tests
- New tests: `tests/<file>`
- Updated tests: `tests/<file>`
- Run: `poetry run pytest`
```

---

## Running tests

For the testing *philosophy* (why tests live in `tests/` and not `src/tests/`, how fixtures are organized, what each test type is for), see [`docs/design/testing_guide.md`](../design/testing_guide.md). This section covers the day-to-day commands.

### The whole suite

```bash
poetry run pytest                          # All 541 tests
poetry run pytest -v                       # Verbose
poetry run pytest --tb=short              # Short traceback
poetry run pytest -x                       # Stop on first failure
```

### A single test or test file

```bash
poetry run pytest tests/test_aggregator.py                       # One file
poetry run pytest tests/test_aggregator.py::test_create_aggregate # One test
poetry run pytest tests/test_aggregator.py -k "binning"          # Match by substring
```

### By marker

The suite uses these markers (from `pyproject.toml`):

| Marker | Meaning |
|--------|---------|
| `unit` | Fast tests, no external dependencies. Auto-applied to anything in `tests/unit/`. |
| `integration` | Database or API calls. Auto-applied to `tests/integration/`. |
| `slow` | Tests > 10 seconds |
| `requires_db` | Needs a running database |
| `requires_api` | Needs network access to a Census/CBP/etc. endpoint |

Run a subset:

```bash
poetry run pytest -m unit                  # Just unit tests
poetry run pytest -m "not slow"            # Skip slow tests
poetry run pytest -m "unit and not requires_db"
```

### Coverage

```bash
poetry run pytest --cov=src                # Coverage summary in terminal
poetry run pytest --cov=src --cov-report=html  # HTML report at htmlcov/index.html
poetry run pytest --cov=src --cov-report=term-missing  # Show uncovered lines
```

Current critical-path coverage targets:
- `src/core/aggregator.py`: > 90%
- `src/core/binning.py`: > 90%
- `src/api/census_client.py`: currently 50% — known gap, prioritize when extending

### Test timeout

Individual tests timeout after 300s (5 min) by default — set via `pyproject.toml:timeout = 300`. Override per-test with `@pytest.mark.timeout(N)`. This was added after an 18-day runaway test incident on a shared server (2025-12-22 lesson).

---

## Adding a test

Tests live in `tests/`. Use the existing structure:

```
tests/
├── conftest.py              # Shared fixtures (test DB, sample data)
├── unit/                    # Auto-marked @pytest.mark.unit
│   ├── test_aggregator.py
│   ├── test_binning.py
│   └── ...
├── integration/             # Auto-marked @pytest.mark.integration
│   └── test_pipeline_e2e.py
└── fixtures/                # Synthetic data files
```

### Pattern: known-answer test

For indicator/aggregation logic, write a test with hand-computed expected values:

```python
def test_poverty_indicator():
    source_data = pd.DataFrame({
        "S1701_C02_001E": [100, 200, 50],   # Below poverty
        "S1701_C01_001E": [1000, 1000, 500], # Total population
    }, index=["A", "B", "C"])

    result = calc._divide(source_data, num="S1701_C02_001E", denom="S1701_C01_001E")

    assert result.loc["A"] == 10.0   # 100/1000 * 100
    assert result.loc["B"] == 20.0
    assert result.loc["C"] == 10.0
```

### Pattern: regression guard

For special-case handling, write a test that fails if the special case regresses:

```python
def test_eavs_negative_88_maps_to_nan():
    """EAVS -88 ('does not apply') must map to NaN, not 0. (2026-03-25 lesson)"""
    raw = pd.Series([100, -88, -99, 0])
    cleaned = clean_eavs_value(raw)
    assert pd.isna(cleaned[1])  # -88 → NaN
    assert pd.isna(cleaned[2])  # -99 → NaN
    assert cleaned[3] == 0      # genuine zero stays
```

### Pattern: NaN behavior test

Whenever you touch indicator math, test the NaN case:

```python
def test_zero_denominator_returns_nan():
    """Zero denominator is undefined, not zero. (2026-03-25 lesson)"""
    source = pd.DataFrame({"num": [10], "denom": [0]}, index=["A"])
    result = calc._divide(source, num="num", denom="denom")
    assert pd.isna(result.loc["A"])  # NOT 0
```

---

## Calibration check

If your change touches indicators, aggregation, binning, or anything in `src/core/`, run a calibration check before committing.

There is no automated `scripts/check_calibration.py` yet. The manual procedure:

```bash
# 1. Generate output on this branch
poetry run python scripts/run_full_pipeline.py \
  --geography county --year 2022 --export-excel --no-db

# 2. Compare against the calibration baseline
# Baseline files live in: data/output/archive_pre_fix/ (or wherever the
# project.yaml-noted calibration target was last validated)
python3 -c "
import pandas as pd
new = pd.read_excel('data/output/cria_results_county_2022.xlsx', sheet_name='agg', index_col=0)
old = pd.read_excel('data/output/archive_pre_fix/cria_results_county_2022.xlsx', sheet_name='agg', index_col=0)
print('Correlation:', new['cri'].corr(old['cri']))
# Target: >= 0.94 for county 2022
"
```

If correlation drops:
1. Run the `decision-scientist` agent (`.claude/agents/decision-scientist.md`) — it will write a methodological audit to `docs/reviews/`.
2. Read the audit's findings before proceeding.
3. Common causes ranked in [troubleshooting.md "Calibration drift"](troubleshooting.md#calibration-drift).

---

## Pre-commit checks

The project has two slash commands for pre-merge sanity:

- `/pcc` — Pre-Code Check. Quick, runs the same checklist every push.
- `/pci` — Pre-Code Inspection. Context-aware deeper review based on the diff.

These are intended to be invoked during a Claude Code session at the end of work. If you're not using Claude, the equivalent is:

```bash
poetry run pytest                          # Tests pass
git diff --check                           # No whitespace issues
git status                                 # Nothing untracked you forgot
```

For a methodological change, also run the `decision-scientist` agent.

---

## CHANGELOG conventions

After a non-trivial change, add an entry to [`CHANGELOG.md`](../../CHANGELOG.md). The format:

```
### YYYY-MM-DD
- `[tag]` Brief description of the change
```

Tags match commit-message tags (`fix`, `feature`, `docs`, `test`, etc.).

The session-end workflow (`/session-end` slash command) usually does this for you. If you're committing manually, do it manually.

---

## Updating `config/project.yaml`

`project.yaml` is the project's central state file. The `state.last_session`, `state.active_work`, `state.known_issues`, and `state.recent_completions` fields are intended to be updated session-by-session.

Add to `lessons_learned` whenever:
- A bug fix took non-trivial debugging
- A design decision is non-obvious from the code
- A workaround is in place that someone might try to "improve" later

Always include a `date:` and a `lesson:` body. The future-you who is debugging this will thank present-you.

---

## The `.claude/` directory

The repo has a custom Claude Code agent system:

- `.claude/agents/` — 6 agents:
  - `cria-analyst` — domain expert (indicators, aggregation, binning, calibration)
  - `data-engineer` — pipeline, API, DB specialist
  - `decision-scientist` — methodological auditor (CRCI design)
  - `quality-auditor` — adversarial reviewer (separation of duties; read-only)
  - `statistical-tester` — adversarial test engineer (write-access to tests/ only)
  - `proposer` — pre-implementation problem analyst
- `.claude/teams/` — 6 team templates: `bug-fix`, `code-review`, `data-pipeline`, `indicator-development`, `test-validation`, `full-pipeline-validation`

Slash commands relevant to contributors:

| Command | Purpose |
|---------|---------|
| `/session-start` | Load context for a new session |
| `/session-end` | Close session (PCC, commit, docs) |
| `/task` | Manage `docs/tasks.md` (Task → TCS → CONOP → OPORD escalation) |
| `/sitrep` | Generate team-facing status report |
| `/pcc` | Pre-Code Check (fast safety) |
| `/pci` | Pre-Code Inspection (deep review) |
| `/implement-feature` | Guided feature workflow |

If you're not using Claude Code, none of this applies — but the agent definitions encode the team's "what to check before merging" knowledge and are worth reading even as plain markdown.

---

## Adding a new indicator

Step-by-step in [extending.md](extending.md#adding-a-new-indicator). Key prerequisites:

1. Pick a function type from the five available (`divide`, `reverse_divide`, `divide_scalar`, `max`, `mean`).
2. Identify the source (ACS / CBP / EAVS / ARDA / POP) and confirm a column name.
3. Decide orientation (`Augment == "reverse"`?).
4. Add to `data/cria_data_reference.xlsx` (Status sheet) AND `config/indicators.yaml`.
5. Re-run `scripts/import_reference_data.py`.
6. Add a known-answer test.
7. Calibration check (correlation will not be 1.0 anymore — that's expected; document the new baseline).

---

## Things to never do

- Skip the calibration check on a `src/core/` change. The 0.94/1.0 targets exist for a reason.
- Add a `# TODO: handle NaN` and ship. NaN handling is one of the most-bug-prone areas; either handle it or open an issue.
- Use ORM `session.add_all()` for >100 rows. Use `bulk_create()` (2000× faster).
- Convert a `result.loc[denom==0] = 0` pattern. Zero denominator means undefined (NaN), not zero. (2026-03-25 lesson.)
- Add `JenksCaspall` back to the binning method pool. It hangs on degenerate data. (2025-12-05 lesson.)
- Mock the database in indicator tests. Use the synthetic test fixtures in `tests/fixtures/` instead.

---

## When stuck

1. Re-read [methodology.md](methodology.md) and [special_cases.md](special_cases.md).
2. Check `config/project.yaml` lessons_learned.
3. Check the most recent `docs/sessions/` for prior context.
4. Run the `decision-scientist` agent for methodological questions.
5. Run the `quality-auditor` agent for "is my change safe?"
6. Ask a teammate. The escalation ladder is Task → TCS → CONOP → OPORD (see `/task`).
