# Defense-in-Depth Fail-Fast + Drop-Log Rewrite — Audit

**Author**: quality-auditor
**Date**: 2026-05-05
**Type**: Code review

Adversarial review of the data-engineer's defense-in-depth fail-fast (3 sites)
and drop-log rewrite (1 site). Verified against working-tree code.

**Test suite**: `607 passed` in 61.69s. All 15 new tests pass.

---

## Site 1 — `src/core/data_puller.py:520-550` (save_to_database fail-fast)

### Verification
- Indicator-map check at [src/core/data_puller.py:527-533](src/core/data_puller.py#L527-L533) — present, raises `RuntimeError`, names `import_reference_data.py`.
- Geo-id-map check at [src/core/data_puller.py:544-550](src/core/data_puller.py#L544-L550) — present, raises `RuntimeError`, names `sync_geographies.py --level county`.
- Existing per-indicator warn at [src/core/data_puller.py:521](src/core/data_puller.py#L521) (`Indicator not found in database: {name}`) — preserved, fires before new guard.
- Existing `db is None` early-return at [src/core/data_puller.py:502-504](src/core/data_puller.py#L502-L504) — fires BEFORE new guards (correct: no DB → quiet skip).

### Findings

1. **LOW — Guard expression assumes `self.reference` is a DataFrame.** `if not indicator_map and len(self.reference) > 0` will raise `TypeError` if `self.reference` is `None` (verified: `len(None)` raises). This is unreachable in practice because `_load_reference()` always returns a DataFrame, but if a future refactor allows None it becomes a latent bug. Cheap fix: `len(self.reference) if self.reference is not None else 0 > 0`.

2. **LOW — Empty `self.reference` (rows == 0) silently skips the guard.** If somehow the reference Excel loads with zero rows, `len(self.reference) > 0` is False and `indicator_map` is also empty — guard does NOT fire, function continues, `source_repo.bulk_create([])` writes nothing, no error. This is consistent with the doctrine ("data, not setup error") but worth naming: empty-reference is itself a setup error and is currently NOT caught here.

3. **PASS — Guard correctly placed AFTER the build-and-warn loop**, so single-indicator misses still warn before the all-miss raise.

---

## Site 2 — `src/core/indicators.py:432-469` (save_to_database fail-fast)

### Verification
- Indicator-map check at [src/core/indicators.py:446-452](src/core/indicators.py#L446-L452) — present, raises `RuntimeError`, message says `Cannot persist indicators` (correctly distinguishes from `source_data`).
- Geo-id-map check at [src/core/indicators.py:463-469](src/core/indicators.py#L463-L469) — uses `len(indicators.index) > 0` (correct local variable name, not `data.index`).
- Existing per-indicator warn at [src/core/indicators.py:440](src/core/indicators.py#L440) — preserved.

### Findings

1. **PASS — Cross-site consistency with data_puller** is high: same guard expressions, same error-message structure, same remediation commands. The only deliberate difference is the table name in the error string (`source_data` vs `indicators`), which is correct.

2. **LOW — Same `self.reference is None` latent bug as Site 1.** Same fix.

---

## Site 3 — `src/core/aggregator.py:719-731` (save_to_database fail-fast)

### Verification
- Geo-id-map check at [src/core/aggregator.py:725-731](src/core/aggregator.py#L725-L731) — present, raises `RuntimeError`, names `sync_geographies.py --level county` and `aggregate_indicators` table.
- Aggregator has NO indicator_map (writes keyed only on geography). Comment at [src/core/aggregator.py:723-724](src/core/aggregator.py#L723-L724) explicitly notes this. Correct doctrine application.
- Empty-`agg_df` early-return at [src/core/aggregator.py:705-707](src/core/aggregator.py#L705-L707) sits BEFORE the new guard at line 725. Confirmed correct ordering: no aggregate data → quiet return; data present but no geos → loud raise.

### Findings

1. **PASS — This site directly addresses Finding 1 of the prior audit** ([docs/reviews/20260505_teammate_setup_robustness_audit.md](docs/reviews/20260505_teammate_setup_robustness_audit.md) lines 31-40), which flagged that the aggregator's silent-success path was missed in the original proposal. The fix is exactly what the audit prescribed: guard on `len(geo_id_map) == 0` since there is no `indicator_map` axis.

2. **LOW — Existing `Skipped {n} geographies` log at [src/core/aggregator.py:794](src/core/aggregator.py#L794) is preserved** — partial misses still warn-and-continue. Test `test_partial_geo_miss_does_not_raise` exercises this path correctly.

---

## Site 4 — `src/core/data_puller.py:404-427` (drop-log rewrite)

### Verification
- Old behavior (single WARNING with no kept-count) at git HEAD `data_puller.py:393-394`: `logger.warning(f"  Dropping {idx_issues.sum()} rows with invalid index")`.
- New behavior at [src/core/data_puller.py:411-427](src/core/data_puller.py#L411-L427): conditional `logger.warning if pct_dropped > 60 else logger.info`, message includes dropped/kept/percent and named cause.
- Threshold operator: `>` (strict). At exactly `pct_dropped == 60.0` → INFO. Verified: `(60/100)*100 > 60` is `False`.
- Floor is INFO (NOT DEBUG) — consistent with the prior audit's rejection of the proposer's blanket DEBUG demotion.

### Findings

1. **MEDIUM — Threshold boundary is NOT tested.** The parametrized cases are 50% (3-of-6), 55.6% (5-of-9), 70%, 90%. The boundary value 60.0% itself is absent, and `60.5%` (smallest WARN trigger) is absent. If a future refactor flips `>` to `>=`, no test catches it. Add: `(40, 60, "INFO")` (60.0% → INFO under `>`) and `(99, 151, "WARNING")` (60.16% → WARNING under `>`).

2. **LOW — Drop-log message readability for very large numbers.** At a 90%-drop county-scale event (`n_dropped=6102, n_kept=678` of 6780), the f-string reads `dropped 6102 NaN-indexed rows (90.0%), keeping 678 valid rows`. Sensible. Spot-check at `n_dropped=1, n_total=2` (50%): `dropped 1 NaN-indexed rows (50.0%), keeping 1 valid rows`. Plural-noun bug ("1 rows") but cosmetic only.

3. **LOW — Cause text is precise but assumes the reader understands "outer-merge artifact".** A teammate seeing this for the first time may not connect "outer-merge" to "the source clients pull each indicator separately and the joined frame keeps unmatched keys as NaN-indexed rows". The data-engineer's wording is technically correct but assumes domain familiarity. Consider expanding to: "Pandas keeps unmatched keys as NaN-indexed rows when merging per-source pulls; these rows have no values from any source and are safe to drop."

4. **PASS — Zero-drop case correctly silent** ([src/core/data_puller.py:411](src/core/data_puller.py#L411) `if n_dropped > 0`). No regression vs old code (which also gated on `> 0`).

---

## Test Quality Audit

### Tests that prove correctness
- `test_threshold_chooses_log_level` — parametrized, asserts exactly-one log line per case (catches duplicate-log bugs), asserts level by name. Real test, not vacuous.
- `test_message_reports_kept_dropped_and_cause` — asserts each substring. If a future change drops `keeping {n}` from the message, this test fails. Real test.
- `test_empty_indicator_map_raises` (data_puller, indicators) — mutation-checked. If the new guard is removed, the function returns normally with empty `source_data_records` (no raise). Test would fail. Real test.
- `test_empty_geo_id_map_raises` (all 3 sites) — same mutation logic. Real test.
- `test_empty_agg_df_returns_early` (aggregator) — verifies the existing early-return sits BEFORE the new guard so empty results don't trigger the new raise. Important ordering test.

### Tests that pass but don't fully exercise the path
- `test_partial_indicator_miss_does_not_raise` (data_puller, indicators) — verifies no-raise + the per-indicator warn fires. Does NOT verify any records actually got persisted (column names in synthetic data don't match indicator names → loop produces empty record list anyway). The test PROVES the no-raise contract but is weakly probative of "warn-and-continue" because there's no continuing work to do. Stronger version: assert `source_repo.bulk_create` was called with N records where N corresponds to the resolved indicator(s).

### Mock fidelity
- Repository constructor patches use `patch("src.core.data_puller.GeographyRepository", return_value=repo_mock)` — correct, patches at use-site.
- `_make_puller` and `_make_calculator` both patch `_load_reference`, `_load_years`, `_load_geographies` and the API clients — faithful.
- `AggregateIndicator(geography="county")` directly instantiates with no DB; constructor at [src/core/aggregator.py:33-52](src/core/aggregator.py#L33-L52) accepts this. Faithful.

---

## Cross-Site Consistency

| Aspect | data_puller | indicators | aggregator |
|---|---|---|---|
| Indicator-map guard | yes | yes | n/a (no map) |
| Geo-id-map guard | yes | yes | yes |
| Error message names target table | `source_data` | `indicators` | `aggregate_indicators` |
| Error message includes remediation cmd | yes | yes | yes |
| Guard placement after build-and-warn | yes | yes | n/a |
| Guard placement after empty-result early-return | n/a | n/a | yes (line 705 before line 725) |

Doctrine is consistently applied. No site got it wrong.

---

## Cognitive Bias Check

- **Confirmation bias (own-proposal implementation)**: The data-engineer is implementing their own proposal. Looked for selective implementation: NONE found — the proposal called for two guards per save site, and that's what's there. Looked for scope creep: NONE — no new logging, no extra checks, no alterations to repository code.
- **Anchoring bias**: Threshold of 60% is anchored on the typical-county-pull figure (51%) cited in the proposal. The audit-rec to add a boundary test (60.0% → INFO) is the only way to make this not be a magic-number-with-no-guard-rail.
- **Prior-audit follow-through**: The aggregator gap (Finding 1 of [docs/reviews/20260505_teammate_setup_robustness_audit.md](docs/reviews/20260505_teammate_setup_robustness_audit.md)) is fixed at Site 3. Drop-log demotion-to-DEBUG (Synthesis #3 of prior audit) is rejected as expected — INFO floor preserved.
- **Unaddressed prior-audit items**: The CWD-trap concern (prior Synthesis #2: default `sqlite:///./cria.db` silently creates a fresh DB in CWD) is NOT addressed by these changes. Out of scope for fail-fast at the persist layer — that's a preflight/doctor concern. Worth noting but not a blocker for THIS PR.

---

## Synthesis

The implementation faithfully executes the proposed defense-in-depth doctrine:
TOTAL miss raises, partial miss warns. All three sites are consistent in
expression, message structure, and placement. The drop-log rewrite preserves
the INFO floor and adds a sensible threshold-based escalation.

### Material concerns (must-think-about, may-not-block)
- **MEDIUM**: Threshold boundary (60.0% exactly) is not unit-tested. Off-by-one in the comparison operator would not be caught.
- **LOW** × 3: `self.reference is None` would `TypeError` the guard expression (latent, currently unreachable).
- **LOW**: Partial-miss test passes vacuously on the persistence side — proves no-raise but doesn't prove records-are-still-written.
- **LOW**: "Outer-merge artifact" phrasing assumes domain familiarity.

### Verdict
**PASS WITH CONCERNS**.

The defense-in-depth fix is correct, tested, and consistent. The drop-log rewrite is correct and tested for typical operating regimes. Recommended (non-blocking) follow-ups:
1. Add boundary parametrize cases at `pct_dropped == 60.0` and `pct_dropped == 60.x`.
2. Strengthen `test_partial_indicator_miss_does_not_raise` to assert records were persisted for the resolved indicator (not just that the warn fired).
3. Optional: defensive `len(self.reference) if self.reference is not None else 0` to harden against a future refactor.
