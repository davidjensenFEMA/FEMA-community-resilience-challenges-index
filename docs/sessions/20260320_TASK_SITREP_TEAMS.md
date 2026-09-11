---
date: 2026-03-20
tags: [#config, #docs, #feature]
status: complete
---

# Add /task, /sitrep Commands and Team Templates

**Date**: 2026-03-20
**Branch**: `main`

---

## Summary

Added project management infrastructure adapted from the TC hurricane project: `/task` command for persistent task tracking with escalation ladder, `/sitrep` command for team-facing status reports, and `.claude/teams/` directory with 4 team templates. Updated all touch points (agents README, session-start, session-end, CLAUDE.md).

Also regenerated county, tract, and tribal 2024 output with the manual bins from the previous session.

## Changes Made

### New Commands
- **`/task`** — Manages `docs/tasks.md` with subcommands: add, list, done, block, unblock, assign, promote, brief, plan. Includes escalation ladder (Task → TCS → CONOP → OPORD) and backbrief format.
- **`/sitrep`** — Generates team-facing status reports from project.yaml, CHANGELOG, tasks.md, sessions, and git log. Supports scope filtering (e.g., `/sitrep binning`).

### Team Templates (`.claude/teams/`)
- **data-pipeline** — data-engineer + cria-analyst + quality-auditor
- **indicator-development** — cria-analyst + statistical-tester + quality-auditor
- **test-validation** — statistical-tester + cria-analyst + quality-auditor
- **full-pipeline-validation** — all 4 agents

### Updated Touch Points
- **agents/README.md** — Added escalation framework section, team template references, updated inter-agent communication
- **session-start.md** — Added Step 4 (check tasks.md), renumbered summary step
- **session-end.md** — Added tasks.md to project status updates
- **CLAUDE.md** — Added Slash Commands table, Agent Teams section, tasks.md in doc structure

### Pipeline Regeneration
- County 2024: 3,284 counties, manual bins verified (cria_p bell curve, pop change reversed)
- Tract 2024: 85,382 tracts, 7-bin manual configs verified
- Tribal 2024: 704 rows, binning-only mode

### Investigation: Missing Suffolk County Tracts
- 14 tracts in county 36103 missing from 2024 output — Census retired these tract numbers in 2010→2020 boundary transition
- All 14 present in 2021 output (2010 boundaries), absent from 2022+ (2020 boundaries)
- 899 tracts retired nationally (883 CT, 14 NY, 1 AK, 1 PR)
- Not a CRIA bug — Census data issue

## Next Steps

- Distribute regenerated output to team
- Push commits to origin/main
- Backfill docs/tasks.md with known issues as backlog items
