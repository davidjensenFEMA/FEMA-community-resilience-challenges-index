# Teammate Setup Robustness — Audit of Two Proposals

**Author**: quality-auditor
**Date**: 2026-05-05
**Type**: Code review

Adversarial review of `20260505_teammate_setup_robustness_data_engineer.md` and
`20260505_teammate_setup_robustness_proposer.md`. Findings verified against
working-tree code.

---

## Audit: data-engineer proposal

### Factual claims — verified

- `data_puller.py:491` (warning), `:488` (soft-skip conditional), `:543-549`
  (bulk-insert fall-through), `:552` (skipped-geos warning) — **all confirmed**.
- `indicators.py:440`, `:437` — **confirmed**.
- `_load_reference` at `data_puller.py:85` does
  `dropna(subset=["Order_2023"])` — **confirmed**. The "Order_2024 rename
  silently zeros indicators" hazard is real.
- `confirm_suspect_api_key` at `run_full_pipeline.py:688` — confirmed
  (definition at `census_client.py:106`).
- `--no-db` flag at `run_full_pipeline.py:651-655` — confirmed.

### Findings

1. **MEDIUM — Missed the aggregator's silent-success path.** The proposal
   scopes the empty-`indicator_map` fix to `data_puller.py:484-491` and
   `indicators.py:433-440`, but `aggregator.save_to_database()` at
   `aggregator.py:700-780` has NO `indicator_map` at all — it writes purely
   keyed on `geography_id`. So if `geographies` is empty (sync skipped) but
   `reference_indicators` is populated, the aggregator silently writes zero
   rows the same way. The data-engineer correctly identified the parallel
   empty-`geographies` failure (Section 1, item 1) and proposed a preflight
   that checks both — that does cover the case at startup. But Recommendation 2
   ("fail-fast inside save_to_database") will not fire here because there's no
   indicator_map check to add; the check would have to be on
   `len(geo_id_map) == 0`. Worth stating explicitly.

2. **MEDIUM — Repository line numbers wrong.** Proposal says add `count()` at
   `repositories.py:~144` and `count_by_level()` at `~86`. Line 144 is inside
   `ReferenceIndicatorRepository.bulk_create` (correct class, but it's the end
   of the class, not "around line 144"). Line 86 is the END of
   `GeographyRepository.get_geo_id_map` — correct class, but
   `GeographyRepository` ends at line 97 (after `delete()`). The new method
   should land near line 97, not 86. Trivial but the implementer will hit
   merge conflicts.

3. **LOW — Drop-log threshold tuning hand-waved.** The 50%/60% threshold for
   WARNING-vs-INFO is admitted to be a guess ("tune empirically"). The author
   states 51.6% is the typical county case, then proposes a 50% threshold,
   then immediately walks it back to 60%. Ship the proposal with one threshold
   and a unit test that asserts a normal county pull produces INFO. Otherwise
   this lands as a flaky alert.

4. **LOW — Drop-log code path holds up at zero rows.** The proposed rewrite
   guards with `if n_dropped > 0:` so zero-drop runs emit nothing. Correct;
   note this is a behavior change (old code only logged when `> 0` too — so
   no regression). Confirmed safe.

5. **LOW — Doctor v1 list omits `data_years`.** `import_reference_data.py`
   populates both `reference_indicators` AND `data_years`. The doctor checks
   only `reference_indicators`. A teammate could partially seed and confuse
   the diagnosis. Cheap to add.

### Cost/benefit honesty
The proposal claims "two cheap SELECT count(*) queries". True for the
preflight. But the actual surface added is: 2 new repo methods + 2 unit tests
each + 1 preflight function + 2 fail-fast raises (each needing a regression
test that an in-memory DB triggers them) + 1 drop-log replacement (with a
threshold test) + 1 new script (doctor.py, ~9 checks) + each check needs a
test for both pass and fail paths + README change. Conservative count: ~15-20
new tests. "Low maintenance burden" is plausible but the claim should be
stated honestly as "moderate first-time cost, near-zero ongoing burden."

### Bias check
- **Confirmation bias**: The author frames Rec. 1 as "the smallest possible
  intervention" and lists no scenario where the preflight would FAIL the
  user (e.g., test fixtures that intentionally start empty). The
  `--allow-empty-db` escape hatch is mentioned but not designed.
