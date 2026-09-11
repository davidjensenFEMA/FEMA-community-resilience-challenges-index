"""
Run complete CRIA pipeline with database storage.

This script orchestrates the complete CRIA workflow:
1. Import reference data (if not already done)
2. Sync geographies from Census API (if not already done)
3. Pull source data from all APIs
4. Calculate indicators from source data
5. Create aggregate CRIA scores
6. Store all data in database
7. Export results to Excel (optional)

Usage:
    # Run for counties with database storage
    DATABASE_URL="sqlite:///./cria.db" poetry run python scripts/run_full_pipeline.py --geography county --year 2021

    # Run without database (backwards compatibility)
    poetry run python scripts/run_full_pipeline.py --geography county --no-db

    # Run with Excel export
    poetry run python scripts/run_full_pipeline.py --geography county --year 2021 --export-excel

    # Skip data pull (use existing data)
    poetry run python scripts/run_full_pipeline.py --geography county --skip-pull --year 2021
"""

import argparse
from pathlib import Path
from typing import Optional
import sys
import signal
import threading

import numpy as np
import pandas as pd

from src.config.settings import settings
from src.api.census_client import confirm_suspect_api_key
from src.db.session import get_db_session, init_db
from src.db.repositories import GeographyRepository, ReferenceIndicatorRepository
from src.core.data_puller import DataPuller
from src.core.indicators import IndicatorCalculator
from src.core.aggregator import AggregateIndicator
from src.utils.logger import logger


# Default bin counts per geography (tract uses 7, all others use 5)
DEFAULT_BINS = {"county": 5, "tract": 7, "tribal": 5, "state": 5}

# Binning exceptions per geography (methods to exclude per indicator)
BINNING_EXCEPTIONS = {
    "county": {
        "Civil Org": ["jenks_caspall"],
        "Hospitals": ["jenks_caspall"],
        "Medical": ["jenks_caspall"],
    },
    "tract": {
        "Mobile Homes": ["jenks_caspall", "fisher_jenks"],
        "Limited English": ["jenks_caspall", "fisher_jenks"],
        "Poverty": [],
        "Hospitals": ["jenks_caspall", "fisher_jenks"],
    },
    "tribal": {
        "Limited English": ["jenks_caspall"],
    },
    "state": {},
}


def _impute_tract_from_county(
    indicators: pd.DataFrame,
    reference: pd.DataFrame,
    geo_reference: pd.DataFrame,
    county_indicators: pd.DataFrame,
    county_geo_reference: pd.DataFrame,
) -> pd.DataFrame:
    """
    Impute non-ACS indicator values for tracts from their parent county.

    For indicators sourced from CBP, EAVS, ARDA, POP — tract-level data
    doesn't exist, so each tract gets its parent county's value.

    This replicates the deprecated logic from
    cria_create_aggregate_tract.py lines 247-281.

    Args:
        indicators: Tract-level indicators DataFrame (GEO_ID index)
        reference: Reference DataFrame with Source column
        geo_reference: Tract geography reference with state/county columns
        county_indicators: County-level indicators DataFrame
        county_geo_reference: County geography reference with state/county columns

    Returns:
        Indicators DataFrame with non-ACS values imputed from county
    """
    non_acs_indicators = reference.loc[
        reference["Source"] != "ACS", "Indicator"
    ].tolist()

    if not non_acs_indicators:
        return indicators

    imputed = indicators.copy()

    # Build county lookup: (state, county) -> indicator values
    county_with_geo = county_indicators.copy()
    county_with_geo["_state"] = county_geo_reference["state"]
    county_with_geo["_county"] = county_geo_reference["county"]

    # Build tract -> (state, county) mapping
    tract_state = geo_reference["state"]
    tract_county = geo_reference["county"]

    # Create county-keyed lookup for non-ACS indicators
    cols_to_impute = [c for c in non_acs_indicators if c in county_indicators.columns]

    if not cols_to_impute:
        logger.warning("No non-ACS indicator columns found in county data for imputation")
        return indicators

    # Build a merge key for county data
    # Deduplicate by (state, county) — CT has 18 entries (9 old + 9 new planning regions)
    county_lookup = county_with_geo[cols_to_impute + ["_state", "_county"]].copy()
    county_lookup = county_lookup.drop_duplicates(subset=["_state", "_county"], keep="first")

    # Build tract merge frame
    tract_keys = pd.DataFrame({
        "_state": tract_state,
        "_county": tract_county,
    }, index=indicators.index)

    # Merge county values onto tract keys
    merged = tract_keys.merge(
        county_lookup,
        on=["_state", "_county"],
        how="left",
    )
    assert len(merged) == len(indicators), f"Merge expanded rows: {len(merged)} vs {len(indicators)}"
    merged.index = indicators.index

    # Overwrite non-ACS columns with county-imputed values
    for col in cols_to_impute:
        # First set to NaN (clear any existing zeros), then fill from county
        imputed[col] = merged[col]

    n_imputed = len(cols_to_impute)
    logger.info(f"Imputed {n_imputed} non-ACS indicators from county: {cols_to_impute}")

    return imputed


