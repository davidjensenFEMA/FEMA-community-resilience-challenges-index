# Project Tasks

Tactical work tracker. Strategic focus lives in `config/project.yaml`.

Use `/task` command to manage: `/task add`, `/task done`, `/task block`, `/task promote`.

---

## Active

- [ ] [P1] Pipeline `--year` arg only labels output; doesn't drive data pull. Sponsor produced `cria_results_county_2024.xlsx` containing ACS 2023 data (env `ACS_YEAR=2023`, ran with `--year 2024`). Filename + DB year column won; actual pull was 2023. Fix: preflight that fails when `args.year != settings.acs_year`, with `--allow-year-mismatch` override flag. See [scripts/run_full_pipeline.py:660](scripts/run_full_pipeline.py#L660) (filename) and [src/core/data_puller.py:55](src/core/data_puller.py#L55) (CensusAPIClient instantiated with no year arg). Discovered 2026-05-14 via sponsor check-file comparison. — owner: unassigned

## Blocked

## Completed
