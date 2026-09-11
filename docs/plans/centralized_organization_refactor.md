# Plan: Centralized Project Organization Refactor

**Date**: 2025-12-10
**Status**: PLANNING
**Branch**: `pipeline-dev`

---

## Goal

Transform FEMA CRIA from locally-organized documentation to a centralized configuration pattern with:
1. Single source of truth (`config/project.yaml`)
2. Separate indicator reference data (`config/indicators.yaml`)
3. Tagged session docs for searchability
4. Clear separation: sessions vs design docs
5. Changelog for production-ready tracking
6. Updated Claude commands for this specific repo

---

## Current State

### Documentation Issues
- 22 files in `docs/sessions/` with mixed purposes:
  - True sessions: `20251203_BUG_FIXES_SESSION.md`, `20251205_JENKSCASPALL_BUG_FIX.md`
  - Design docs: `DATABASE_SCHEMA.md`, `DOCKER_GUIDE.md`, `REFACTOR_PLAN.md`, `PRODUCTION_DEPLOYMENT.md`
  - Guides: `QUICK_START_*.md`, `KEY_FILES_*.md`
  - Handoffs: `*_HANDOFF.md`
- `docs/sessions/README.md` contains MAUT project README (wrong project!)
- Empty `docs/design/` and `docs/plans/` folders
- No central project state tracking
- No tag network for searchability
- Commands reference video game project structure, not CRIA

### Current Config
- Runtime config in `src/config/settings.py` (Pydantic) - KEEP
- Path config in `src/config/paths.py` - KEEP
- No project metadata config

---

## Target State

```
fema_cria/
├── config/                        # NEW: Project configuration
│   ├── project.yaml               # Central project state & metadata
│   └── indicators.yaml            # 22 indicator definitions (reference data)
│
├── docs/
│   ├── design/                    # Architecture & reference docs
│   │   ├── database_schema.md     # Moved from sessions/
│   │   ├── docker_guide.md        # Moved from sessions/
│   │   ├── refactor_plan.md       # Moved from sessions/
│   │   ├── production_deployment.md
│   │   ├── testing_guide.md
│   │   └── workplan.md            # Project goals & roadmap
│   │
│   ├── plans/                     # Implementation plans (for future work)
│   │   └── centralized_organization_refactor.md  # This file
│   │
│   └── sessions/                  # Chronological session logs (with tags)
│       ├── 20251030_SESSION_SUMMARY.md
│       ├── 20251107_PHASE6_COMPLETION.md
│       ├── 20251108_PHASE7_COMPLETION.md
│       ├── 20251203_BUG_FIXES_SESSION.md
│       ├── 20251203_DATABASE_PERFORMANCE_FIX.md
│       ├── 20251203_TEST_VERIFICATION_SESSION.md
│       └── 20251205_JENKSCASPALL_BUG_FIX.md
│
├── tasks/
│   └── changelog.md               # Track completed work (prod-ready project)
│
├── .claude/commands/              # Updated for CRIA-specific paths
│   ├── session-start.md
│   ├── session-end.md
│   └── implement-feature.md
│
├── src/config/                    # UNCHANGED: Runtime configuration
│   ├── settings.py
│   └── paths.py
│
└── CLAUDE.md                      # Updated to reference config/project.yaml
```

---

## Tag Taxonomy

### Core Tags (by layer)
| Category | Tags | Use for |
|----------|------|---------|
| **Pipeline** | `#data-pull` `#indicators` `#aggregation` `#binning` | Core workflow stages |
| **Data Sources** | `#census-acs` `#cbp` `#eavs` `#arda` `#pop` | API/data source work |
| **Infrastructure** | `#database` `#docker` `#config` `#migrations` | Systems work |
| **Geography** | `#county` `#tract` `#state` `#tribal` | Geography-level work |

### Activity Tags
| Tag | Use for |
|-----|---------|
| `#bugfix` | Bug fixes |
| `#feature` | New functionality |
| `#refactor` | Code restructuring |
| `#performance` | Optimization work |
| `#calibration` | Validation against baseline |
| `#deployment` | Production/Docker setup |
| `#docs` | Documentation |

### Phase Tags (historical)
| Tag | Use for |
|-----|---------|
| `#phase-1` through `#phase-8` | Original refactoring phases |

---

## Implementation Steps

### Phase 1: Create Central Config Structure
- [ ] Create `config/` directory at project root
- [ ] Create `config/project.yaml` with:
  - Project name, version, status
  - Current focus area
  - Module registry (api, core, db, config, utils)
  - Directory map
  - State (last session, active work, known issues)
  - Lessons learned
- [ ] Create `config/indicators.yaml` with 22 indicator definitions from reference Excel

### Phase 2: Reorganize Documentation
- [ ] Move design docs from `sessions/` to `design/`:
  - `20251030_DATABASE_SCHEMA.md` → `design/database_schema.md`
  - `20251030_DOCKER_GUIDE.md` → `design/docker_guide.md`
  - `20251030_REFACTOR_PLAN.md` → `design/refactor_plan.md`
  - `20251108_PRODUCTION_DEPLOYMENT.md` → `design/production_deployment.md`
  - `20251023_TESTING_GUIDE.md` → `design/testing_guide.md`