- **Anchoring**: Anchored on the empty-`reference_indicators` story and only
  belatedly noticed the empty-`geographies` parallel (Section 1, item 1).
  Did NOT consider: wrong DATABASE_URL pointing at an empty SQLite file (the
  default URL is `sqlite:///./cria.db` — `init_db()` will silently create
  this file in CWD, then teammate's "real" DB stays untouched while pipeline
  reports success).

### Verdict
**PASS WITH CONCERNS**. Finding 1 is the only material gap; the rest are
implementation quibbles. The doctrine ("pipeline detects, setup scripts
execute") is well-defended and the explicit rejection of auto-bootstrap is
the right call.

---

## Audit: proposer proposal

### Factual claims — verified

- `indicators.py:440` and `data_puller.py:491` — confirmed.
- `data_puller.py:396` drop-log — confirmed.
- Three-script bootstrap sequence — confirmed.
- `--no-db` flag — confirmed.

### Findings

1. **HIGH — "Refuse to start if `DATABASE_URL` is set but unreachable" is
   essentially unreachable in the default case.** The settings default
   (`settings.py:87`) is `sqlite:///./cria.db`. SQLite will happily create
   a fresh empty DB file at that path. So the proposed Class 1 rule
   ("DATABASE_URL is set but the database cannot be reached") will only
   trigger for misconfigured PostgreSQL/remote DB users — which is a much
   smaller cohort than the failure mode that motivated the proposal. The
   real Day-1 silent failure is "DATABASE_URL points at a brand-new empty
   SQLite file in the wrong directory because the user `cd`'d before
   running" — `init_db()` silently creates it, every table reads as empty,
   and pipeline reports success. The proposal does not surface this
   directory-of-CWD trap at all.

2. **MEDIUM — `cria diagnose` example output makes a false promise.** The
   example shows `Census API ... [not tested — use --test-api to run live
   check]` while `DATABASE_URL: sqlite:///./cria.db [accessible: YES]` is
   reported as a fact. But "accessible" for SQLite means "CWD is writeable",
   which conflates two different things. Open question 4 admits the live
   API test is conditional but the DB "accessible" check is not designed
   with the same care. Spec the contract.

3. **MEDIUM — Doctrine table contradicts itself on key validity.** Class 1
   row says "Census API key absent/invalid + not `--skip-pull`: Refuse to
   start". But a valid key format does NOT guarantee a working key —
   `validate_census_api_key_format` (census_client.py:72) is a 40-hex-char
   regex. A teammate's key could pass format validation and still 401. The
   doctrine treats format validity as sufficient; it isn't. The diagnose
   command's `--test-api` flag is the right mechanism but the doctrine
   should reflect that the preflight is necessarily best-effort.

4. **MEDIUM — The "len(indicator_map) == 0 is a contradiction" assertion is
   incomplete.** The proposal says (Class 2): "if `len(indicator_map) == 0`
   and `len(self.reference) > 0`, that is a contradiction". True for
   data_puller and indicators, but the aggregator (aggregator.py:700+) has
   no indicator_map at all, so this rule literally cannot be applied there.
   Same gap as data-engineer Finding 1. Both proposals miss the aggregator.

5. **MEDIUM — Approach B (`cria` CLI) breaks the "scope exceeds problem"
   self-discipline the author imposes.** The author recommends Approach C
   (preflight guard) for now and Approach B for later — but then Angle 2
   recommends `cria diagnose` (Approach B), implicitly building the CLI
   layer they said they'd defer. If `diagnose` is a `scripts/diagnose.py`
   script (no `cria` verb), be explicit. If it is the start of `cria`, own
   it.

6. **MEDIUM — Recommendation to demote drop-log to DEBUG eliminates the
   genuine-anomaly signal.** The proposer's "two-character fix"
   (`logger.warning` → `logger.debug`) is wrong. If a future bug causes 90%
   of rows to drop instead of 50%, DEBUG is invisible by default. The
   data-engineer's threshold-based escalation is correct; the proposer's
   demotion is over-correction and would mask real regressions. **The two
   proposals contradict each other here, and the proposer's version is
   worse.**

7. **LOW — Open Question 2 has the wrong default.** "Write report on success
   only with `--report` flag, always on failure". This breaks the use case
   the author identified two paragraphs earlier ("teammates have to know to
   use it"). If reports are valuable, write them always; if not, don't write
   them on failure either. The split is incoherent.

### Bias check
- **Availability bias**: Heavy on CLI/UX patterns ("Rails db:migrate is not
  inside rails server") that read like web-framework analogies. CRIA is an
  ETL pipeline; the analogy doesn't quite fit, and the comparison is doing
  rhetorical work the doctrine doesn't need.
- **Confirmation bias**: Proposes `cria diagnose` then in Open Question 4
  immediately admits it has rate-limit and connectivity issues. The doubt
  is buried; the recommendation is firm. Either the rec or the doubt is
  wrong.
- **Recency bias**: Both proposals over-fit to the specific symptom the
  teammate reported. Neither examines the wider class: any setup state
  where pipeline produces output that LOOKS successful but isn't.

### Verdict
**PASS WITH CONCERNS**. Findings 1, 4, and 6 are material. Finding 6 in
particular is a direct conflict with the data-engineer proposal that the
user must resolve before either lands.

---

## Synthesis

### Highest-confidence problems (with code evidence)

1. **Both proposals miss the aggregator's silent-success path.** At
   `aggregator.py:700-780`, `save_to_database()` keys writes only on
   `geo_id_map`. If `geographies` is empty, every row is skipped (`:728`),
   `aggregate_records` is empty, and the function falls through to the
   "No aggregate records to save" warning at `:777` while `PIPELINE COMPLETE`
   still prints. Neither the empty-`indicator_map` fail-fast nor the
   per-indicator warning fix touches this. The data-engineer's preflight
   does cover it at startup (catches empty `geographies`), but the
   defense-in-depth fail-fast proposed at "Recommendation 2" does not have
   an aggregator analogue and should.

2. **Default `DATABASE_URL` is `sqlite:///./cria.db`** (`settings.py:87`),
   which means `init_db()` silently creates a new SQLite file in the user's
   current working directory. A teammate who runs the pipeline from a
   different directory than `import_reference_data.py` ends up with TWO
   SQLite files, both empty from the pipeline's perspective, both
   "successful." Neither proposal flags this CWD trap. The data-engineer's
   doctor.py Section 4 lists DATABASE_URL parseability but not "is this the
   same DB file the import script wrote to." A doctor-level check should
   compare ref-table counts AND log the absolute resolved DB path.

3. **Proposer's drop-log fix (WARNING → DEBUG) is a regression risk.** The
   data-engineer's threshold-based version (escalate on >50%) is correct;
   the proposer's blanket demotion would silence genuine 90%-row-loss
   regressions. The proposer's `--log-level debug` workaround does not help
   the operator who runs in production with default log level. Take the
   data-engineer's version.

### Agreement worth preserving

- Both reject auto-bootstrap. The reasoning is independently sound (different
  arguments arrive at the same conclusion).
- Both propose a preflight check on empty `reference_indicators`. The
  data-engineer's framing is more precise (pipeline detects, setup scripts
  execute) but the proposer's Class-1/Class-2 doctrine is the right
  conceptual frame for thinking about WHEN to apply it.
- Both want a richer drop-log message; they only disagree on the level
  policy.
- Both want a doctor/diagnose tool. Build one, not two.

### Materially wrong

- Proposer Finding 1 (DATABASE_URL Class 1 rule unreachable in default
  config) — the proposal's reach is narrower than its language suggests.
- Proposer Finding 6 (drop-log demotion) — actively worse than the
  data-engineer alternative.
- Both proposals' aggregator gap.
- Data-engineer line-number references for `repositories.py` (~144, ~86)
  point at the wrong insertion sites.

### Questions to ask before deciding

1. Will `import_reference_data.py` and the pipeline always run with the
   same CWD in your team's setup? If not, the doctor must report the
   resolved absolute DB path so two-DB confusion is visible.
2. Do you want `--no-db` to bypass the preflight or to run a degraded
   "warn but continue" version? The proposer is explicit (yes, bypass);
   the data-engineer's doctrine implies bypass but doesn't state it.
3. Is the doctor a standalone script or the seed of a `cria` CLI? Both
   proposals are ambiguous; pick one before either lands so the
   maintenance story is honest.
4. What is the regression-test bar? Both proposals omit explicit "test
   that an empty in-memory DB triggers the new fail-fast path" steps.
5. Who owns the doctor's check list as the codebase evolves (new tables,
   new env vars)? Without an owner it goes stale within two quarters.
