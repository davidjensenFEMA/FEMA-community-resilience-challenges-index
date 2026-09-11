"""
DataPuller class - orchestrates data collection from multiple sources.

This class replaces the functional code in cria_pull_data.py with an
object-oriented approach that's easier to test and maintain.
"""

from typing import Optional, Dict
import pandas as pd
import logging
from sqlalchemy.orm import Session

from src.api.census_client import CensusAPIClient
from src.api.cbp_client import CBPClient
from src.api.external_clients import EAVSClient, ARDAClient, POPClient
from src.config.paths import paths
from src.config.settings import settings
from src.db.repositories import (
    GeographyRepository, ReferenceIndicatorRepository, SourceDataRepository
)

logger = logging.getLogger(__name__)


class DataPuller:
    """
    Orchestrates data collection from multiple sources.

    Pulls raw data needed for CRIA indicator calculation:
    - ACS (American Community Survey) - demographic/economic data
    - CBP (County Business Patterns) - establishment counts
    - EAVS (Election Admin) - voter registration
    - ARDA (Religion census) - religious adherents
    - POP (Population estimates) - migration data

    Example:
        >>> puller = DataPuller(geography='county')
        >>> data = puller.pull_all_data()
        >>> print(data.shape)
        (3143, 85)  # 3143 counties, 85 source columns
    """

    def __init__(self, geography: str = "county", db: Optional[Session] = None):
        """
        Initialize DataPuller.

        Args:
            geography: Geographic level ('state', 'county', 'tract', 'tribal')
            db: Optional database session for storing data
        """
        self.geography = geography
        self.db = db

        # Initialize API clients
        self.census = CensusAPIClient()
        self.cbp = CBPClient()
        self.eavs = EAVSClient()
        self.arda = ARDAClient()
        self.pop = POPClient()

        # Load reference data
        self.reference = self._load_reference()
        self.years = self._load_years()
        self.geographies = self._load_geographies()

        logger.info(f"DataPuller initialized for {geography} geography")
        logger.info(f"  Reference: {len(self.reference)} indicators")
        logger.info(f"  Years: {self.years}")
        if db is not None:
            logger.info("  Database session provided - will store source data")

    def _load_reference(self) -> pd.DataFrame:
        """
        Load indicator reference data from Excel.

        Returns:
            DataFrame with indicator definitions
        """
        logger.debug(f"Loading reference from: {paths.reference_file}")

        xl = pd.ExcelFile(paths.reference_file)
        ref = xl.parse("Status")

        # Filter to active indicators (those in Order_2023)
        ref = ref.dropna(subset=["Order_2023"], axis=0)
        ref = ref.sort_values("Order_2023")

        logger.debug(f"  Loaded {len(ref)} indicators")

        return ref

    def _load_years(self) -> Dict[str, int]:
        """
        Load year configuration from Excel.

        Returns:
            Dictionary mapping source names to years
        """
        xl = pd.ExcelFile(paths.reference_file)
        years_df = xl.parse("Years")

        years = dict(zip(years_df.label, years_df.year_ref))

        # Also include settings years for consistency
        years.update(settings.years_dict)

        return years

    def _load_geographies(self) -> Dict[str, pd.DataFrame]:
        """
        Load geography reference data.

        Loader precedence:
          1. data/geographies/{level}.parquet — checked-in, portable (preferred)
          2. data/ser_geo.pkl — legacy pickle cache
          3. Census API fallback (currently produces stripped columns —
             acceptable as last-resort only)

        Returns:
            Dictionary mapping geography levels to DataFrames
        """
        logger.debug("Loading geography reference data")

        geographies = {}
        levels = ["state", "county", "tract", "tribal"]

        parquet_dir = paths.data / "geographies"
        if parquet_dir.exists():
            for level in levels:
                pq = parquet_dir / f"{level}.parquet"
                if pq.exists():
                    try:
                        geographies[level] = pd.read_parquet(pq)
                    except ImportError as e:
                        # No parquet engine installed (pyarrow / fastparquet).
                        # Fail loudly: silently falling back to the Census API path
                        # produces a stripped geography reference (no state_abbr,
                        # county_name, etc.) which corrupts downstream EAVS/CBP joins
                        # and yields tens of thousands of NaN-indexed rows during merge.
                        raise RuntimeError(
                            f"Cannot read geography parquet ({pq}): no parquet engine "
                            f"installed. Run `poetry install` to install pyarrow "
                            f"(declared in pyproject.toml). Original error: {e}"
                        ) from e
                    except Exception as e:
                        logger.warning(f"Failed to load {pq}: {e}")
            if len(geographies) == len(levels):
                logger.debug(f"  Loaded geographies from parquet: {list(geographies.keys())}")
                return geographies

        pkl_path = paths.data / "ser_geo.pkl"
        if pkl_path.exists():
            try:
                ser_geo = pd.read_pickle(pkl_path)
                geographies = ser_geo.to_dict()
                logger.debug(f"  Loaded from pickle: {list(geographies.keys())}")
                return geographies
            except Exception as e:
                logger.warning(f"Failed to load pickle, will fetch: {e}")

        logger.info("Fetching geography data from Census API...")
        for level in levels:
            try:
                df = self.census.get_geographies(level)
                geographies[level] = df
                logger.info(f"  Fetched {len(df)} {level} geographies")
            except Exception as e:
                logger.error(f"  Failed to fetch {level}: {e}")

        try:
            ser_geo = pd.Series(geographies)
            ser_geo.to_pickle(pkl_path)
            logger.debug(f"  Saved to pickle: {pkl_path}")
        except Exception as e:
            logger.warning(f"Failed to save pickle: {e}")

        return geographies

    def pull_all_data(self) -> pd.DataFrame:
        """
        Pull all CRIA source data based on reference file.

        This is the main entry point - loops through reference file
        and calls appropriate data source for each indicator.

        Returns:
            DataFrame indexed by GEO_ID with all source columns
        """
        logger.info(f"Starting data pull for {self.geography} geography")
        logger.info(f"  Pulling {len(self.reference)} indicators")

        data = pd.DataFrame()

        for idx, row in self.reference.iterrows():
            indicator = row["Indicator"]
            source = row["Source"]

            logger.info(f"[{idx}] {indicator} from {source}")

            try:
                # Pull data based on source
                if source == "ACS":
                    df = self._pull_acs_indicator(idx, row)
                elif source == "CBP":
                    df = self._pull_cbp_indicator(idx, row)
                elif source == "EAVS":
                    df = self._pull_eavs_indicator(idx, row)
                elif source == "ARDA":
                    df = self._pull_arda_indicator(idx, row)
                elif source == "POP":
                    df = self._pull_pop_indicator(idx, row)
                else:
                    logger.warning(f"  Skipping - unknown source: {source}")
                    continue

                # Merge into main dataframe
                if data.empty:
                    data = df.copy()
                else:
                    # Drop columns from df that already exist in data
                    # Census API returns shared columns (NAME, denominators) with every request
                    # This prevents duplicate columns like DP04_0001E_x, DP04_0001E_y
                    existing_cols = set(data.columns)
                    new_cols = set(df.columns)
                    duplicate_cols = existing_cols & new_cols

                    if duplicate_cols:
                        logger.debug(f"  Dropping duplicate columns from merge: {duplicate_cols}")
                        df = df.drop(columns=list(duplicate_cols))

                    # Only merge if df still has columns to add
                    if not df.empty and len(df.columns) > 0:
                        data = data.merge(df, left_index=True, right_index=True, how="outer")

                logger.debug(f"  Data shape: {data.shape}")

            except Exception as e:
                logger.error(f"  Failed to pull {indicator}: {e}", exc_info=True)
                continue

        # Post-processing
        data = self._post_process_data(data)

        logger.info(f"Data pull complete. Final shape: {data.shape}")
        return data

    def _pull_acs_indicator(self, idx: int, row: pd.Series) -> pd.DataFrame:
        """
        Pull ACS data for a single indicator.

        Args:
            idx: Reference index
            row: Reference row with indicator definition

        Returns:
            DataFrame with ACS columns
        """
        # Parse numerator and denominator
        num = row["numerator"].split(",") if isinstance(row["numerator"], str) else []
        denom = row["denominator"]

        if isinstance(denom, str):
            denom = denom.split(",")
        else:
            denom = [denom] if denom != 1 else []

        # Combine and filter to ACS columns only
        cols = [c.strip() for c in num + denom]
        cols = [c for c in cols if len(str(c)) > 6]  # ACS columns are longer

        if not cols:
            logger.warning("  No ACS columns found")
            return pd.DataFrame()

        # Fetch data
        df = self.census.fetch_acs_data(cols, geography=self.geography)

        return df

    def _pull_cbp_indicator(self, idx: int, row: pd.Series) -> pd.DataFrame:
        """
        Pull CBP data for a single indicator.

        Args:
            idx: Reference index
            row: Reference row with indicator definition

        Returns:
            DataFrame with CBP establishment counts
        """
        # Numerator is NAICS code (integer)
        naics_code = int(row["numerator"])

        # Fetch data
        df = self.cbp.fetch_cbp_data(naics_code)

        return df

    def _pull_eavs_indicator(self, idx: int, row: pd.Series) -> pd.DataFrame:
        """
        Pull EAVS voter registration data.

        Args:
            idx: Reference index
            row: Reference row with indicator definition

        Returns:
            DataFrame with voter registration columns
        """
        # Parse columns needed
        num = row["numerator"].split(",") if isinstance(row["numerator"], str) else []
        denom = row["denominator"].split(",") if isinstance(row["denominator"], str) else []
        cols = [c.strip() for c in num + denom]

        # Get county reference for merging
        counties_ref = self.geographies.get("county")

        # Fetch data
        df = self.eavs.fetch_eavs_data(counties_ref=counties_ref)

        # Select only needed columns
        cols_available = [c for c in cols if c in df.columns]
        if cols_available:
            df = df[cols_available]

        return df

    def _pull_arda_indicator(self, idx: int, row: pd.Series) -> pd.DataFrame:
        """
        Pull ARDA religion census data.

        Args:
            idx: Reference index
            row: Reference row with indicator definition

        Returns:
            DataFrame with religion data
        """
        # Get year from reference or settings
        year = self.years.get("asarb", 2020)

        # Parse columns
        num = row["numerator"]
        denom = row["denominator"]

        # Fetch data (includes both POP{year} and generic POP column)
        df = self.arda.fetch_arda_data(year=year)

        # Determine which columns to include
        # Include both the year-specific POP column and generic POP for calculator compatibility
        cols = [num]
        if isinstance(denom, str) and denom.startswith("POP"):
            # Include both POP{year} and POP if reference says "POP"
            cols.append(f"POP{year}")
            if denom == "POP" and "POP" in df.columns:
                cols.append("POP")
        else:
            cols.append(denom)

        # Select only needed columns that exist
        cols_available = [c for c in cols if c in df.columns]
        if cols_available:
            df = df[cols_available]

        return df

    def _pull_pop_indicator(self, idx: int, row: pd.Series) -> pd.DataFrame:
        """
        Pull population migration data.

        Args:
            idx: Reference index
            row: Reference row with indicator definition

        Returns:
            DataFrame with migration columns
        """
        # Get years to fetch (last 5 years by default)
        year_pop = self.years.get("pop", 2020)
        years = list(range(year_pop, year_pop - 5, -1))

        # Fetch data
        df = self.pop.fetch_pop_data(years=years)

        return df

    def _post_process_data(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Post-process pulled data.

        - Drop state-level rows (if geography is county/tract)
        - Fill CBP missing values with 0
        - Handle Puerto Rico Limited English issue
        - Remove invalid indices

        Args:
            data: Raw pulled data

        Returns:
            Cleaned DataFrame
        """
        logger.info("Post-processing data")

        # Remove invalid indices (NaN). These are outer-merge artifacts: when
        # one source has data for geographies the others don't, pandas pads
        # the joined frame with NaN-indexed rows. Expected for any multi-source
        # pull — the count typically lands near the orphan-geo count of the
        # smallest source. Final shape is what matters.
        idx_issues = pd.isna(data.index)
        n_dropped = int(idx_issues.sum())
        if n_dropped > 0:
            n_total = len(data)
            n_kept = n_total - n_dropped
            pct_dropped = (n_dropped / n_total) * 100
            # Threshold: 60%. A normal county pull lands around 51% (3496/6780),
            # so 60% leaves headroom for tract/state variation while still
            # escalating on a genuine regression (e.g. a corrupted geography
            # file producing 90% NaN-indexed rows). Keep at INFO at minimum
            # so a future regression is not silently demoted to DEBUG.
            log_fn = logger.warning if pct_dropped > 60 else logger.info
            log_fn(
                f"  Cleaning merge artifacts: dropped {n_dropped} NaN-indexed rows "
                f"({pct_dropped:.1f}%), keeping {n_kept} valid rows. "
                f"Outer-merge artifact from per-source data pulls — these are rows "
                f"from one source that have no matching key in any other source."
            )
            data = data.loc[~idx_issues, :].copy()

        # Fill CBP missing values with 0
        cbp_cols = self.reference.loc[self.reference["Source"] == "CBP", "numerator"]
        cbp_cols = [str(int(c)) for c in cbp_cols if pd.notna(c)]
        cbp_cols_in_data = [c for c in cbp_cols if c in data.columns]

        if cbp_cols_in_data:
            n_filled = data[cbp_cols_in_data].isna().sum().sum()
            logger.info(f"  Filling {n_filled} CBP missing values with 0")
            data[cbp_cols_in_data] = data[cbp_cols_in_data].fillna(0)

        # Puerto Rico Limited English issue
        # (PR uses Spanish, so Limited English should be null)
        if self.geography in ["state", "county", "tract"]:
            geo_ref = self.geographies.get(self.geography)
            if geo_ref is not None:
                idx_PR = geo_ref.loc[geo_ref["state"] == 72, :].index
                if len(idx_PR) > 0:
                    # Find Limited English column
                    le_indicators = self.reference.loc[
                        self.reference["Indicator"] == "Limited English", "numerator"
                    ]
                    if len(le_indicators) > 0:
                        col_LE = le_indicators.iloc[0]
                        if col_LE in data.columns:
                            logger.info(f"  Setting {len(idx_PR)} PR Limited English values to NaN")
                            data.loc[idx_PR, col_LE] = pd.NA

        logger.info(f"  Post-processing complete. Shape: {data.shape}")

        return data

    def save_to_excel(self, data: pd.DataFrame, filename: Optional[str] = None):
        """
        Save pulled data to Excel (for debugging/validation).

        Args:
            data: DataFrame to save
            filename: Output filename (defaults to geography-based name)
        """
        if filename is None:
            filename = f"cria_inputs_{self.geography}.xlsx"

        output_path = paths.get_output_file(filename)

        logger.info(f"Saving data to: {output_path}")

        # Add labels row at top (if available)
        # TODO: Implement label row from reference

        data.to_excel(output_path)

        logger.info(f"  Saved {data.shape[0]} rows, {data.shape[1]} columns")

    def save_to_database(
        self,
        data: pd.DataFrame,
        year: int,
        db: Optional[Session] = None
    ):
        """
        Save source data to database.

        Args:
            data: Source data DataFrame (indexed by GEO_ID)
            year: Data year
            db: Optional database session (uses self.db if not provided)

        Note:
            This stores the raw source data (before indicator calculation).
            Each column value is stored as a separate SourceData record.
        """
        db = db or self.db

        if db is None:
            logger.warning("No database session provided, skipping database save")
            return

        logger.info(f"Saving source data to database (year={year})")

        # Get repositories
        geo_repo = GeographyRepository(db)
        ref_repo = ReferenceIndicatorRepository(db)
        source_repo = SourceDataRepository(db)

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
                "Cannot persist source_data: indicator_map is empty "
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
        if not geo_id_map and len(data.index) > 0:
            raise RuntimeError(
                f"Cannot persist source_data: geo_id_map is empty for level='{self.geography}' "
                "(no geographies in database for this level). "
                f"Run `poetry run python scripts/sync_geographies.py --level {self.geography}` "
                "to populate, then re-run."
            )

        # Process each row (geography)
        source_data_records = []
        processed_geos = 0
        skipped_geos = 0

        for geo_id in data.index:
            # Fast dictionary lookup instead of database query
            db_geo_id = geo_id_map.get(str(geo_id))
            if db_geo_id is None:
                skipped_geos += 1
                continue

            # Process each column (source data field)
            for col in data.columns:
                value = data.loc[geo_id, col]

                # Skip NaN values
                if pd.isna(value):
                    continue

                # Find which indicator this column belongs to
                # (match against numerator/denominator in reference)
                indicator_id = self._find_indicator_for_column(col, indicator_map)

                if indicator_id is None:
                    # Column doesn't match any indicator
                    continue

                source_data_records.append({
                    "geography_id": db_geo_id,
                    "indicator_id": indicator_id,
                    "column_name": col,
                    "value": float(value),
                    "year": year,
                    "is_imputed": False
                })

            processed_geos += 1

            # Log progress every 10000 geographies for large datasets
            if processed_geos % 10000 == 0:
                logger.info(f"  Processed {processed_geos} geographies...")

        # Bulk insert all source data using SQLAlchemy Core (fast!)
        if source_data_records:
            logger.info(f"Bulk inserting {len(source_data_records)} source data records...")
            num_inserted = source_repo.bulk_create(source_data_records)
            db.commit()
            logger.info(f"✓ Saved {num_inserted} source data records")
        else:
            logger.warning("No source data records to save")

        if skipped_geos > 0:
            logger.warning(f"Skipped {skipped_geos} geographies not found in database")

    def _find_indicator_for_column(
        self,
        column: str,
        indicator_map: Dict[str, int]
    ) -> Optional[int]:
        """
        Find which indicator a column belongs to.

        Args:
            column: Column name (e.g., "B17001_002E", "622110", "NETMIG2020")
            indicator_map: Dict mapping indicator names to database IDs

        Returns:
            Indicator ID or None if not found
        """
        # Check each indicator in reference
        for _, row in self.reference.iterrows():
            indicator_name = row["Indicator"]

            # Check if column is in numerator
            if pd.notna(row["numerator"]):
                numerator = str(row["numerator"])
                num_cols = [c.strip() for c in numerator.split(",")]
                if column in num_cols or column.startswith(tuple(num_cols)):
                    return indicator_map.get(indicator_name)

            # Check if column is in denominator
            if pd.notna(row["denominator"]) and isinstance(row["denominator"], str):
                denominator = str(row["denominator"])
                denom_cols = [c.strip() for c in denominator.split(",")]
                if column in denom_cols or column.startswith(tuple(denom_cols)):
                    return indicator_map.get(indicator_name)

        return None

    def __repr__(self) -> str:
        """String representation."""
        return f"DataPuller(geography={self.geography})"
