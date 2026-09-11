"""
Import reference data from Excel to database.

Reads cria_data_reference.xlsx and populates:
- reference_indicators table
- data_years table

This is a ONE-TIME migration from Excel to database.

Usage:
    DATABASE_URL="sqlite:///./cria.db" poetry run python scripts/import_reference_data.py
"""

from pathlib import Path
import pandas as pd
from src.config.paths import paths
from src.db.session import get_db, init_db
from src.db.models import ReferenceIndicator, DataYear
from src.db.repositories import ReferenceIndicatorRepository
from src.utils.logger import logger


def import_reference_indicators():
    """Import indicators from Status sheet."""
    logger.info(f"Reading reference file: {paths.reference_file}")

    if not paths.reference_file.exists():
        logger.error(f"Reference file not found: {paths.reference_file}")
        raise FileNotFoundError(f"Reference file not found: {paths.reference_file}")

    # Read Status sheet
    xl = pd.ExcelFile(paths.reference_file)
    ref_df = xl.parse("Status")

    logger.info(f"Loaded {len(ref_df)} rows from Status sheet")

    # Clean and filter - only include rows with Order_2023
    ref_df = ref_df.dropna(subset=["Order_2023"])
    logger.info(f"Filtered to {len(ref_df)} indicators with Order_2023")

    indicators = []
    for idx, row in ref_df.iterrows():
        # Build indicator dict
        indicator_data = {
            "indicator_name": str(row["Indicator"]),
            "source": str(row["Source"]),
            "function": str(row["Function"]),
            "order_2023": int(row["Order_2023"]),
            "is_active": True,
        }

        # Add optional fields if they exist
        if "numerator" in row and pd.notna(row["numerator"]):
            indicator_data["numerator"] = str(row["numerator"])

        if "denominator" in row and pd.notna(row["denominator"]):
            indicator_data["denominator"] = str(row["denominator"])

        if "rate" in row and pd.notna(row["rate"]):
            indicator_data["rate"] = float(row["rate"])

        if "Category" in row and pd.notna(row["Category"]):
            indicator_data["category"] = str(row["Category"])

        if "Description" in row and pd.notna(row["Description"]):
            indicator_data["description"] = str(row["Description"])

        if "year_source" in row and pd.notna(row["year_source"]):
            indicator_data["year_source"] = str(row["year_source"])

        # Check for reverse polarity flag
        if "reverse_polarity" in row and pd.notna(row["reverse_polarity"]):
            indicator_data["reverse_polarity"] = bool(row["reverse_polarity"])

        indicators.append(indicator_data)

    # Insert into database
    with get_db() as db:
        repo = ReferenceIndicatorRepository(db)
        created = repo.bulk_create(indicators)
        logger.info(f"Imported {len(created)} reference indicators")

    return len(created)


def import_data_years():
    """Import data years from Years sheet."""
    logger.info(f"Reading Years sheet from: {paths.reference_file}")

    # Read Years sheet
    xl = pd.ExcelFile(paths.reference_file)
    years_df = xl.parse("Years")

    logger.info(f"Loaded {len(years_df)} rows from Years sheet")

    years = []
    for idx, row in years_df.iterrows():
        # Skip rows with missing data
        if pd.isna(row.get("label")) or pd.isna(row.get("year_ref")):
            continue

        year_data = {
            "source": str(row["label"]),
            "year": int(row["year_ref"]),
        }

        # Add description if available
        if "description" in row and pd.notna(row["description"]):
            year_data["description"] = str(row["description"])
        else:
            year_data["description"] = f"{row['label']} data year {int(row['year_ref'])}"

        years.append(year_data)

    # Insert into database
    with get_db() as db:
        for year_data in years:
            year = DataYear(**year_data)
            db.add(year)

        logger.info(f"Imported {len(years)} data years")

    return len(years)


def main():
    """Main import function."""
    logger.info("="*80)
    logger.info("CRIA Reference Data Import")
    logger.info("="*80)

    # Initialize database (create tables if they don't exist)
    logger.info("Initializing database...")
    init_db()

    try:
        # Import reference indicators
        logger.info("\n--- Importing Reference Indicators ---")
        num_indicators = import_reference_indicators()
        logger.info(f"✓ Successfully imported {num_indicators} indicators")

        # Import data years
        logger.info("\n--- Importing Data Years ---")
        num_years = import_data_years()
        logger.info(f"✓ Successfully imported {num_years} data years")

        # Summary
        logger.info("\n" + "="*80)
        logger.info("IMPORT COMPLETE")
        logger.info(f"  Reference Indicators: {num_indicators}")
        logger.info(f"  Data Years: {num_years}")
        logger.info("="*80)

    except Exception as e:
        logger.error(f"Import failed: {e}")
        raise


if __name__ == "__main__":
    main()
