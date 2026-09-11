---
date: 2025-12-22
tags: [#config, #docs, #feature]
status: complete
---

# Pytest Timeout and PCC/PCI Pre-Commit Skills

**Date**: 2025-12-22
**Branch**: `main`

---

## Summary

Added pytest timeout protection after an 18-day runaway test incident on shared server TitanV. Created two new Claude Code skills (`/pcc` and `/pci`) inspired by military Pre-Combat Check/Inspection workflow to provide shift-left testing before pushes and merges.

## Origin

A coworker discovered a pytest process running for 18 days on TitanV:
```
PID    PPID USER         ELAPSED CMD
837027  837020 jhutchi+ 17-22:23:55 pytest --tb=short -q
```

This prompted adding timeout protection and formalizing a pre-commit workflow.

## Changes Made

### Pytest Timeout Configuration
- Added `pytest-timeout = "^2.4.0"` to dev dependencies
- Configured 300s (5 min) timeout in both `pyproject.toml` and `pytest.ini`
- Individual tests can override with `@pytest.mark.timeout(X)`

### /pcc - Pre-Code Check (New Skill)
Fast, deterministic checklist run before every push:
- No secrets in staged files
- Tests pass
- Lint clean (if configured)
- Lock file in sync
- No debug artifacts

**Analogy**: Ammo, water, weapon - same check every time, no thinking required.

### /pci - Pre-Code Inspection (New Skill)
Context-aware inspection based on what changed:
- Analyzes domains touched (API, DB, Config, Core, Tests, Infra, Deps)
- Applies relevant checks per domain
- Recommends specialized skills when warranted

**Analogy**: Mission-specific gear check - night mission? Check NVGs.

### Session-End Integration
Updated `.claude/commands/session-end.md`:
- Step 0: PCC (required) before any commit
- Step 5: PCI (optional) before merge to main
- Added quick reference table comparing PCC vs PCI

## Files Changed

| File | Change |
|------|--------|
| `.claude/commands/pcc.md` | NEW - Pre-Code Check skill |
| `.claude/commands/pci.md` | NEW - Pre-Code Inspection skill |
| `.claude/commands/session-end.md` | Integrated PCC/PCI workflow |
| `pyproject.toml` | Added pytest-timeout, timeout=300 |
| `pytest.ini` | Added timeout=300 |
| `poetry.lock` | Updated for pytest-timeout |

## Design Decisions

1. **PCC is fast and same every time** - Muscle memory, no judgment calls
2. **PCI adapts to the diff** - Applies relevant checks based on what changed
3. **Skills are self-contained** - Portable to other projects without modification
4. **Timeout in both files** - Redundant but ensures coverage regardless of which file pytest reads

## Next Steps

- Consider removing `pytest.ini` redundancy (pyproject.toml is sufficient)
- Add `pip-audit` for dependency vulnerability scanning in PCI
- Potentially add pre-push git hook to auto-run PCC