def _nullify_zero_vote_states(
    results: dict,
    source_data: Optional[pd.DataFrame],
    geo_reference: pd.DataFrame,
    geographies: dict,
) -> dict:
    """
    Set Inactive Voter_bins to NaN for states with zero voter data.

    Replicates deprecated logic from cria_create_aggregate_indicator.py
    lines 333-358 and cria_create_aggregate_tract.py lines 287-311.

    Args:
        results: Output dict from create_aggregate()
        source_data: Source data DataFrame with A1a, A1c columns
        geo_reference: Geography reference for current level
        geographies: Full geographies dict (needs 'state' for state_abbr lookup)

    Returns:
        Modified results dict with Inactive Voter_bins NaN'd for zero-vote states
    """
    if source_data is None:
        logger.warning("No source data available for vote data post-processing")
        return results

    bin_labels = results.get("bin_labels")
    if bin_labels is None or bin_labels.empty:
        return results

    if "Inactive Voter_bins" not in bin_labels.columns:
        logger.debug("No Inactive Voter_bins column in bin_labels, skipping vote fix")
        return results

    # Need A1a and A1c columns plus state_abbr to identify zero-vote states
    if "A1a" not in source_data.columns or "A1c" not in source_data.columns:
        logger.warning("A1a/A1c columns not in source data, skipping vote fix")
        return results

    if "state_abbr" not in geo_reference.columns:
        logger.warning("state_abbr not in geo_reference, skipping vote fix")
        return results

    # Compute votes by state: sum A1a and A1c per state_abbr
    vote_data = source_data[["A1a", "A1c"]].copy()
    vote_data["state_abbr"] = geo_reference["state_abbr"]
    votes_by_state = vote_data.groupby("state_abbr").sum(min_count=1)
    votes_by_state["prod"] = votes_by_state["A1a"] * votes_by_state["A1c"]

    zero_vote_states = set(
        votes_by_state.loc[votes_by_state["prod"] == 0].index
    )

    if not zero_vote_states:
        logger.debug("No zero-vote states found")
        return results

    logger.info(f"Zero-vote states: {sorted(zero_vote_states)}")

    # Match geo_reference state_abbr to bin_labels index
    df_bin = results["bin_labels"].copy()

    # Determine which rows belong to zero-vote states
    state_abbr_for_rows = geo_reference.reindex(df_bin.index)["state_abbr"]
    mask = state_abbr_for_rows.isin(zero_vote_states)

    n_nullified = mask.sum()
    df_bin.loc[mask, "Inactive Voter_bins"] = np.nan
    results["bin_labels"] = df_bin

    logger.info(
        f"Set Inactive Voter_bins to NaN for {n_nullified} rows "
        f"in {len(zero_vote_states)} zero-vote states"
    )

    return results


