# FEMA CRIA Scripts

This directory contains executable scripts for running CRIA workflows.

## Available Scripts

### Workflow Scripts (Coming in Phase 2-3)

- `run_county_workflow.py` - Run complete workflow for county-level data
- `run_tract_workflow.py` - Run complete workflow for tract-level data
- `run_tribal_workflow.py` - Run complete workflow for tribal-level data

### Database Scripts (Coming in Phase 4)

- `import_reference_data.py` - Import Excel reference data to PostgreSQL
- `export_to_excel.py` - Export database results to Excel (legacy compatibility)
- `reset_database.py` - Reset database to clean state

### Utility Scripts

- `run_tests.sh` - Run test suite with various options

## Usage

### From Command Line (with Poetry)

```bash
# Run county workflow
poetry run python scripts/run_county_workflow.py

# Run tests
./scripts/run_tests.sh unit
```

### From Docker

```bash
# Run county workflow
docker-compose exec app poetry run python scripts/run_county_workflow.py

# Run tests
docker-compose exec app ./scripts/run_tests.sh all
```

### Using Poetry Scripts (Shortcuts)

```bash
# Defined in pyproject.toml
poetry run cria-county
poetry run cria-tract
poetry run cria-tribal
```

## Development

All scripts should:
- Use `src.config.settings` and `src.config.paths` for configuration
- Set up logging at the start
- Handle errors gracefully
- Return appropriate exit codes
- Include docstrings explaining usage