- [ ] Create `design/workplan.md` for project goals/roadmap
- [ ] Delete or fix `docs/sessions/README.md` (currently contains wrong project)
- [ ] Remove redundant guides: `QUICK_START_*.md`, `KEY_FILES_*.md`, `*_HANDOFF.md`, `*_NEXT_SESSION*.md`

### Phase 3: Add YAML Frontmatter to Sessions
- [ ] Add frontmatter to each remaining session doc:
  ```yaml
  ---
  date: YYYY-MM-DD
  tags: [#tag1, #tag2, #tag3]
  status: complete
  ---
  ```
- [ ] Session files to update:
  - `20251030_SESSION_SUMMARY.md`
  - `20251030_SESSION_PHASE1_COMPLETE.md`
  - `20251030_FINAL_SESSION_SUMMARY.md`
  - `20251107_PHASE6_COMPLETION.md`
  - `20251108_PHASE7_COMPLETION.md`
  - `20251203_BUG_FIXES_SESSION.md`
  - `20251203_DATABASE_PERFORMANCE_FIX.md`
  - `20251203_TEST_VERIFICATION_SESSION.md`
  - `20251205_JENKSCASPALL_BUG_FIX.md`

### Phase 4: Create Changelog
- [ ] Create `tasks/` directory
- [ ] Create `tasks/changelog.md` with historical entries from session docs
- [ ] Format: date, category tag, description

### Phase 5: Update Claude Commands
- [ ] Update `.claude/commands/session-start.md`:
  - Reference `config/project.yaml` instead of generic paths
  - Reference `tasks/changelog.md`
  - Reference `docs/plans/` for active plans
  - Update health check commands for this project (poetry run pytest)
- [ ] Update `.claude/commands/session-end.md`:
  - Update project.yaml state section
  - Add entry to changelog.md
  - Create session doc with proper tags
  - Use CRIA-specific commit tags
- [ ] Update `.claude/commands/implement-feature.md`:
  - Reference CRIA module locations
  - Update test locations for this project

### Phase 6: Update CLAUDE.md
- [ ] Add reference to `config/project.yaml` as central state
- [ ] Update documentation links (design/ paths instead of sessions/)
- [ ] Simplify "Important Documentation" section to point to design/

### Phase 7: Validation
- [ ] Run `grep -r "#database" docs/sessions/` to verify tag searchability
- [ ] Verify all links in CLAUDE.md work
- [ ] Run tests to ensure nothing broke
- [ ] Create session doc for this work with proper tags

---

## Files to Create

1. `config/project.yaml` - Central project state
2. `config/indicators.yaml` - 22 indicator definitions
3. `docs/design/workplan.md` - Project goals/roadmap
4. `tasks/changelog.md` - Historical record

## Files to Move

| From | To |
|------|-----|
| `docs/sessions/20251030_DATABASE_SCHEMA.md` | `docs/design/database_schema.md` |
| `docs/sessions/20251030_DOCKER_GUIDE.md` | `docs/design/docker_guide.md` |
| `docs/sessions/20251030_REFACTOR_PLAN.md` | `docs/design/refactor_plan.md` |
| `docs/sessions/20251108_PRODUCTION_DEPLOYMENT.md` | `docs/design/production_deployment.md` |
| `docs/sessions/20251023_TESTING_GUIDE.md` | `docs/design/testing_guide.md` |

## Files to Delete

- `docs/sessions/README.md` (wrong project content)
- `docs/sessions/QUICK_START_PHASE7.md` (redundant)
- `docs/sessions/QUICK_START_NEXT_SESSION.md` (redundant)
- `docs/sessions/KEY_FILES_PHASE7.md` (redundant)
- `docs/sessions/20251030_NEXT_SESSION_INSTRUCTIONS.md` (stale)
- `docs/sessions/20251030_PHASE5_HANDOFF.md` (stale)
- `docs/sessions/20251030_PHASE6_HANDOFF.md` (stale)
- `docs/sessions/VALIDATION_GUIDE_2022_COMPARISON.md` (can move to design if needed)

## Files to Update

- `.claude/commands/session-start.md`
- `.claude/commands/session-end.md`
- `.claude/commands/implement-feature.md`
- `CLAUDE.md`
- All remaining session docs (add frontmatter)

---

## Success Criteria

- [ ] `config/project.yaml` exists and contains current project state
- [ ] `config/indicators.yaml` exists with all 22 indicators
- [ ] `docs/design/` contains 5+ architecture docs
- [ ] `docs/sessions/` contains only true session logs with YAML frontmatter
- [ ] `tasks/changelog.md` exists with historical entries
- [ ] Commands work with CRIA paths
- [ ] `grep -r "#bugfix" docs/sessions/` returns relevant results
- [ ] All tests pass
- [ ] CLAUDE.md links all work

---

## Estimated Effort

| Phase | Effort |
|-------|--------|
| Phase 1: Config structure | 30 min |
| Phase 2: Reorganize docs | 20 min |
| Phase 3: Add frontmatter | 20 min |
| Phase 4: Create changelog | 15 min |
| Phase 5: Update commands | 30 min |
| Phase 6: Update CLAUDE.md | 15 min |
| Phase 7: Validation | 10 min |
| **Total** | **~2.5 hours** |

---

**Plan Created**: 2025-12-10
**Author**: Claude Code
