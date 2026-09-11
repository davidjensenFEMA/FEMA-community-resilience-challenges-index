"""
Sync geographies from Census API to database.

This script fetches geographic reference data from the Census API
and stores it in the database geographies table.

Usage:
    # Sync all geography levels
    DATABASE_URL="sqlite:///./cria.db" poetry run python scripts/sync_geographies.py

    # Sync specific level
    DATABASE_URL="sqlite:///./cria.db" poetry run python scripts/sync_geographies.py --level county

    # Dry run (don't save to database)
    poetry run python scripts/sync_geographies.py --dry-run
"""

import argparse
from typing import Optional, List
import pandas as pd

import sys

from src.api.census_client import CensusAPIClient, confirm_suspect_api_key
from src.db.session import get_db, init_db
from src.db.repositories import GeographyRepository
from src.utils.logger import logger


def sync_geographies(
    levels: Optional[List[str]] = None,
    dry_run: bool = False
) -> dict:
    """
    Sync geographies from Census API to database.

    Args:
        levels: List of geography levels to sync. If None, syncs all.
                Options: ["state", "county", "tract", "tribal"]
        dry_run: If True, fetch data but don't save to database

    Returns:
        Dictionary with sync statistics
    """
    if levels is None:
        levels = ["state", "county", "tract", "tribal"]

    logger.info("="*80)
    logger.info("Geography Sync")
    logger.info("="*80)
    logger.info(f"Levels to sync: {', '.join(levels)}")
    logger.info(f"Dry run: {dry_run}")

    # Initialize Census API client
    census = CensusAPIClient()

    # Statistics
    stats = {
        "levels": [],
        "fetched": 0,
        "created": 0,
        "skipped": 0,
        "errors": 0
    }

    # Initialize database if not dry run
    if not dry_run:
        logger.info("\nInitializing database...")
        init_db()

    # Process each level
    for level in levels:
        logger.info(f"\n--- Syncing {level} geographies ---")
        stats["levels"].append(level)

        try:
            # Fetch geographies from Census API
            logger.info(f"Fetching {level} data from Census API...")
            geo_df = census.get_geographies(level)

            if geo_df is None or geo_df.empty:
                logger.warning(f"No {level} geographies fetched")
                continue

            logger.info(f"Fetched {len(geo_df)} {level} geographies")
            stats["fetched"] += len(geo_df)

            if dry_run:
                logger.info("Dry run - skipping database save")
                logger.info(f"Sample data:\n{geo_df.head()}")
                continue

            # Save to database
            logger.info(f"Saving to database...")
            with get_db() as db:
                geo_repo = GeographyRepository(db)

                created = 0
                skipped = 0

                for idx, row in geo_df.iterrows():
                    geo_id = str(row.get("GEO_ID", idx))

                    # Check if geography already exists
                    existing = geo_repo.get_by_geo_id(geo_id)
                    if existing:
                        logger.debug(f"Geography {geo_id} already exists, skipping")
                        skipped += 1
                        continue

                    # Create geography record
                    geo_data = {
                        "geo_id": geo_id,
                        "name": row.get("NAME", "Unknown"),
                        "geography_level": level,
                    }

                    # Add state code if available
                    if "state" in row:
                        geo_data["state_code"] = str(row["state"]).zfill(2)

                    # Add state name if available
                    if "state_name" in row:
                        geo_data["state_name"] = row["state_name"]

                    # Add county code if available
                    if "county" in row:
                        geo_data["county_code"] = str(row["county"]).zfill(3)

                    # Add population if available
                    if "POP" in row or "population" in row:
                        pop_col = "POP" if "POP" in row else "population"
                        if pd.notna(row[pop_col]):
                            geo_data["population"] = int(row[pop_col])

                    # Create geography
                    geo_repo.create(**geo_data)
                    created += 1

                    # Log progress every 500 records
                    if created % 500 == 0:
                        logger.info(f"  Created {created} geographies...")

                # Commit all changes
                db.commit()

                logger.info(f"✓ Created {created} new {level} geographies")
                logger.info(f"  Skipped {skipped} existing {level} geographies")

                stats["created"] += created
                stats["skipped"] += skipped

        except Exception as e:
            logger.error(f"Error syncing {level} geographies: {e}", exc_info=True)
            stats["errors"] += 1
            continue

    # Summary
    logger.info("\n" + "="*80)
    logger.info("SYNC COMPLETE")
    logger.info("="*80)
    logger.info(f"Levels synced: {len(stats['levels'])}")
    logger.info(f"Geographies fetched: {stats['fetched']}")
    if not dry_run:
        logger.info(f"Geographies created: {stats['created']}")
        logger.info(f"Geographies skipped: {stats['skipped']}")
    logger.info(f"Errors: {stats['errors']}")
    logger.info("="*80)

    return stats


def main():
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description="Sync geographies from Census API to database"
    )
    parser.add_argument(
        "--level",
        choices=["state", "county", "tract", "tribal"],
        help="Geography level to sync (default: all levels)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch data but don't save to database"
    )
    parser.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Skip the prompt that warns when CENSUS_API_KEY does not look valid"
    )

    args = parser.parse_args()

    # Preflight: warn (and prompt) if CENSUS_API_KEY does not look right.
    if not confirm_suspect_api_key(assume_yes=args.yes):
        logger.error("Aborted by user: suspect CENSUS_API_KEY format.")
        sys.exit(1)

    # Determine levels to sync
    levels = [args.level] if args.level else None

    # Run sync
    sync_geographies(levels=levels, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
