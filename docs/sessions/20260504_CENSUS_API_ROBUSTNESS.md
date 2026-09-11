---
date: 2026-05-04
tags: [#bugfix, #census-acs, #data-pull, #config]
status: complete
---

# Census API Robustness — Surface Real Errors, Validate Key Format

**Date**: 2026-05-04
**Branch**: `main`
**Follows**: [20260430_USER_GUIDE_SYSTEM.md](20260430_USER_GUIDE_SYSTEM.md)
**Trigger**: Sponsor report — `Failed to pull Mobile Homes: Expecting value: line 2 column 1 (char 1)` on `DP04_0014E` from `run_full_pipeline.py`

---

## Summary

A sponsor running the pipeline fresh hit a cryptic `JSONDecodeError` on the very first ACS variable (Mobile Homes / `DP04_0014E`). They correctly diagnosed the symptom — "Census is returning text instead of JSON" — but our code was throwing the actual server message away. Two commits address the root cause and add preventive validation.

**Commit 1 — `d4ce817` `[fix][api]`**: Wrap `json.loads` at all three sites with a `CensusAPIError` that preserves the redacted URL, HTTP status, content-type, requested variables, and a 500-char body excerpt. Fail fast on empty/placeholder API keys. Warn on future-year ACS. Redact `key=` from all logged URLs in `base_client.py` (latent secret-in-logs problem).

**Commit 2 — `2a1f81a` `[feat][api]`**: Soft-validate key format at startup. `_normalize_api_key` strips `.env` paste artifacts (quotes, whitespace, line wrap) that pydantic-settings preserves literally. `validate_census_api_key_format` heuristic checks 40-char hex. `confirm_suspect_api_key` CLI helper prompts on TTY when the key looks wrong; in CI / Docker / non-interactive contexts it logs and continues. `--yes` flag on both CLI scripts skips the prompt.

Tests: 541 → 583 (+42). All passing.

## Root Cause

Census API returns **HTTP 200 with plain-text or HTML error bodies** for several error classes — unknown variables, unknown datasets, invalid keys. Examples:

- `error: error: unknown variable 'DP04_0014E'`
- HTML error page when `2024/acs/acs5` is requested before publication
- `Invalid key.` on bad/missing key

The chain that swallowed this:
1. [base_client.py:121](src/api/base_client.py#L121) — `response.raise_for_status()` only catches 4xx/5xx; the 200 sails through.
2. [census_client.py:186](src/api/census_client.py#L186) (pre-fix) — `data = json.loads(response.text)` dies on the text body with `Expecting value: line 2 column 1 (char 1)`.
3. [data_puller.py:227](src/core/data_puller.py#L227) — caught with `exc_info=True` but the real message in `response.text` was never logged.

Sponsor saw the JSONDecodeError, no clue what Census actually said.

## Changes Made

### Commit 1 (`d4ce817`)

- [src/api/census_client.py](src/api/census_client.py) — added `CensusAPIError`, `_redact_api_key`, `_parse_census_response`; wrapped 3 parse sites; fail-fast on empty/placeholder key in `__init__`; future-year warning.
- [src/api/base_client.py](src/api/base_client.py) — `_redact_url` helper; updated all 5 log sites in `get()` and `post()`.
- [tests/unit/test_census_client.py](tests/unit/test_census_client.py) — TestCensusAPIErrorHandling (6), TestCensusAPIClientInit (4), TestFetchACSDataErrorPropagation (1).
- [tests/unit/test_base_client.py](tests/unit/test_base_client.py) — TestRedactURL (4), incl. end-to-end "key never leaks to logs on HTTPError".

### Commit 2 (`2a1f81a`)

- [src/api/census_client.py](src/api/census_client.py) — `_normalize_api_key`, `validate_census_api_key_format`, `_mask_api_key`, `confirm_suspect_api_key`; wired normalization + format check into `__init__` (warning only, never blocks library use).
- [scripts/run_full_pipeline.py](scripts/run_full_pipeline.py) — preflight call + `--yes` flag.
- [scripts/sync_geographies.py](scripts/sync_geographies.py) — same.
- [tests/unit/test_census_client.py](tests/unit/test_census_client.py) — TestNormalizeAPIKey (7), TestValidateCensusAPIKeyFormat (7), TestMaskAPIKey (2), TestConfirmSuspectAPIKey (8), TestInitNormalizesAndWarns (3).

### Behavior changes the sponsor will see

| Scenario | Before | After |
|---|---|---|
| Bad variable | `JSONDecodeError: Expecting value...` | `CensusAPIError: ... unknown variable 'DP04_0014E'` (real Census text) |
| Empty `CENSUS_API_KEY` | Cryptic JSON error mid-pipeline | `ValueError` at client construction |
| `your_census_api_key_here` | Cryptic JSON error mid-pipeline | `ValueError` at client construction |
| `.env` has `KEY="abc"` (with quotes) | Quotes go into URL → Census rejects → cryptic error | Auto-stripped at construction with warning |
| `ACS_YEAR=2024` (pre-release) | Cryptic JSON error mid-pipeline | Warning at construction; clear `CensusAPIError` if it fails |
| Suspect-looking key, interactive | Silent until first request fails | `Continue anyway? [y/N]` prompt with masked key |
| Suspect-looking key, CI | Silent until first request fails | Warning logged, continues |
| Logs contain key | Yes (every URL log) | No (key=REDACTED) |

## Process Notes

### Diagnosis was fast because the failure surface was small

Three `json.loads(response.text)` sites in census_client.py, all identical pattern. One helper covers all three. Same for the URL log sites in base_client.py — five of them, one helper.

### Test pattern: mock at `BaseAPIClient.get` boundary

Existing tests already used `@patch("src.api.census_client.BaseAPIClient.get")` to inject a fake response. Reused the same pattern for the new error-path tests — keeps the new tests at the same level of abstraction as the old ones, no transport-layer mocking needed.

### Constructor semantics fix exposed by a test

When I wrote `test_empty_api_key_raises` and ran it, it failed: passing `api_key=""` was being silently overridden by `settings.census_api_key` because of `self.api_key = api_key or settings.census_api_key`. The `or` short-circuit treats `""` as "fall back." Fixed by switching to `settings.census_api_key if api_key is None else api_key` — explicit `""` now stays `""` and trips the validation. The test caught a real semantic bug, not just a contrived case.

### Soft-validation design

The user explicitly asked for "soft check; do you want to continue" rather than enforcement. Three design calls:

1. **Library use stays pure.** `__init__` warns but never blocks. Notebook construction, programmatic use, tests — no behavior change.
2. **Prompt lives in CLI, not the class.** `confirm_suspect_api_key` is a separate function called from `run_full_pipeline.py` / `sync_geographies.py`. Keeps the class testable and side-effect-free.
3. **TTY gating.** `sys.stdin.isatty()` check means CI/Docker/cron get the warning but don't hang on a prompt. `--yes` flag suppresses the prompt explicitly.

### Auto-strip vs reject for `.env` paste artifacts

User's intent is clear when `CENSUS_API_KEY="abc..."` shows up — they want `abc...`. Auto-stripping with a warning is friendlier than refusing and demanding they edit `.env` first. Same for line-wrap whitespace.

## Next Steps

- **Push** `d4ce817` and `2a1f81a` to `origin/main` (deferred for user approval — pushing is shared-state action)
- **Tell sponsor** the fix is on `main` and outline the diagnostic flow (most likely `ACS_YEAR=2024`, missing key, or `.env` quoting issue)
- **Consider** extending the same pattern to `external_clients.py` (CBP, EAVS, ARDA, POP) — out of scope this session but the failure mode is generic
- **Carry over** from prior sessions:
  - Distribute regenerated 2024 output (county/tract/tribal) to FEMA RAPT team
  - Draft RAPT write-up of code changes since Jan 30
  - [CLAUDE.md:28](CLAUDE.md#L28) still references `src/core/calculator.py` — should be `src/core/indicators.py`