class PipelineTimeout:
    """
    Timeout handler for the CRIA pipeline.

    Prevents runaway processes by terminating after a configurable timeout.
    Uses SIGALRM on Unix systems, threading.Timer on Windows.
    """

    def __init__(self, timeout_minutes: int):
        """
        Initialize timeout handler.

        Args:
            timeout_minutes: Maximum runtime in minutes before termination
        """
        self.timeout_minutes = timeout_minutes
        self.timeout_seconds = timeout_minutes * 60
        self._timer = None
        self._using_signal = hasattr(signal, 'SIGALRM')

    def _timeout_handler(self, signum=None, frame=None):
        """Handle timeout - log error and exit."""
        logger.error("=" * 80)
        logger.error("PIPELINE TIMEOUT")
        logger.error("=" * 80)
        logger.error(f"Pipeline exceeded maximum runtime of {self.timeout_minutes} minutes")
        logger.error("This is a safety feature to prevent runaway processes.")
        logger.error("")
        logger.error("To increase the timeout, set PIPELINE_TIMEOUT_MINUTES in .env")
        logger.error(f"Example: PIPELINE_TIMEOUT_MINUTES=120")
        logger.error("=" * 80)
        sys.exit(1)

    def start(self):
        """Start the timeout timer."""
        logger.info(f"Pipeline timeout set to {self.timeout_minutes} minutes")

        if self._using_signal:
            # Unix: Use SIGALRM for reliable timeout
            signal.signal(signal.SIGALRM, self._timeout_handler)
            signal.alarm(self.timeout_seconds)
        else:
            # Windows: Use threading.Timer (less reliable but works)
            self._timer = threading.Timer(self.timeout_seconds, self._timeout_handler)
            self._timer.daemon = True
            self._timer.start()

    def cancel(self):
        """Cancel the timeout timer (call on successful completion)."""
        if self._using_signal:
            signal.alarm(0)  # Cancel alarm
        elif self._timer:
            self._timer.cancel()


class PipelinePreflightError(SystemExit):
    """Raised when a pre-pull database state check fails. Inherits SystemExit so the
    process exits with code 1 instead of dumping a traceback for what is, from the
    user's POV, a setup problem rather than a bug."""

    def __init__(self, message: str):
        super().__init__(1)
        self.message = message

    def __str__(self) -> str:
        return self.message


class YearMismatchError(SystemExit):
    """Raised when --year disagrees with settings.acs_year and the user has not
    explicitly opted in via --allow-year-mismatch. Same SystemExit pattern as
    PipelinePreflightError so the CLI exits cleanly with code 1."""

    def __init__(self, message: str):
        super().__init__(1)
        self.message = message

    def __str__(self) -> str:
        return self.message


def preflight_year_consistency(year: int, allow_mismatch: bool = False) -> None:
    """Refuse to start when the requested ``--year`` doesn't match ``settings.acs_year``.

    Closes a silent-mislabel failure mode: ``--year`` only flows into the output
    filename and DB year column — the actual ACS pull is governed by
    ``settings.acs_year`` (read from .env). A user with ``ACS_YEAR=2023`` who runs
    with ``--year 2024`` produces ``cria_results_county_2024.xlsx`` containing
    ACS 2023 data, with no warning.

    The override exists for the rare legitimate case (e.g. tagging a back-dated
    re-run, or comparing two vintages); it logs loudly so the divergence isn't
    invisible.
    """
    env_year = settings.acs_year
    if year == env_year:
        return

    summary = (
        f"--year={year} but settings.acs_year={env_year} "
        f"(from .env / ACS_YEAR environment variable)"
    )

    if allow_mismatch:
        logger.warning(
            "YEAR MISMATCH (allowed by --allow-year-mismatch): %s. "
            "Output will be labeled %s but the actual ACS data pulled is %s.",
            summary, year, env_year,
        )
        return

    message = (
        "\n" + "=" * 80 + "\n"
        "YEAR MISMATCH — REFUSING TO RUN\n"
        + "=" * 80 + "\n"
        f"  • {summary}\n\n"
        "The --year flag only labels output (filename, DB year column). The actual\n"
        "ACS data pulled is driven by settings.acs_year. Running anyway would\n"
        f"produce a file named '..._{year}.xlsx' that contains ACS {env_year} data.\n\n"
        "Fix one of:\n"
        f"  • Run with --year {env_year} (match the .env value)\n"
        f"  • Set ACS_YEAR={year} in .env (and rerun) to actually pull {year} data\n"
        f"  • Pass --allow-year-mismatch to acknowledge and proceed (logs a warning)\n"
        + "=" * 80
    )
    logger.error(message)
    raise YearMismatchError(message)


