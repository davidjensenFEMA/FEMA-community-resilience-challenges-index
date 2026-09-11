# Deprecated Code

This directory contains code that has been replaced by the new modular architecture in `src/`.

**Date Deprecated**: October 30, 2025
**Phase**: Post-Phase 6 Cleanup

---

## Why This Code Was Deprecated

The FEMA CRIA project underwent a major refactoring (Phases 3-6) to modernize the codebase:

- **Phase 3**: Created modular `src/` structure with proper separation of concerns
- **Phase 4**: Implemented database layer with SQLAlchemy and repositories
- **Phase 5**: Added comprehensive testing (134 tests)
- **Phase 6**: Integrated database with core pipeline classes

The old functional scripts have been replaced with:
- Object-oriented, testable classes
- Database integration
- Comprehensive test coverage
- Better error handling and logging

---

## Directory Structure

```
deprecated/
├── old_scripts/          # Old root-level Python scripts
│   ├── cria_*.py        # Original CRIA pipeline scripts
│   ├── island_*.py      # Island territories code
│   └── *.py             # Miscellaneous utility scripts
│
└── old_utils/           # Old utils/ directory
    ├── utils_*.py       # Various utility functions
    ├── iaa_*.py         # Island area aggregation
    ├── territory_*.py   # Territory retrieval
    └── *.xlsx           # Reference Excel files (kept for reference)
```

---

## Migration Guide: Old → New

### **Data Pulling**

#### Old Way (deprecated):
```python
# cria_pull_data.py
# Functional script with global variables
# Hard to test, tightly coupled

import cria_pull_data
data = cria_pull_data.pull_all_data()
```

#### New Way (current):
```python
# src/core/data_puller.py
# Object-oriented, testable, database-aware

from src.core.data_puller import DataPuller
from src.db.session import get_db

with get_db() as db:
    puller = DataPuller(geography="county", db=db)
    data = puller.pull_all_data()
    puller.save_to_database(data, year=2021)
```

---

### **Indicator Calculation**

#### Old Way (deprecated):
```python
# cria_create_indicators.py
# Functional script, no separation of concerns

import cria_create_indicators
indicators = cria_create_indicators.calculate(data)
```

#### New Way (current):
```python
# src/core/indicators.py
# Testable class with database integration

from src.core.indicators import IndicatorCalculator

calc = IndicatorCalculator(geography="county", db=db)
indicators = calc.calculate_all_indicators(source_data)
calc.save_to_database(indicators, year=2021)
```

---

### **Aggregation**

#### Old Way (deprecated):
```python
# cria_create_aggregate_indicator.py
# Monolithic script, Excel-based

import cria_create_aggregate_indicator
results = cria_create_aggregate_indicator.aggregate(indicators)
```

#### New Way (current):
```python
# src/core/aggregator.py
# Modular class with binning engine

from src.core.aggregator import AggregateIndicator

agg = AggregateIndicator(geography="county", bins=5, db=db)
results = agg.create_aggregate(indicators, reference)
agg.save_to_database(results, year=2021)
```

---

### **Utility Functions**

#### Old Way (deprecated):
```python
# utils/utils_api.py, utils/utils_excel_*.py
# Scattered utility functions

from utils import utils_api
response = utils_api.make_request(url)
```

#### New Way (current):
```python
# src/api/, src/utils/, src/config/
# Organized by responsibility

from src.api.census_client import CensusAPIClient
from src.utils.logger import logger
from src.config.settings import settings

client = CensusAPIClient()
data = client.fetch_acs_data(columns, geography="county")
```

---

## Deprecated Files Reference

### **Old Scripts (`old_scripts/`)**

| File | Replaced By | Description |
|------|-------------|-------------|
| `cria_pull_data.py` | `src/core/data_puller.py` | Data collection from APIs |
| `cria_create_indicators.py` | `src/core/indicators.py` | Indicator calculation |
| `cria_create_indicators_tribal.py` | `src/core/indicators.py` | Tribal-specific indicators (now handled by geography parameter) |
| `cria_create_aggregate_indicator.py` | `src/core/aggregator.py` | Aggregate score creation |
| `cria_create_aggregate_tract.py` | `src/core/aggregator.py` | Tract-level aggregation (now handled by geography parameter) |
| `cria_functions.py` | `src/core/transformations.py` | Data transformation functions |
| `cria_plots.py` | _(Future)_ | Visualization (to be implemented) |
| `cria_analysis.py` | _(Future)_ | Analysis tools (to be implemented) |
| `cria_compare_*.py` | _(Future)_ | Comparison tools (to be implemented) |
| `cria_references.py` | `src/config/paths.py` | Reference data management |
| `island_census_client.py` | `src/api/census_client.py` | Census API client |
| `bin_local_data.py` | `src/core/binning.py` | Binning/classification |

---

### **Old Utils (`old_utils/`)**

| File | Replaced By | Description |
|------|-------------|-------------|
| `utils_api.py` | `src/api/base_client.py` | Base API client functionality |
| `utils_excel_*.py` | `pandas` + `openpyxl` | Excel operations (use pandas directly) |
| `utils_logger.py` | `src/utils/logger.py` | Logging configuration |
| `utils_decoder.py` | `src/utils/` | Data decoding utilities |
| `iaa_aggregate.py` | `src/core/aggregator.py` | Aggregation logic |
| `island_areas_census_downloader.py` | `src/api/census_client.py` | Census data download |
| `territory_retriever*.py` | `src/api/census_client.py` | Territory data retrieval |
| `states_and_regions.xlsx` | `src/config/` or database | Reference data (can be imported to DB) |

---

## Can I Delete This Code?

### **Keep for Now:**
- Reference Excel files (`.xlsx`) - May contain useful metadata
- `cria_plots.py`, `cria_analysis.py` - Will be modernized in future phases
- Anything with unique logic not yet migrated

### **Safe to Delete (Eventually):**
- Scripts fully replaced by `src/` modules
- Duplicate utility functions
- Old test files (if any)

### **Before Deleting:**
1. Verify new code covers all functionality
2. Check for any unique edge cases
3. Extract any useful constants or configurations
4. Document any tribal/territory-specific logic

---

## Testing the New Code

The new codebase has comprehensive test coverage:

```bash
# Run all tests
poetry run pytest tests/ -v

# Run specific test categories
poetry run pytest tests/unit/ -v          # Unit tests
poetry run pytest tests/integration/ -v   # Integration tests

# Test coverage
poetry run pytest tests/ --cov=src --cov-report=html
```

**Current Status:**
- ✅ 134 tests passing
- ✅ 100% backward compatibility maintained
- ✅ Database integration working
- ✅ All core functionality covered

---

## Need Help?

If you need to reference old code:

1. **Check the new location first**: Look in `src/` for equivalent functionality
2. **Read the docs**: See `docs/PHASE6_HANDOFF.md` for migration guide
3. **Run tests**: Tests demonstrate how to use new code
4. **Ask questions**: Open an issue if functionality is missing

---

## Future Cleanup

**Phase 7+ Tasks:**
- Migrate visualization code (`cria_plots.py`)
- Implement comparison tools (`cria_compare_*.py`)
- Extract any remaining useful utilities
- Final deletion of deprecated code (after verification)

---

**Last Updated**: October 30, 2025
**Deprecated In**: Phase 6 completion
**Maintained By**: Project team
