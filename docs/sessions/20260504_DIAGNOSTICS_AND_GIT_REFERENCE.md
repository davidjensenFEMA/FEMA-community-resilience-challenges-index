---
date: 2026-05-04
tags: [#census-acs, #data-pull, #docs, #config]
status: complete
---

# Operational Reference: Census API Diagnostics + Git Orientation

**Date**: 2026-05-04
**Branch**: `main`
**Companion to**: [20260504_CENSUS_API_ROBUSTNESS.md](20260504_CENSUS_API_ROBUSTNESS.md) (the code/feature work)

---

## Summary

Knowledge captured during the Census API robustness work — kept separate from the implementation session doc so it's findable on its own when the next person hits a similar problem. Two parts: how to diagnose Census API failures, and how to orient yourself in a git repo when you're not sure what you're looking at.

---

## Part 1: Diagnosing Census API Issues

### What the error messages actually mean

After commit `d4ce817`, the pipeline surfaces `CensusAPIError` with the Census server's actual response body. Read the **HTML `<title>`** first — it's the most concise diagnostic Census gives you.

| Census body excerpt | What it means | Where to fix |
|---|---|---|
| `<title>Invalid Key</title>` | API key is rejected (not activated, wrong, or revoked) | `.env` `CENSUS_API_KEY` value, or activate the key |
| `error: error: unknown variable 'XXX'` | Variable doesn't exist in this dataset/year | `config/indicators.yaml` or `ACS_YEAR` is wrong |
| `<title>404 Not Found</title>` (or HTML page) | Dataset path doesn't exist | `ACS_YEAR` is too new; ACS 5-year ships in Dec of year+1 |
| `error: error: unknown/unsupported geography heading 'X'` | Geography predicate malformed | URL builder bug (rare); see `build_acs_url` |

### The variable name in the error is often a red herring

When the pipeline reports `Failed to pull Mobile Homes: ...`, "Mobile Homes" is just **the first indicator in the queue** (`order: 1` in `config/indicators.yaml`). If the failure is auth-related, *every* request would fail the same way — Mobile Homes is the canary, not the cause.

Test: if the error says `Invalid Key`, the next indicator (Owner Occupied / `DP04_0046E`) would fail identically. The fix is never "exclude Mobile Homes" — it's at the layer that affects the whole client.

### Diagnostic ladder for "Census is failing"

Run these in order; each rules out cheaper hypotheses first:

1. **Read the body excerpt.** Our `CensusAPIError` includes 500 chars of the Census response. Don't skip it. The title tag tells you 90% of what you need.
2. **Curl the URL manually**, redacted key replaced with the real one. Eliminates everything our code does:
   ```bash
   curl 'https://api.census.gov/data/2023/acs/acs5/profile?get=NAME,DP04_0001E&for=state:01&key=YOUR_KEY'
   ```
   - Returns JSON → our code has a bug
   - Returns the same HTML/text error → it's Census, key, or URL parameters; not us
3. **Check the key format.** Census keys are 40 lowercase-hex characters (`[0-9a-f]{40}`). If it's not that, it's not a real Census key. Our `validate_census_api_key_format` warns about this at startup.
4. **Check `.env` parsing.** pydantic-settings preserves quotes and whitespace literally. `CENSUS_API_KEY="abc"` becomes the string `"abc"` (with quotes). Our `_normalize_api_key` strips these; if you bypass it, you'll get an `Invalid Key` from Census.
5. **Check the year.** ACS 5-year for year N ships in December of year N+1. Setting `ACS_YEAR=2024` before Dec 2025 gives you a 404 page from a non-existent dataset path.
6. **Check the dataset prefix.** Subject tables (`S*`) live at `/acs5/subject/`, profiles (`DP*`) at `/acs5/profile/`, comparison (`CP*`) at `/acs5/cprofile/`, detailed (`B*`) at the root `/acs5/`. Asking for an `S` variable on the detailed-table endpoint returns "unknown variable."

### What does NOT work

- **Removing the key from `.env`.** Our fail-fast raises `ValueError` at client construction. Even if you bypassed it, our URL builder always appends `&key=` (empty) — Census reads that as a failed authentication, not as anonymous access.
- **Anonymous Census access for a full pipeline run.** Census historically allowed ~500 unauthenticated requests/day per IP. The tract pipeline alone is 1,144 requests (22 indicators × 52 states). Even if anonymous works, you'd hit rate limits halfway through. Don't design around this.

### Activating a Census API key

The most common cause of `Invalid Key` for new users is **the key was never activated.** Census signup at `api.census.gov/data/key_signup.html` returns a key on screen and **emails an activation link**. Until the link is clicked, the key is dormant — present, syntactically valid, rejected by every request. Look for "Your Census Bureau API Key Request" in the inbox / spam folder.

### Where this lives in our code

| What | File / Line |
|---|---|
| Error wrapping | [src/api/census_client.py:50-82](src/api/census_client.py#L50-L82) `_parse_census_response` |
| Custom exception | [src/api/census_client.py:29-42](src/api/census_client.py#L29-L42) `CensusAPIError` |
| Key normalization | [src/api/census_client.py](src/api/census_client.py) `_normalize_api_key` |
| Format heuristic | [src/api/census_client.py](src/api/census_client.py) `validate_census_api_key_format` |
| URL key redaction (logs) | [src/api/base_client.py](src/api/base_client.py) `_redact_url` |
| Pre-flight prompt | [src/api/census_client.py](src/api/census_client.py) `confirm_suspect_api_key` |

---

## Part 2: Orienting in Git — "Where am I, what's going on?"

### The "where am I" toolkit

| Command | Tells you |
|---|---|
| `git status` | Current branch, modified/staged/untracked files, ahead/behind upstream |
| `git branch --show-current` | Just the branch name |
| `git branch -v` | All local branches + their last commit |
| `git log --oneline -5` | Last 5 commits on current branch |
| `git log --oneline --decorate --graph --all -10` | **Full picture: branches, merges, tags, all refs.** Single best command for "what's happening here." |
| `git remote -v` | What remotes exist and where they point |

### Identifying a mystery hash

Short hashes like `d4ce817` are the abbreviated form of git's 40-char SHA-1 commit ID. Git auto-truncates to the shortest unambiguous prefix (usually 7 chars).

| Command | Tells you |
|---|---|
| `git cat-file -t <sha>` | Object type: `commit`, `tag`, `tree`, or `blob` |
| `git rev-parse <sha>` | Expands short hash to full 40-char SHA |
| `git show <sha>` | Full commit content (message + diff) |
| `git log --oneline -1 <sha>` | Just the commit's title line |
| `git name-rev <sha>` | Symbolic name like `main~3` |
| `git describe <sha>` | Description relative to nearest tag |

Tags look different from SHAs — tags have human names like `v1.0.0`, SHAs are always hex. List tags with `git tag -l`.

### Reading `git log --decorate` output

```
* 988957f (HEAD -> main, origin/main, origin/HEAD) [docs] Session notes: ...
* 2a1f81a [feat][api] Soft-validate CENSUS_API_KEY format with TTY-gated prompt
* d4ce817 [fix][api] Surface real Census error text on non-JSON 200 responses
```

The parenthetical is added by `--decorate` and tells you which refs point at each commit:

- `HEAD -> main`: the `->` means "currently checked out." HEAD is your working position; `main` is the branch you're on.
- `origin/main`: git's local cached idea of where `main` was on the remote at last fetch. **Not** the live remote — `git fetch` updates this.
- `origin/HEAD`: the remote's default branch (usually mirrors `origin/main`).

When `HEAD -> main` and `origin/main` are on the **same** commit: your local branch is up-to-date with the remote tracking ref. When they're on **different** commits: `git status` will tell you "ahead by N" or "behind by M."

### "Are my commits pushed?"

Two ways:

1. `git status` — says "Your branch is ahead of 'origin/main' by N commits" if there's anything unpushed
2. `git log origin/main..HEAD --oneline` — lists commits on HEAD that aren't on `origin/main`

Both rely on the local `origin/main` ref being current. Run `git fetch` first if you're not sure.

---

## Why this is captured here

The original session doc covers what we built and why. This doc covers **the operational skill** of using what we built — knowledge that's only obvious in retrospect, that the next person diagnosing a Census failure or trying to figure out git state shouldn't have to re-derive.

If this doc gets used more than once, promote it to `docs/guides/troubleshooting.md` or split into `guides/census_diagnostics.md` and `guides/git_orientation.md`.

## Next Steps

Nothing pending from this iteration — pure documentation capture. Open items remain those from the implementation session:

- Notify sponsor that fix is on `main` and walk through the `Invalid Key` diagnosis
- Distribute regenerated 2024 output (county/tract/tribal) to FEMA RAPT team
- Draft RAPT write-up of code changes since Jan 30
- Fix `CLAUDE.md:28` reference to `src/core/calculator.py` (should be `indicators.py`)