def preflight_database(geography: str, db) -> None:
    """Verify the DB is bootstrapped before we spend ~minutes pulling source data.

    Catches the silent-failure mode where a teammate runs the pipeline without first
    running ``import_reference_data.py`` / ``sync_geographies.py``: data pulls fine,
    save_to_database() then logs a warning per indicator and persists nothing, and
    the pipeline reports success while the DB stays empty.

    Tract pipelines additionally require county geographies (for D1 imputation of
    non-ACS indicators from the parent county at run_full_pipeline.py:415-434).
    """
    geo_repo = GeographyRepository(db)
    ref_repo = ReferenceIndicatorRepository(db)

    failures: list[str] = []

    ref_count = ref_repo.count()
    if ref_count == 0:
        failures.append(
            "  • reference_indicators table is empty\n"
            "      Fix: poetry run python scripts/import_reference_data.py"
        )

    geo_count = geo_repo.count(level=geography)
    if geo_count == 0:
        failures.append(
            f"  • geographies table has 0 rows for level={geography!r}\n"
            f"      Fix: poetry run python scripts/sync_geographies.py --level {geography}"
        )

    # Tract pulls also lean on county geographies for the D1 imputation step.
    if geography == "tract":
        county_count = geo_repo.count(level="county")
        if county_count == 0:
            failures.append(
                "  • geographies table has 0 rows for level='county' "
                "(required for tract D1 imputation)\n"
                "      Fix: poetry run python scripts/sync_geographies.py --level county"
            )

    if failures:
        message = (
            "\n" + "=" * 80 + "\n"
            "PIPELINE PREFLIGHT FAILED\n"
            + "=" * 80 + "\n"
            "Refusing to start data pull — the database is not bootstrapped, so the\n"
            "pipeline would silently produce empty/partial output.\n\n"
            + "\n".join(failures) + "\n\n"
            "Run `poetry run python scripts/doctor.py` for a full install report.\n"
            "If you intentionally want to skip database persistence, re-run with --no-db.\n"
            + "=" * 80
        )
        logger.error(message)
        raise PipelinePreflightError(message)

    logger.info(
        f"  Preflight OK: {ref_count} reference indicators, "
        f"{geo_count} {geography} geographies"
    )


