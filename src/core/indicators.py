"""
IndicatorCalculator class - calculates CRIA indicators from source data.

Transforms raw source data (counts) into indicators (rates, ratios).
Replaces functional code from cria_create_indicators.py.
"""

from typing import Optional
import pandas as pd
import numpy as np
import logging
from sqlalchemy.orm import Session

from src.core.data_puller import DataPuller
from src.db.repositories import (
    GeographyRepository, ReferenceIndicatorRepository, IndicatorRepository
)

logger = logging.getLogger(__name__)


class IndicatorCalculator:
    """
    Calculate CRIA indicators from source data.

    Takes raw data (population counts, establishment counts, etc.)
    and calculates indicators (poverty rate, establishments per capita, etc.)
    based on functions defined in the reference file.

    Supported functions:
    - divide: numerator / denominator
    - max: max(numerators) / denominator
    - mean: mean(numerators) / denominator
    - divide_scalar: (numerator / denominator) * scalar
    - reverse_divide: (denominator - numerator) / denominator

    Example:
        >>> calc = IndicatorCalculator(geography='county')
        >>> indicators = calc.calculate_all_indicators()
        >>> print(indicators.head())
    """

    def __init__(self, geography: str = "county", db: Optional[Session] = None):
        """
        Initialize IndicatorCalculator.

        Args:
            geography: Geographic level ('state', 'county', 'tract', 'tribal')
            db: Optional database session for storing indicators
        """
        self.geography = geography
        self.db = db
        self.data_puller = DataPuller(geography, db=db)
        self.reference = self.data_puller.reference
        self.years = self.data_puller.years

        logger.info(f"IndicatorCalculator initialized for {geography} geography")
        if db is not None:
            logger.info("  Database session provided - will store indicators")

    def calculate_all_indicators(
        self,
        source_data: Optional[pd.DataFrame] = None,
    ) -> pd.DataFrame:
        """
        Calculate all indicators from source data.

        Args:
            source_data: Optional pre-pulled source data.
                        If None, will pull data automatically.

        Returns:
            DataFrame indexed by GEO_ID with calculated indicators

        Example:
            >>> calc = IndicatorCalculator(geography='county')
            >>> indicators = calc.calculate_all_indicators()
            >>> print(indicators['Poverty'].head())
        """
        # Pull source data if not provided
        if source_data is None:
            logger.info("No source data provided, pulling data...")
            source_data = self.data_puller.pull_all_data()

        logger.info(f"Calculating {len(self.reference)} indicators")

        # Initialize results DataFrame
        indicators = pd.DataFrame(index=source_data.index)

        # Calculate each indicator
        for idx, row in self.reference.iterrows():
            indicator_name = row["Indicator"]
            function = row["Function"]

            logger.info(f"[{idx}] Calculating {indicator_name} (function: {function})")

            try:
                result = self._calculate_indicator(idx, row, source_data)
                indicators[indicator_name] = result

                # Log summary stats
                n_valid = result.notna().sum()
                n_total = len(result)
                pct_valid = 100 * n_valid / n_total if n_total > 0 else 0

                logger.debug(
                    f"  Valid: {n_valid}/{n_total} ({pct_valid:.1f}%), "
                    f"Mean: {result.mean():.4f}, "
                    f"Std: {result.std():.4f}"
                )

            except Exception as e:
                logger.error(f"  Failed to calculate {indicator_name}: {e}", exc_info=True)
                # Create empty column
                indicators[indicator_name] = np.nan

        logger.info(f"Calculation complete. Shape: {indicators.shape}")

        return indicators

    def _calculate_indicator(
        self,
        idx: int,
        row: pd.Series,
        data: pd.DataFrame,
    ) -> pd.Series:
        """
        Calculate a single indicator.

        Args:
            idx: Reference index
            row: Reference row with indicator definition
            data: Source data DataFrame

        Returns:
            Series with calculated indicator values
        """
        function = row["Function"]

        # Dispatch to appropriate calculation function
        if function == "divide":
            return self._divide_function(row, data)
        elif function == "max":
            return self._max_function(row, data)
        elif function == "mean":
            return self._mean_function(row, data)
        elif function == "divide_scalar":
            return self._divide_scalar_function(row, data)
        elif function == "reverse_divide":
            return self._reverse_divide_function(row, data)
        else:
            logger.warning(f"Unknown function: {function}")
            return pd.Series(index=data.index, dtype=float)

    def _divide_function(self, row: pd.Series, data: pd.DataFrame) -> pd.Series:
        """
        Calculate indicator: sum(numerators) / denominator.

        Args:
            row: Reference row
            data: Source data

        Returns:
            Calculated indicator
        """
        num_cols = self._parse_numerator(row["numerator"])
        denom = row["denominator"]

        # Calculate numerator (sum of columns)
        numerator = data[num_cols].sum(axis=1)

        # Calculate denominator
        if isinstance(denom, str):
            # Denominator is a column
            denominator = data[denom]
            result = numerator / denominator

            # Set to NaN where denominator is 0 (undefined, not zero)
            result.loc[denominator == 0] = np.nan

        else:
            # Denominator is a scalar
            result = numerator / denom

        # Set to NaN where numerator data is missing
        missing_mask = data[num_cols].isna().any(axis=1)
        result.loc[missing_mask] = np.nan

        return result

    def _max_function(self, row: pd.Series, data: pd.DataFrame) -> pd.Series:
        """
        Calculate indicator: max(numerators) / denominator.

        Args:
            row: Reference row
            data: Source data

        Returns:
            Calculated indicator
        """
        num_cols = self._parse_numerator(row["numerator"])
        denom = row["denominator"]

        # Calculate numerator (max of columns)
        numerator = data[num_cols].max(axis=1)

        # Calculate result
        if isinstance(denom, str):
            denominator = data[denom]
            result = numerator / denominator
            result.loc[denominator == 0] = np.nan
        else:
            result = numerator / denom

        # Set to NaN where data is missing
        missing_mask = data[num_cols].isna().all(axis=1)
        result.loc[missing_mask] = np.nan

        return result

    def _mean_function(self, row: pd.Series, data: pd.DataFrame) -> pd.Series:
        """
        Calculate indicator: mean(numerators) / denominator.

        Typically used for population migration (average over multiple years).

        Args:
            row: Reference row
            data: Source data

        Returns:
            Calculated indicator
        """
        # For mean function, numerator is typically "NETMIG" and we need to
        # construct column names from years
        year_pop = self.years.get("pop", 2020)
        num_cols = [f"NETMIG{year}" for year in range(year_pop, year_pop - 5, -1)]

        # Filter to columns that exist
        num_cols = [c for c in num_cols if c in data.columns]

        if not num_cols:
            logger.warning("No NETMIG columns found for mean function")
            return pd.Series(index=data.index, dtype=float)

        denom = row["denominator"]

        # Calculate mean
        numerator = data[num_cols].mean(axis=1)

        # Calculate result
        if isinstance(denom, str):
            denominator = data[denom]
            result = numerator / denominator
            result.loc[denominator == 0] = np.nan
        else:
            result = numerator / denom

        return result

    def _divide_scalar_function(self, row: pd.Series, data: pd.DataFrame) -> pd.Series:
        """
        Calculate indicator: (sum(numerators) / denominator) * scalar.

        Used for rates per 1000, etc.

        Args:
            row: Reference row
            data: Source data

        Returns:
            Calculated indicator
        """
        num_cols = self._parse_numerator(row["numerator"])
        denom = row["denominator"]
        scalar = row["rate"] * 1000  # Rate recorded as ~1k in reference

        # Calculate
        numerator = data[num_cols].sum(axis=1)

        if isinstance(denom, str):
            denominator = data[denom]
            result = (numerator / denominator) * scalar
            result.loc[denominator == 0] = np.nan
        else:
            result = (numerator / denom) * scalar

        # Set to NaN where numerator is missing
        missing_mask = data[num_cols].isna().any(axis=1)
        result.loc[missing_mask] = np.nan

        return result

    def _reverse_divide_function(self, row: pd.Series, data: pd.DataFrame) -> pd.Series:
        """
        Calculate indicator: (denominator - sum(numerators)) / denominator.

        Used for things like "percent without X" when you have "percent with X".

        Args:
            row: Reference row
            data: Source data

        Returns:
            Calculated indicator
        """
        num_cols = self._parse_numerator(row["numerator"])
        denom = row["denominator"]

        # Calculate numerator (what we DON'T have)
        numerator_sum = data[num_cols].sum(axis=1)

        if isinstance(denom, str):
            denominator = data[denom]

            # Ensure non-negative (can't have negative "without X")
            numerator = pd.concat([
                pd.Series(0, index=data.index),
                denominator - numerator_sum,
            ], axis=1).max(axis=1)

            result = numerator / denominator
            result.loc[denominator == 0] = np.nan

            # Log cases where denominator < numerator (data issue)
            negative_mask = (denominator - numerator_sum) < 0
            if negative_mask.sum() > 0:
                logger.warning(
                    f"  {negative_mask.sum()} cases where denominator < numerator "
                    f"(capped at 0)"
                )

        else:
            numerator = pd.concat([
                pd.Series(0, index=data.index),
                denom - numerator_sum,
            ], axis=1).max(axis=1)

            result = numerator / denom

        # Set to NaN where numerator is missing
        missing_mask = data[num_cols].isna().any(axis=1)
        result.loc[missing_mask] = np.nan

        return result

    def _parse_numerator(self, numerator) -> list:
        """
        Parse numerator into list of column names.

        Args:
            numerator: Numerator specification (str with commas, or single value)

        Returns:
            List of column names
        """
        if isinstance(numerator, str):
            cols = numerator.split(",")
            cols = [c.strip() for c in cols]
        else:
            cols = [str(int(numerator))]  # CBP NAICS code

        return cols

    def save_to_excel(
        self,
        indicators: pd.DataFrame,
        source_data: Optional[pd.DataFrame] = None,
        filename: Optional[str] = None,
    ):
        """
        Save indicators to Excel (with optional source data).

        Args:
            indicators: Calculated indicators DataFrame
            source_data: Optional source data to include
            filename: Output filename
        """
        from src.config.paths import paths

        if filename is None:
            year = self.years.get("acs", 2021)
            filename = f"cria_indicators_{self.geography}_{year}.xlsx"

        output_path = paths.get_output_file(filename)

        logger.info(f"Saving indicators to: {output_path}")

        # Create Excel writer
        with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
            # Save indicators
            indicators.to_excel(writer, sheet_name="indicators")

            # Save source data if provided
            if source_data is not None:
                source_data.to_excel(writer, sheet_name="source_data")

        logger.info(f"  Saved {indicators.shape}")

    def save_to_database(
        self,
        indicators: pd.DataFrame,
        year: int,
        db: Optional[Session] = None
    ):
        """
        Save calculated indicators to database.

        Args:
            indicators: Calculated indicators DataFrame (indexed by GEO_ID)
            year: Data year
            db: Optional database session (uses self.db if not provided)

        Note:
            This stores the calculated indicator values (after applying functions).
            Uses upsert to handle duplicate entries.
        """
        db = db or self.db

        if db is None:
            logger.warning("No database session provided, skipping database save")
            return

        logger.info(f"Saving indicators to database (year={year})")

        # Get repositories
        geo_repo = GeographyRepository(db)
        ref_repo = ReferenceIndicatorRepository(db)
        ind_repo = IndicatorRepository(db)

        # Build mapping of indicator names to database IDs
        indicator_map = {}
        for _, row in self.reference.iterrows():
            indicator_name = row["Indicator"]
            db_indicator = ref_repo.get_by_name(indicator_name)
            if db_indicator:
                indicator_map[indicator_name] = db_indicator.id
            else:
                logger.warning(f"Indicator not found in database: {indicator_name}")

        # Defense-in-depth: TOTAL miss (every reference indicator missing from DB)
        # is a setup-state error, not a data issue — fail loudly so callers that
        # bypass scripts/run_full_pipeline.py preflight still see the problem.
        # Partial misses still warn-and-continue above (single missing indicator).
        if not indicator_map and len(self.reference) > 0:
            raise RuntimeError(
                "Cannot persist indicators: indicator_map is empty "
                "(no reference indicators in database). "
                "Run `poetry run python scripts/import_reference_data.py` "
                "to populate, then re-run."
            )

        # Get geo_id -> database id mapping in a single query (fast!)
        # This replaces 88k individual get_by_geo_id() calls with one query
        logger.info("  Loading geography ID mapping...")
        geo_id_map = geo_repo.get_geo_id_map(level=self.geography)
        logger.info(f"  Loaded {len(geo_id_map)} geography mappings")

        # Defense-in-depth: empty geographies table for this level is also a
        # setup-state error. The per-row skip below would silently drop every
        # row otherwise.
        if not geo_id_map and len(indicators.index) > 0:
            raise RuntimeError(
                f"Cannot persist indicators: geo_id_map is empty for level='{self.geography}' "
                "(no geographies in database for this level). "
                f"Run `poetry run python scripts/sync_geographies.py --level {self.geography}` "
                "to populate, then re-run."
            )

        # Process each geography
        indicator_records = []
        processed_geos = 0
        skipped_geos = 0

        for geo_id in indicators.index:
            # Fast dictionary lookup instead of database query
            db_geo_id = geo_id_map.get(str(geo_id))
            if db_geo_id is None:
                skipped_geos += 1
                continue

            # Process each indicator column
            for indicator_name in indicators.columns:
                value = indicators.loc[geo_id, indicator_name]

                # Skip NaN values
                if pd.isna(value):
                    continue

                # Get indicator ID
                indicator_id = indicator_map.get(indicator_name)
                if indicator_id is None:
                    continue

                indicator_records.append({
                    "geography_id": db_geo_id,
                    "indicator_id": indicator_id,
                    "value": float(value),
                    "year": year,
                    "is_clean": True,
                    "is_imputed": False
                })

            processed_geos += 1

            # Log progress every 10000 geographies for large datasets
            if processed_geos % 10000 == 0:
                logger.info(f"  Processed {processed_geos} geographies...")

        # Bulk insert indicators using SQLAlchemy Core (fast!)
        if indicator_records:
            logger.info(f"Bulk inserting {len(indicator_records)} indicator records...")
            num_inserted = ind_repo.bulk_create(indicator_records)
            db.commit()
            logger.info(f"✓ Saved {num_inserted} indicator records")
        else:
            logger.warning("No indicator records to save")

        if skipped_geos > 0:
            logger.warning(f"Skipped {skipped_geos} geographies not found in database")

    def __repr__(self) -> str:
        """String representation."""
        return f"IndicatorCalculator(geography={self.geography})"
