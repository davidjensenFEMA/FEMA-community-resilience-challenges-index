# Testing Guide - FEMA CRIA

## Quick Reference

```bash
# Install testing tools (handled by Poetry)
poetry install --with dev

# Run all tests
pytest

# Run unit tests (fast)
./scripts/run_tests.sh unit

# Run with coverage
./scripts/run_tests.sh coverage

# Watch mode (auto-run on changes)
./scripts/run_tests.sh watch
```

## Testing Philosophy

### Separate from src/ (Yes!)

Tests are kept in a **separate `tests/` directory** at the project root. This is Python best practice because:

✅ **Clear separation** - Production code vs test code
✅ **Clean imports** - Tests import from `src/` as users would
✅ **No pollution** - Test files don't clutter source directories
✅ **Easy exclusion** - Can exclude `tests/` from production builds
✅ **Standard structure** - Follows pytest conventions

### Why NOT in src/?

Some projects put tests in `src/tests/`, but we chose **top-level `tests/`** because:

1. **Streamline goal** - Keep `src/` focused on production code only
2. **Discovery** - Easier for developers to find tests
3. **Tools** - Most Python tools expect `tests/` at project root
4. **Distribution** - Tests don't get packaged with production code

## Directory Structure

```
fema_cria/
├── src/                      # Production code ONLY
│   ├── api/
│   ├── core/
│   ├── db/
│   └── ...
├── tests/                    # All tests here
│   ├── unit/                 # Fast, isolated tests
│   ├── integration/          # Multi-component tests
│   ├── fixtures/             # Test data
│   └── conftest.py           # Shared fixtures
├── pyproject.toml            # Test configuration (markers, timeout)
└── scripts/run_tests.sh      # Test runner
```

## Test Types

### Unit Tests (`tests/unit/`)

**Purpose**: Test individual functions/classes in isolation

**Characteristics**:
- ⚡ Fast (< 1 second)
- 🔒 Isolated (no external dependencies)
- 🎯 Focused (one concept per test)

**Example**:
```python
# tests/unit/test_entity_parser.py
def test_parse_doe_order():
    """Parse DOE Order format correctly"""
    result = parse_entity("DOE Order 413.3B")
    assert result['type'] == 'DOE_ORDER'
    assert result['number'] == '413.3B'
```

### Integration Tests (`tests/integration/`)

**Purpose**: Test multiple components working together

**Characteristics**:
- 🐢 Slower (multiple seconds)
- 🔗 Multi-component
- 🎛️ May require services

**Example**:
```python
# tests/integration/test_pipeline.py
@pytest.mark.integration
@pytest.mark.requires_docker
def test_full_pipeline_processing():
    """Test complete document processing pipeline"""
    # Tests: text extraction → NER → relationship extraction → Neo4j
    pass
```

## Writing Tests

### AAA Pattern

All tests should follow **Arrange-Act-Assert**:

```python
def test_relationship_key_standardization():
    # ARRANGE - Set up test data
    data = {'document': 'test.pdf', 'relationships': [...]}

    # ACT - Execute the function
    result = process_document(data)

    # ASSERT - Verify results
    assert 'relationships' in result
    assert len(result['relationships']) > 0
```

### Using Fixtures

Fixtures provide reusable test data:

```python
def test_with_fixture(sample_entity):
    """sample_entity comes from conftest.py"""
    assert sample_entity['label'] == 'DOE_ORDER'
```

**Available fixtures** (see `tests/conftest.py`):
- `sample_entity` - Example entity
- `sample_relationship` - Example relationship
- `sample_entities_json` - Complete JSON structure
- `temp_json_file` - Temporary file for testing
- `neo4j_available` - Check if Neo4j is running

## Running Tests

### Via Pytest (Direct)

```bash
# All tests
pytest

# Specific directory
pytest tests/unit/

# Specific file
pytest tests/unit/test_relationship_key_fix.py

# Specific function
pytest tests/unit/test_relationship_key_fix.py::test_key_standardization

# With markers
pytest -m unit          # Only unit tests
pytest -m integration   # Only integration tests
pytest -m "not slow"    # Skip slow tests
```

### Via Test Runner (Convenient)

