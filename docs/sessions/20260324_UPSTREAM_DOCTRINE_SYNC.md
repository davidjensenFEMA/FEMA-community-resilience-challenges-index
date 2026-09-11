---
date: 2026-03-24
tags: [#config, #docs, #feature]
status: complete
---

# Upstream Doctrine Sync from Utils Repo

**Date**: 2026-03-24
**Branch**: `main`

---

## Summary

Synced `.claude/` infrastructure from the upstream `utils` repo (github/utils) into the CRIA project. Received an upstream doctrine update notification (`.claude/upstream-update.md`) and expanded the sync beyond today's changes to cover all gaps between the two repos. Deployed a 3-wave agent team with quality audit.

## Changes Made

### Wave 1: Commands + Proposer Agent
- **session-start.md**: Added Step 5 (Check Upstream Doctrine Updates) — checks for `.claude/upstream-update.md` and surfaces it to the user. Renumbered steps 1-8.
- **task.md**: Added "Military origin" subtitle, TCS universal language ("every task within a CONOP/OPORD is specified at TCS detail level"), "Terminology: Phases vs Waves" section, updated "phase" → "wave" in tactical contexts. Preserved all CRIA-specific content.
- **proposer.md**: New agent — CRIA-adapted problem analyst. Sonnet model, `docs/`-only write access. Adds structured exploration/debate before implementation. CRIA-specific guidelines for calibration targets, indicator formulas, geography-level implications.

### Wave 2: Skills Framework
- Copied 5 Level 0 (universal, portable) skills from utils:
  - `SKILLS_FRAMEWORK.md` — Level 0/Level 1 concept, adapted inventory for CRIA
  - `configuration-management.md` — hierarchical config systems
  - `python-venv-management.md` — venv creation/troubleshooting
  - `shift-left-testing.md` — test pyramid, mocks, CI/CD
  - `session-end.md` — git workflow, knowledge graph session docs

### Wave 3: Team Templates + README
- **bug-fix.md**: New team — regression-first workflow (failing test → fix). Domain-adaptive implementer (data-engineer or cria-analyst) + statistical-tester.
- **code-review.md**: New team — read-only investigative audit. quality-auditor + statistical-tester.
- **indicator-development.md**: Updated — added proposer as first agent with explicit 6-step workflow (propose → review → design → test → implement → challenge).
- **agents/README.md**: Added design principle #6 (frameworks as tools), proposer in catalog/scope matrix, Level 0/Level 1 guidance section, updated model config note, wave terminology.

### Quality Audit Fixes
7 findings from quality-auditor, all resolved:
1. CLAUDE.md: "5 agents and 6 team templates", added proposer + bug-fix + code-review
2. task.md: Added proposer to agent roster
3. task.md: Updated CONOP team listings (indicator-development includes proposer)
4. Resolved full-pipeline-validation contradiction: "all 4 domain agents" (proposer is pre-implementation, not validation)
5. agents/README.md: Model note updated for proposer's pinned sonnet
6. teams/README.md: "multi-phase" → "multi-wave" in scaling rules
7. session-start.md: Renumbered steps sequentially (1-8)

### Deleted
- `.claude/upstream-update.md` — all action items addressed

## Agent Team Execution

| Agent | Tasks | Duration |
|-------|-------|----------|
| wave-1 | session-start, task.md, proposer agent | ~3 min |
| wave-2 | Skills framework (5 files) | ~1 min |
| wave-3a | Team templates (3 files) | ~2 min |
| wave-3b | Agents README | ~2 min |
| auditor (quality-auditor) | Full audit, 7 findings | ~3 min |
| lead | Audit fixes (7 edits) | ~1 min |

## Next Steps

- Delete `.claude/upstream-update.md` (action items complete)
- Consider adding Level 1 CRIA-specific skills (census-api-integration, indicator-calculation, binning-methodology)
- Test proposer agent on a real task to validate the workflow