def run_pipeline(
    geography: str = "county",
    year: Optional[int] = None,
    use_database: bool = True,
    export_excel: bool = False,
    skip_pull: bool = False,
    bins: Optional[int] = None,
    timeout_minutes: Optional[int] = None,
    allow_year_mismatch: bool = False,
) -> dict:
    """
    Run complete CRIA pipeline.

    Args:
        geography: Geography level ("state", "county", "tract", "tribal")
        year: Data year (uses settings default if not provided)
        use_database: Whether to store data in database
        export_excel: Whether to export results to Excel
        skip_pull: Skip data pull (use existing data)
        bins: Number of bins for classification (default: 7 for tract, 5 for others)
        timeout_minutes: Maximum runtime in minutes (default from settings)

    Returns:
        Dictionary with pipeline results and statistics
    """
    # D7: Auto-set bin count by geography (tract=7, others=5)
    if bins is None:
        bins = DEFAULT_BINS.get(geography, 5)

    logger.info("="*80)
    logger.info("FEMA CRIA PIPELINE")
    logger.info("="*80)
    logger.info(f"Geography: {geography}")
    logger.info(f"Year: {year or 'default'}")
    logger.info(f"Database: {use_database}")
    logger.info(f"Export Excel: {export_excel}")
    logger.info(f"Skip data pull: {skip_pull}")
    logger.info(f"Bins: {bins}")
    logger.info("="*80)

    # Initialize timeout handler
    timeout_mins = timeout_minutes or settings.pipeline_timeout_minutes
    timeout_handler = PipelineTimeout(timeout_mins)
    timeout_handler.start()

    # Determine year
    if year is None:
        year = settings.acs_year
        logger.info(f"Using default ACS year: {year}")
    else:
        # Refuse to run when --year disagrees with settings.acs_year unless the
        # user has explicitly opted in. See preflight_year_consistency() docstring.
        preflight_year_consistency(year=year, allow_mismatch=allow_year_mismatch)

    # Initialize database session if needed
    db_session = None
    if use_database:
        logger.info("\n--- Initializing Database ---")
        init_db()
        db_session = get_db_session()
        logger.info("Database initialized successfully")

    try:
        # Preflight runs inside the try so a failure here still closes db_session
        # cleanly via the finally block below.
        if use_database and db_session is not None:
            logger.info("\n--- Preflight: Verifying Database Bootstrap ---")
            preflight_database(geography=geography, db=db_session)

        # Statistics
        stats = {
            "geography": geography,
            "year": year,
            "source_data_shape": None,
            "indicators_shape": None,
            "aggregates_count": 0,
            "database_records": {
                "source_data": 0,
                "indicators": 0,
                "aggregates": 0
            },
            "excel_files": []
        }

        # =================================================================
        # STEP 1: Pull source data
        # =================================================================
        if not skip_pull:
            logger.info("\n--- Step 1: Pulling Source Data ---")
            puller = DataPuller(geography=geography, db=db_session)

            source_data = puller.pull_all_data()
            logger.info(f"✓ Pulled data: {source_data.shape}")
            stats["source_data_shape"] = source_data.shape

            # Save to database if enabled
            if use_database and db_session:
                logger.info("Saving source data to database...")
                puller.save_to_database(source_data, year=year, db=db_session)
                logger.info("✓ Source data saved to database")

            # Export to Excel if requested
            if export_excel:
                logger.info("Exporting source data to Excel...")
                puller.save_to_excel(source_data)
                stats["excel_files"].append(f"cria_inputs_{geography}.xlsx")
                logger.info("✓ Source data exported to Excel")
        else:
            logger.info("\n--- Step 1: Skipping Data Pull ---")
            source_data = None

        # =================================================================
        # STEP 2: Calculate indicators
        # =================================================================
        logger.info("\n--- Step 2: Calculating Indicators ---")
        calculator = IndicatorCalculator(geography=geography, db=db_session)

        indicators = calculator.calculate_all_indicators(source_data=source_data)
        logger.info(f"✓ Calculated indicators: {indicators.shape}")
        stats["indicators_shape"] = indicators.shape

        # Save to database if enabled
        if use_database and db_session:
            logger.info("Saving indicators to database...")
            calculator.save_to_database(indicators, year=year, db=db_session)
            logger.info("✓ Indicators saved to database")

        # Export to Excel if requested
        if export_excel:
            logger.info("Exporting indicators to Excel...")
            calculator.save_to_excel(indicators, source_data=source_data)
            stats["excel_files"].append(f"cria_indicators_{geography}_{year}.xlsx")
            logger.info("✓ Indicators exported to Excel")

        # =================================================================
        # STEP 3: Create aggregate scores
        # =================================================================
        logger.info("\n--- Step 3: Creating Aggregate Scores ---")

        # D4: Get geo_reference for special case handling (CT CBP, PR Limited English)
        geo_reference = calculator.data_puller.geographies.get(geography)

        # D1: Impute non-ACS indicators from county for tract
        if geography == "tract":
            county_geo = calculator.data_puller.geographies.get("county")
            if county_geo is not None and geo_reference is not None:
                logger.info("Running county indicator calculation for imputation...")
                county_calculator = IndicatorCalculator(
                    geography="county", db=db_session
                )
                county_indicators = county_calculator.calculate_all_indicators(
                    source_data=None
                )
                county_geo_ref = county_calculator.data_puller.geographies.get("county")

                logger.info("Imputing non-ACS indicators from county values...")
                indicators = _impute_tract_from_county(
                    indicators=indicators,
                    reference=calculator.reference,
                    geo_reference=geo_reference,
                    county_indicators=county_indicators,
                    county_geo_reference=county_geo_ref,
                )
            else:
                logger.warning(
                    "Cannot impute non-ACS indicators: "
                    "county or tract geo_reference not available"
                )

        # D9: For tract, filter out county-format GEO_IDs from the output
        # The DataPuller's outer merge introduces county-level rows (0500000US*)
        # alongside tract-level rows (1400000US*). The deprecated pipeline kept
        # only tract GEO_IDs (cria_create_aggregate_tract.py:236).
        if geography == "tract":
            tract_mask = indicators.index.str.startswith("1400000US")
            n_non_tract = (~tract_mask).sum()
            if n_non_tract > 0:
                indicators = indicators.loc[tract_mask]
                if geo_reference is not None:
                    geo_tract_mask = geo_reference.index.str.startswith("1400000US")
                    geo_reference = geo_reference.loc[geo_tract_mask]
                logger.info(
                    f"Tract: filtered to {tract_mask.sum()} tract GEO_IDs "
                    f"(removed {n_non_tract} county-format GEO_IDs)"
                )

        # D10: For tribal, filter out county-format GEO_IDs from the output
        # Same contamination pattern as D9 (tract), caused by DataPuller outer merge
        # introducing county-level rows (0500000US*) alongside tribal (2500000US*)
        if geography == "tribal":
            tribal_mask = indicators.index.str.startswith("2500000US")
            n_non_tribal = (~tribal_mask).sum()
            if n_non_tribal > 0:
                indicators = indicators.loc[tribal_mask]
                if source_data is not None:
                    source_tribal_mask = source_data.index.str.startswith("2500000US")
                    source_data = source_data.loc[source_tribal_mask]
                if geo_reference is not None:
                    geo_tribal_mask = geo_reference.index.str.startswith("2500000US")
                    geo_reference = geo_reference.loc[geo_tribal_mask]
                logger.info(
                    f"Tribal: filtered to {tribal_mask.sum()} tribal GEO_IDs "
                    f"(removed {n_non_tribal} county-format GEO_IDs)"
                )

        # D1b: For tribal, drop non-ACS indicator columns entirely
        # (replicates deprecated/old_scripts/cria_create_indicators_tribal.py:95-96)
        if geography == "tribal":
            non_acs_cols = calculator.reference.loc[
                calculator.reference["Source"] != "ACS", "Indicator"
            ].tolist()
            cols_to_drop = [c for c in non_acs_cols if c in indicators.columns]
            if cols_to_drop:
                logger.info(f"Tribal: dropping {len(cols_to_drop)} non-ACS indicator columns: {cols_to_drop}")
                indicators = indicators.drop(columns=cols_to_drop)
            else:
                logger.debug("Tribal: no non-ACS indicator columns to drop")

        # D8: For tribal, filter to non-zero-population rows before aggregation
        # (replicates deprecated/old_scripts/cria_create_indicators_tribal.py:116-127)
        # County-type GEOs (0500000US*) have all-NaN ACS data; including them
        # causes mean-imputation to make 82% of rows identical (degenerate bins).
        tribal_full_index = None
        if geography == "tribal" and source_data is not None:
            pop_col = "S0101_C01_001E"  # Total population from ACS Age & Sex
            if pop_col in source_data.columns:
                # Build set of GEO_IDs with non-zero population
                pop_series = source_data[pop_col].fillna(0)
                nonzero_geo_ids = set(pop_series[pop_series != 0].index)
                # Filter indicators (may have different index type than source_data)
                keep_mask = indicators.index.isin(nonzero_geo_ids)
                n_excluded = (~keep_mask).sum()
                n_kept = keep_mask.sum()
                if n_excluded > 0:
                    tribal_full_index = indicators.index.copy()
                    indicators = indicators.loc[keep_mask]
                    if geo_reference is not None:
                        geo_keep = geo_reference.index.isin(nonzero_geo_ids)
                        geo_reference = geo_reference.loc[geo_keep]
                    logger.info(
                        f"Tribal: filtered to {n_kept} non-zero-population rows "
                        f"(excluded {n_excluded} zero-population GEOs)"
                    )
            else:
                logger.warning(f"Tribal: {pop_col} not in source_data, skipping zero-pop filter")

        # Get binning exceptions for this geography
        exceptions = BINNING_EXCEPTIONS.get(geography, {})

        aggregator = AggregateIndicator(
            geography=geography,
            bins=bins,
            db=db_session
        )

        results = aggregator.create_aggregate(
            indicators=indicators,
            reference=calculator.reference,
            geo_reference=geo_reference,
            bin_indicators=True,
            exceptions=exceptions,
            skip_aggregation=(geography == "tribal"),
        )

        # For tribal, include source data in results for Excel export
        # (replicates deprecated output which had a "data" tab)
        if geography == "tribal" and source_data is not None:
            results["data"] = source_data

        # D8b: Re-index tribal results back to full index (excluded rows get NaN)
        if tribal_full_index is not None:
            for key in ("bin_labels",):
                if key in results and results[key] is not None:
                    results[key] = results[key].reindex(tribal_full_index)
                    logger.debug(f"Tribal: re-indexed {key} to full {len(tribal_full_index)} rows")

        # D6: Nullify Inactive Voter_bins for states with zero voter data
        # (tribal drops Inactive Voter via D1b, so this is a no-op for tribal,
        # but the guard inside _nullify_zero_vote_states handles it safely)
        if geo_reference is not None and "bin_labels" in results:
            results = _nullify_zero_vote_states(
                results=results,
                source_data=source_data,
                geo_reference=geo_reference,
                geographies=calculator.data_puller.geographies,
            )

        agg_df = results.get("agg")
        if agg_df is not None:
            logger.info(f"✓ Created aggregates: {len(agg_df)} geographies")
            stats["aggregates_count"] = len(agg_df)
        else:
            bin_labels = results.get("bin_labels")
            n_binned = len(bin_labels) if bin_labels is not None else 0
            logger.info(f"✓ Binning complete (no aggregation for {geography}): {n_binned} rows")
            stats["aggregates_count"] = 0

        # Save to database if enabled
        if use_database and db_session and "agg" in results:
            logger.info("Saving aggregates to database...")
            aggregator.save_to_database(results, year=year, db=db_session)
            logger.info("✓ Aggregates saved to database")

        # Export to Excel if requested
        if export_excel:
            logger.info("Exporting aggregates to Excel...")
            from src.config.paths import paths
            excel_filename = f"cria_results_{geography}_{year}.xlsx"
            excel_path = paths.output / excel_filename
            aggregator.save_to_excel(
                results,
                file_path=str(excel_path),
                reference=calculator.reference,
                years=calculator.years
            )
            stats["excel_files"].append(excel_filename)
            logger.info(f"✓ Aggregates exported to Excel: {excel_path}")

        # =================================================================
        # Summary
        # =================================================================
        logger.info("\n" + "="*80)
        logger.info("PIPELINE COMPLETE")
        logger.info("="*80)
        logger.info(f"Geography: {geography}")
        logger.info(f"Year: {year}")

        if stats["source_data_shape"]:
            logger.info(f"Source data: {stats['source_data_shape'][0]} rows × {stats['source_data_shape'][1]} columns")

        if stats["indicators_shape"]:
            logger.info(f"Indicators: {stats['indicators_shape'][0]} rows × {stats['indicators_shape'][1]} indicators")

        logger.info(f"Aggregates: {stats['aggregates_count']} geographies")

        if use_database:
            logger.info("\nDatabase storage: ENABLED")
            logger.info("  All data saved to database")

        if export_excel:
            logger.info("\nExcel exports:")
            for filename in stats["excel_files"]:
                logger.info(f"  ✓ {filename}")

        logger.info("="*80)

        return stats

    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        raise

    finally:
        # Cancel timeout on completion (success or failure)
        timeout_handler.cancel()

        # Close database session
        if db_session:
            db_session.close()
            logger.debug("Database session closed")