```bash
./scripts/run_tests.sh all          # All tests
./scripts/run_tests.sh unit         # Unit tests only
./scripts/run_tests.sh integration  # Integration tests only
./scripts/run_tests.sh coverage     # With coverage report
./scripts/run_tests.sh watch        # Auto-run on changes
./scripts/run_tests.sh failed       # Re-run failed tests
./scripts/run_tests.sh quick        # Quick sanity check
```

## Test Markers

Mark tests for categorization:

```python
@pytest.mark.unit              # Fast unit test
@pytest.mark.integration       # Integration test
@pytest.mark.slow              # Takes > 10 seconds
@pytest.mark.requires_neo4j    # Needs Neo4j running
@pytest.mark.requires_docker   # Needs Docker
```

**Auto-markers**: Tests in `unit/` and `integration/` are automatically marked by directory.

## Coverage Reports

```bash
# Terminal report
pytest --cov=src

# HTML report (detailed)
pytest --cov=src --cov-report=html
open htmlcov/index.html

# Or use the script
./scripts/run_tests.sh coverage
```

**Coverage goals**:
- Critical modules: > 80%
- Utilities: > 70%
- Overall: > 60%

## Best Practices

### ✅ DO

- Write tests for all new features
- Keep unit tests fast (< 1 second)
- Use descriptive test names
- One assertion concept per test
- Use fixtures for common data
- Test edge cases and errors
- Mark tests appropriately

### ❌ DON'T

- Test implementation details
- Write order-dependent tests
- Use real services in unit tests
- Commit test outputs
- Skip tests for "simple" code
- Put tests in `src/`

## Adding New Tests

### 1. Create Test File

```bash
# For unit test
touch tests/unit/test_my_feature.py

# For integration test
touch tests/integration/test_my_workflow.py
```

### 2. Write Test

```python
# tests/unit/test_my_feature.py
import pytest

def test_my_function():
    """Test description"""
    result = my_function(input_data)
    assert result == expected
```

### 3. Run Test

```bash
pytest tests/unit/test_my_feature.py -v
```

### 4. Verify

```bash
# Should see:
# tests/unit/test_my_feature.py::test_my_function PASSED
```

## Integration with CI/CD

For continuous integration:

```bash
# Fast CI (unit tests only)
pytest -m unit --tb=line

# Full CI (all tests, fail fast)
pytest --tb=short --maxfail=5

# With coverage requirements
pytest --cov=src --cov-fail-under=60
```

## Debugging Tests

```bash
# Stop at first failure
pytest -x

# Show local variables
pytest -l

# Enter debugger on failure
pytest --pdb

# Verbose output
pytest -vv

# Show print statements
pytest -s
```

## Common Issues

### "ModuleNotFoundError"
**Solution**: Check `sys.path` in `tests/conftest.py`

### "Fixture not found"
**Solution**: Check spelling, ensure in `conftest.py`

### Tests pass alone, fail together
**Solution**: Check for shared state, use fixtures for isolation

## Example: Complete Test File

```python
# tests/unit/test_entity_extraction.py
import pytest
from src.ner.enhanced_ner_system import extract_entities

class TestEntityExtraction:
    """Test suite for entity extraction"""

    def test_extract_doe_order(self, sample_entity):
        """Extract DOE Order entities correctly"""
        text = "As per DOE Order 413.3B requirements..."
        entities = extract_entities(text)

        assert len(entities) > 0
        assert any(e['label'] == 'DOE_ORDER' for e in entities)

    @pytest.mark.parametrize("text,expected_type", [
        ("DOE Order 413.3B", "DOE_ORDER"),
        ("10 CFR 851", "CFR"),
        ("Safety Plan", "POLICY"),
    ])
    def test_various_entity_types(self, text, expected_type):
        """Test multiple entity types"""
        entities = extract_entities(text)
        assert entities[0]['label'] == expected_type
```

## Resources

- Full guide: [tests/README.md](../tests/README.md)
- Pytest docs: https://docs.pytest.org/
- Conftest examples: `tests/conftest.py`
- Test runner: `scripts/run_tests.sh`

---

**Summary**: Tests live in `tests/` directory (separate from `src/`), following Python best practices. This keeps production code clean while providing comprehensive testing infrastructure.

*Last updated: October 23, 2025*