def main():
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description="Run complete CRIA pipeline with database storage"
    )
    parser.add_argument(
        "--geography",
        choices=["state", "county", "tract", "tribal"],
        default="county",
        help="Geography level (default: county)"
    )
    parser.add_argument(
        "--year",
        type=int,
        help=(
            f"Data year — must equal settings.acs_year={settings.acs_year} "
            "from .env (use --allow-year-mismatch to override)"
        ),
    )
    parser.add_argument(
        "--allow-year-mismatch",
        action="store_true",
        help=(
            "Allow --year to differ from settings.acs_year. Off by default — "
            "the mismatch is the silent-mislabel bug that produced "
            "'cria_results_county_2024.xlsx' containing ACS 2023 data."
        ),
    )
    parser.add_argument(
        "--no-db",
        dest="use_database",
        action="store_false",
        help="Disable database storage (backwards compatibility mode)"
    )
    parser.add_argument(
        "--export-excel",
        action="store_true",
        help="Export results to Excel files"
    )
    parser.add_argument(
        "--skip-pull",
        action="store_true",
        help="Skip data pull (use for testing with existing data)"
    )
    parser.add_argument(
        "--bins",
        type=int,
        default=None,
        help="Number of bins for classification (default: 7 for tract, 5 for others)"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        help=f"Timeout in minutes (default: {settings.pipeline_timeout_minutes})"
    )
    parser.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Skip the prompt that warns when CENSUS_API_KEY does not look valid"
    )

    args = parser.parse_args()

    # Preflight: warn (and prompt) if CENSUS_API_KEY does not look right.
    # The pipeline pulls source data first; failing here saves the user a
    # noisy error several seconds later.
    if not args.skip_pull and not confirm_suspect_api_key(assume_yes=args.yes):
        logger.error("Aborted by user: suspect CENSUS_API_KEY format.")
        sys.exit(1)

    try:
        run_pipeline(
            geography=args.geography,
            year=args.year,
            use_database=args.use_database,
            export_excel=args.export_excel,
            skip_pull=args.skip_pull,
            bins=args.bins,
            timeout_minutes=args.timeout,
            allow_year_mismatch=args.allow_year_mismatch,
        )
    except Exception as e:
        logger.error(f"Pipeline execution failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
