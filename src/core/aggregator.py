"""
Aggregation Engine for CRIA final scores.

This module creates final Community Resilience Indicator Analysis (CRIA)
aggregate scores from individual indicators.
"""

from typing import Dict, Optional, List, Tuple
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session
from src.core.binning import BinningEngine
from src.core.transformations import clean_series, calc_z_scores, calc_full_corr_matrix
from src.utils.logger import logger
from src.db.repositories import (
    GeographyRepository, AggregateIndicatorRepository
)


class AggregateIndicator:
    """
    Create final CRIA aggregate scores from binned indicators.

    Pipeline:
    1. Clean indicators (handle missing, outliers)
    2. Rescale indicators (0-1 to 0-100 for fractions/indexes)
    3. Reorient (reverse polarity if needed)
    4. Standardize (z-scores)
    5. Bin into classes (1-5 or 1-7)
    6. Aggregate (weighted or simple average)
    """

    def __init__(
        self,
        geography: str = "county",
        bins: int = 5,
        binning_strategy: str = "auto",
        db: Optional[Session] = None
    ):
        """
        Initialize AggregateIndicator.

        Args:
            geography: Geography level ("county", "tract", "tribal", "state")
            bins: Number of bins for classification (default: 5)
            binning_strategy: Strategy for binning ("auto", "quantiles", etc.)
            db: Optional database session for storing aggregates
        """
        self.geography = geography
        self.bins = bins
        self.binning_strategy = binning_strategy
        self.db = db

        # Initialize binning engine
        self.binning_engine = BinningEngine(
            strategy=binning_strategy,
            k=bins
        )

        if db is not None:
            logger.info("Database session provided - will store aggregates")

    def create_aggregate(
        self,
        indicators: pd.DataFrame,
        reference: pd.DataFrame,
        geo_reference: Optional[pd.DataFrame] = None,
        bin_indicators: bool = True,
        weights: Optional[Dict[str, float]] = None,
        exceptions: Optional[Dict[str, List[str]]] = None,
        skip_aggregation: bool = False,
    ) -> Dict[str, pd.DataFrame]:
        """
        Create aggregate CRIA indicator.

        Args:
            indicators: DataFrame with calculated indicators
            reference: Reference DataFrame with indicator metadata
            geo_reference: Geography reference DataFrame (optional)
            bin_indicators: Whether to bin indicators (default: True)
            weights: Optional weights for indicators (default: equal weights)
            exceptions: Dict of binning exceptions for specific indicators
            skip_aggregation: If True, skip z-scores/aggregation/CRCI and return
                binning-only results. Used for tribal geography which has no
                aggregate score. Uses impute=False for cleaning to match
                deprecated behavior.

        Returns:
            Dictionary containing (full aggregation):
                - "indicators": Original indicators (cleaned)
                - "pos": Reoriented indicators (positive = resilience)
                - "scores": Standardized z-scores
                - "scores_percentiles": Percentile ranks
                - "lowest_ind": Top 3 lowest resilience indicators per geography
                - "agg": Aggregate DataFrame with final scores
                - "bin_labels": Binned indicator labels (if bin_indicators=True)
                - "bin_meta": Binning metadata (if bin_indicators=True)
                - "agg_labels": Binned aggregate labels
                - "agg_meta": Aggregate binning metadata
                - "corr": Correlation matrix (Pearson r) if correlation computed
                - "p": Correlation p-values if correlation computed
                - "zero": Significance flags (1=significant) if correlation computed
                - "n": Pairwise sample sizes if correlation computed

            Dictionary containing (skip_aggregation=True):
                - "indicators": Original indicators (cleaned, impute=False)
                - "bin_labels": Binned indicator labels
                - "bin_meta": Binning metadata

        Example:
            >>> aggregator = AggregateIndicator(geography="county")
            >>> results = aggregator.create_aggregate(indicators, reference)
            >>> print(results["agg"]["cria_p"].describe())
        """
        logger.info(f"Creating aggregate indicator for {self.geography} level")

        exceptions = exceptions or {}

        # Step 1: Clean indicators
        # When skipping aggregation (tribal), use impute=False to match
        # deprecated/old_scripts/cria_create_indicators_tribal.py:100
        impute = not skip_aggregation
        logger.debug(f"Step 1: Cleaning indicators (impute={impute})")
        df_clean = self._clean_indicators(
            indicators, reference, geo_reference, impute=impute
        )

        # Create display copy WITHOUT imputation so indicators tab shows NaN
        # (gray on map) instead of mean-imputed values. The aggregation
        # pipeline continues to use df_clean (imputed) for CRCI calculation.
        if impute:
            df_display = self._clean_indicators(
                indicators, reference, geo_reference, impute=False
            )
        else:
            df_display = df_clean

        # Step 2: Rescale indicators (0-1 to 0-100 for fractions)
        logger.debug("Step 2: Rescaling indicators")
        df_scale = self._rescale_indicators(df_clean, reference)

        # Step 3: Bin individual indicators (optional)
        if bin_indicators:
            logger.debug("Step 3: Binning indicators")
            bin_results = self._bin_indicators(
                df_scale, reference, exceptions
            )
            bin_labels = bin_results["bins"]
            bin_meta = bin_results["meta"]
        else:
            bin_labels = pd.DataFrame()
            bin_meta = pd.DataFrame()

        # Skip aggregation for tribal — return binning-only results
        if skip_aggregation:
            output = {
                "indicators": df_display,
                "bin_labels": bin_labels,
                "bin_meta": bin_meta,
            }
            logger.info(
                "Skipping aggregation (binning-only mode) — "
                f"{len(df_clean)} rows, {len(df_clean.columns)} indicators"
            )
            return output

        # Step 4: Reorient indicators (reverse polarity for negative indicators)
        logger.debug("Step 4: Reorienting indicators")
        df_pos = self._reorient_indicators(df_scale, reference)

        # Step 5: Calculate z-scores
        logger.debug("Step 5: Calculating z-scores")
        df_scores = self._calc_z_scores(df_pos)

        # Step 6: Calculate aggregate scores
        logger.debug("Step 6: Aggregating scores")
        df_agg = self._aggregate_scores(df_scores, reference, weights)

        # Step 7: Bin aggregate scores
        logger.debug("Step 7: Binning aggregate scores")
        agg_bin_results = self._bin_aggregate(df_agg, exceptions)

        # Step 8: Calculate percentile ranks
        logger.debug("Step 8: Calculating percentiles")
        df_scores_p = df_scores.rank(axis=0, pct=True)

        # Step 9: Identify lowest resilience indicators (top 3 drivers)
        logger.debug("Step 9: Computing lowest resilience indicators")
        lowest_ind = self._compute_lowest_indicators(df_scores)

        # Step 10: Compute correlation matrix
        logger.debug("Step 10: Computing correlation matrix")
        corr_r, corr_p, corr_zero, corr_n = self._compute_correlation(df_clean)

        # Prepare output
        output = {
            "indicators": df_display,
            "pos": df_pos,
            "scores": df_scores,
            "scores_percentiles": df_scores_p,
            "lowest_ind": lowest_ind,
            "agg": df_agg,
            "bin_labels": bin_labels,
            "bin_meta": bin_meta,
            "agg_labels": agg_bin_results["bins"],
            "agg_meta": agg_bin_results["meta"],
            "corr": corr_r,
            "p": corr_p,
            "zero": corr_zero,
            "n": corr_n,
        }

        logger.info("Aggregate indicator creation complete")
        return output

    def _clean_indicators(
        self,
        indicators: pd.DataFrame,
        reference: pd.DataFrame,
        geo_reference: Optional[pd.DataFrame] = None,
        impute: bool = True,
    ) -> pd.DataFrame:
        """
        Clean indicators (optionally impute missing values).

        Handles special cases:
        - Connecticut CBP data (2022): Zero values should be NaN
        - Puerto Rico Limited English: Spanish-speaking, so should be NaN

        Args:
            indicators: Raw indicators
            reference: Reference data
            geo_reference: Geography reference
            impute: Whether to impute NaN with column mean (default: True).
                Set to False for tribal to match deprecated behavior.

        Returns:
            Cleaned indicators DataFrame
        """
        df_clean = indicators.apply(clean_series, impute=impute)

        # Special case: Connecticut CBP issue
        if self.geography == "county" and geo_reference is not None:
            logger.debug("Handling Connecticut CBP special case")
            idx_ct = geo_reference[
                geo_reference["state_name"] == "Connecticut"
            ].index

            # Get CBP indicator names
            cbp_indicators = reference.loc[
                reference["Source"] == "CBP", "Indicator"
            ].tolist()

            # Set CT CBP values to NaN
            for indicator in cbp_indicators:
                if indicator in df_clean.columns:
                    df_clean.loc[idx_ct, indicator] = np.nan

        # Special case: Puerto Rico Limited English
        if self.geography in ["state", "county", "tract"] and geo_reference is not None:
            logger.debug("Handling Puerto Rico Limited English special case")

            # Find Puerto Rico rows (state code 72)
            idx_pr = geo_reference[geo_reference["state"] == 72].index

            if len(idx_pr) > 0 and "Limited English" in df_clean.columns:
                logger.info(
                    f"Setting {len(idx_pr)} Puerto Rico 'Limited English' "
                    "values to NaN"
                )
                df_clean.loc[idx_pr, "Limited English"] = np.nan

        return df_clean

    def _rescale_indicators(
        self,
        indicators: pd.DataFrame,
        reference: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Rescale indicators from 0-1 to 0-100 for fractions and indexes.

        Args:
            indicators: Cleaned indicators
            reference: Reference data with "Units" column

        Returns:
            Rescaled indicators DataFrame
        """
        df_scale = indicators.copy()

        # Find indicators that need rescaling (fractions and indexes)
        if "Units" in reference.columns:
            rescale_indicators = reference.loc[
                reference["Units"].isin(["index", "fraction"]), "Indicator"
            ].tolist()

            logger.debug(f"Rescaling {len(rescale_indicators)} indicators")

            for indicator in rescale_indicators:
                if indicator in df_scale.columns:
                    df_scale[indicator] = 100 * df_scale[indicator]

        return df_scale

    def _reorient_indicators(
        self,
        indicators: pd.DataFrame,
        reference: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Reorient indicators so higher values = higher resilience.

        For negative indicators (e.g., poverty, unemployment), reverse the scale.

        Args:
            indicators: Scaled indicators
            reference: Reference data with "Augment" column

        Returns:
            Reoriented indicators DataFrame
        """
        df_pos = indicators.copy()

        # Find indicators that need reversal
        if "Augment" in reference.columns:
            reverse_indicators = reference.loc[
                reference["Augment"] == "reverse", "Indicator"
            ].tolist()

            logger.debug(f"Reversing {len(reverse_indicators)} indicators")

            for indicator in reverse_indicators:
                if indicator in df_pos.columns:
                    df_pos[indicator] = 100 - df_pos[indicator]

        return df_pos

    def _calc_z_scores(self, indicators: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate standardized z-scores for indicators.

        Special handling for "Population Change" - use absolute deviation
        instead of standard centering.

        Args:
            indicators: Reoriented indicators

        Returns:
            Z-score DataFrame
        """
        df_scores = calc_z_scores(indicators)

        return df_scores

    def _compute_lowest_indicators(
        self,
        df_scores: pd.DataFrame,
        n: int = 3,
    ) -> pd.DataFrame:
        """
        Identify the n indicators with lowest z-scores per geography.

        Lower z-scores = worse resilience = top drivers of challenge.
        Replicates deprecated/old_scripts/cria_create_aggregate_indicator.py:140-167.

        Args:
            df_scores: Z-score DataFrame (geographies x indicators)
            n: Number of lowest indicators to identify (default: 3)

        Returns:
            DataFrame with columns: ind_1, ind_2, ind_3,
            ind_1_score, ind_2_score, ind_3_score, list_labels
        """
        # Cap n at available indicator count
        n = min(n, len(df_scores.columns))

        if len(df_scores) == 0 or n == 0:
            return pd.DataFrame()

        values = df_scores.values
        col_names = df_scores.columns.values

        # Find indices of n lowest z-scores per row
        idx_filter = np.argsort(values, axis=1)[:, :n]

        # Indicator names for each geography's worst performers
        df_names = pd.DataFrame(
            data=col_names[idx_filter],
            index=df_scores.index,
            columns=[f"ind_{i+1}" for i in range(n)],
        )

        # Z-score values for those indicators
        rows = []
        for row_idx, geo_id in enumerate(df_scores.index):
            cols = df_scores.columns[idx_filter[row_idx]]
            score_values = df_scores.loc[geo_id, cols].values
            row_data = {}
            for i in range(n):
                row_data[f"ind_{i+1}_score"] = score_values[i]
            row_data["list_labels"] = list(cols)
            rows.append(row_data)

        df_values = pd.DataFrame(rows, index=df_scores.index)

        result = pd.concat([df_names, df_values], axis=1)
        # Sort columns: ind_1, ind_1_score, ind_2, ind_2_score, ...
        sorted_cols = []
        for i in range(n):
            sorted_cols.extend([f"ind_{i+1}", f"ind_{i+1}_score"])
        sorted_cols.append("list_labels")
        result = result[sorted_cols]

        logger.debug(f"Computed lowest {n} indicators for {len(df_scores)} geographies")
        return result

    def _compute_correlation(
        self,
        indicators: pd.DataFrame,
        reference_path: Optional[str] = None,
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """
        Compute full correlation matrix with relabeling from reference data.

        Reads Label_Correlation and Order_Correlation from the reference Excel
        file to relabel and reorder indicators before computing correlations.
        Replicates deprecated/old_scripts/cria_create_aggregate_indicator.py:199-206.

        Args:
            indicators: Cleaned indicator DataFrame (imputed)
            reference_path: Path to reference Excel with correlation labels.
                Defaults to Paths.reference_data.

        Returns:
            Tuple of (corr_r, corr_p, corr_zero, corr_n) DataFrames
        """
        from src.config.paths import PathConfig

        df_corr = indicators.copy()

        # Read correlation labels/ordering from reference Excel
        if reference_path is None:
            ref_path = PathConfig().reference_file
        else:
            from pathlib import Path
            ref_path = Path(reference_path)
        if ref_path.exists():
            try:
                ref = pd.read_excel(ref_path, sheet_name="Status")

                # Relabel columns using Label_Correlation
                if "Label_Correlation" in ref.columns and "Indicator" in ref.columns:
                    label_map = dict(
                        zip(ref["Indicator"], ref["Label_Correlation"])
                    )
                    df_corr = df_corr.rename(columns=label_map)

                # Reorder by Order_Correlation
                if "Order_Correlation" in ref.columns:
                    order = ref.dropna(subset=["Order_Correlation"]).sort_values(
                        "Order_Correlation"
                    )
                    label_col = (
                        "Label_Correlation"
                        if "Label_Correlation" in ref.columns
                        else "Indicator"
                    )
                    seen = set()
                    ordered_cols = []
                    for c in order[label_col]:
                        if c in df_corr.columns and c not in seen:
                            ordered_cols.append(c)
                            seen.add(c)
                    if ordered_cols:
                        df_corr = df_corr[ordered_cols]

                logger.debug(
                    f"Relabeled correlation matrix: {len(df_corr.columns)} indicators"
                )
            except Exception as e:
                logger.warning(
                    f"Could not read correlation labels from {ref_path}: {e}. "
                    "Using original indicator names."
                )
        else:
            logger.debug(
                f"Reference file {ref_path} not found, using original names"
            )

        return calc_full_corr_matrix(df_corr)

    def _aggregate_scores(
        self,
        scores: pd.DataFrame,
        reference: pd.DataFrame,
        weights: Optional[Dict[str, float]] = None
    ) -> pd.DataFrame:
        """
        Aggregate z-scores into final CRIA scores.

        Special handling:
        - "Population Change": Convert to negative absolute value
        - Equal weights by default
        - CRI = -AGG (Community Resilience Index)

        Args:
            scores: Z-score DataFrame
            reference: Reference data
            weights: Optional weights (default: equal weights)

        Returns:
            Aggregate DataFrame with columns:
                - agg: Aggregate score (mean of z-scores)
                - cri: Community Resilience Index (-agg)
                - cria_p: Percentile rank of CRI
                - pop change: Absolute value of population change z-score
                - pop_p: Percentile rank of population change
        """
        df_agg = pd.DataFrame(index=scores.index)

        # Special handling for Population Change
        logger.info(
            "Converting standardized population change to negative "
            "absolute value"
        )
        scores_adj = scores.copy()

        if "Population Change" in scores_adj.columns:
            scores_adj["Population Change"] = -abs(scores_adj["Population Change"])

        # Get list of indicators from reference
        list_indicators = reference["Indicator"].tolist()

        # Filter to only indicators present in scores
        available_indicators = [
            ind for ind in list_indicators
            if ind in scores_adj.columns
        ]

        # Calculate aggregate (mean of z-scores)
        if weights is None:
            # Equal weights
            df_agg["agg"] = scores_adj[available_indicators].mean(axis="columns")
        else:
            # Weighted average
            weighted_sum = sum(
                scores_adj[ind] * weights.get(ind, 1.0)
                for ind in available_indicators
            )
            weight_total = sum(weights.get(ind, 1.0) for ind in available_indicators)
            df_agg["agg"] = weighted_sum / weight_total

        # Community Resilience Index (negative of aggregate)
        df_agg["cri"] = -df_agg["agg"]

        # Percentile rank
        df_agg["cria_p"] = df_agg["cri"].rank(axis=0, pct=True)

        # Population change (absolute value)
        if "Population Change" in scores.columns:
            df_agg["pop change"] = abs(scores["Population Change"])
            df_agg["pop_p"] = df_agg["pop change"].rank(axis=0, pct=True)

        return df_agg

    def _bin_indicators(
        self,
        indicators: pd.DataFrame,
        reference: pd.DataFrame,
        exceptions: Dict[str, List[str]]
    ) -> Dict[str, pd.DataFrame]:
        """
        Bin individual indicators into classes.

        Args:
            indicators: Scaled indicators
            reference: Reference data
            exceptions: Dict of binning exceptions

        Returns:
            Dictionary with "bins" and "meta" DataFrames
        """
        # Use binning engine
        bin_labels = self.binning_engine.bin_dataframe(
            indicators,
            k=self.bins,
            exceptions_dict=exceptions
        )

        # Capture method selection metadata before get_metadata() re-bins
        saved_selection = {
            col: self.binning_engine.get_selection_metadata(col)
            for col in indicators.columns
        }

        # Generate metadata for each indicator
        meta_list = []

        for col in indicators.columns:
            metadata = self.binning_engine.get_metadata(
                indicators[col],
                k=self.bins
            )
            metadata["indicator"] = col

            # Overwrite with the authoritative selection metadata from
            # bin_dataframe() (which used the correct exceptions)
            selection = saved_selection.get(col)
            if selection:
                metadata["selected_method"] = selection["selected_method"]
                metadata["selected_score"] = selection["selected_score"]

            meta_list.append(metadata)

        if meta_list:
            bin_meta = pd.concat(meta_list, ignore_index=True)
        else:
            bin_meta = pd.DataFrame()

        return {"bins": bin_labels, "meta": bin_meta}

    def _bin_aggregate(
        self,
        aggregate: pd.DataFrame,
        exceptions: Dict[str, List[str]]
    ) -> Dict[str, pd.DataFrame]:
        """
        Bin aggregate scores into classes.

        Args:
            aggregate: Aggregate scores DataFrame
            exceptions: Dict of binning exceptions

        Returns:
            Dictionary with "bins" and "meta" DataFrames
        """
        # Bin aggregate columns
        agg_labels = self.binning_engine.bin_dataframe(
            aggregate,
            k=self.bins,
            exceptions_dict=exceptions
        )

        # Capture method selection metadata before get_metadata() re-bins
        saved_selection = {
            col: self.binning_engine.get_selection_metadata(col)
            for col in aggregate.columns
        }

        # Generate metadata
        meta_list = []

        for col in aggregate.columns:
            metadata = self.binning_engine.get_metadata(
                aggregate[col],
                k=self.bins
            )
            metadata["indicator"] = col

            # Overwrite with the authoritative selection metadata from
            # bin_dataframe() (which used the correct exceptions)
            selection = saved_selection.get(col)
            if selection:
                metadata["selected_method"] = selection["selected_method"]
                metadata["selected_score"] = selection["selected_score"]

            meta_list.append(metadata)

        if meta_list:
            agg_meta = pd.concat(meta_list, ignore_index=True)
        else:
            agg_meta = pd.DataFrame()

        return {"bins": agg_labels, "meta": agg_meta}

    def save_to_database(
        self,
        results: Dict[str, pd.DataFrame],
        year: int,
        db: Optional[Session] = None
    ):
        """
        Save aggregate results to database.

        Args:
            results: Output from create_aggregate() containing 'agg' DataFrame
            year: Data year
            db: Optional database session (uses self.db if not provided)

        Note:
            Stores the final aggregate scores and bins from the 'agg' DataFrame.
            Uses upsert to handle duplicate entries.
        """
        db = db or self.db

        if db is None:
            logger.warning("No database session provided, skipping database save")
            return

        logger.info(f"Saving aggregate indicators to database (year={year})")

        # Get the aggregate DataFrame
        agg_df = results.get("agg")
        if agg_df is None or agg_df.empty:
            logger.warning("No aggregate data to save")
            return

        # Get repositories
        geo_repo = GeographyRepository(db)
        agg_repo = AggregateIndicatorRepository(db)

        # Get geo_id -> database id mapping in a single query (fast!)
        # This replaces 88k individual get_by_geo_id() calls with one query
        logger.info("  Loading geography ID mapping...")
        geo_id_map = geo_repo.get_geo_id_map(level=self.geography)
        logger.info(f"  Loaded {len(geo_id_map)} geography mappings")

        # Defense-in-depth: TOTAL miss (no geographies in DB for this level) is
        # a setup-state error, not a data issue — fail loudly so callers that
        # bypass scripts/run_full_pipeline.py preflight still see the problem.
        # Partial misses still warn-and-continue below (skipped_geos counter).
        # Note: aggregator has no indicator_map — writes are keyed only on
        # geography, so this is the only failure axis to guard.
        if not geo_id_map and len(agg_df.index) > 0:
            raise RuntimeError(
                f"Cannot persist aggregate_indicators: geo_id_map is empty for "
                f"level='{self.geography}' (no geographies in database for this level). "
                f"Run `poetry run python scripts/sync_geographies.py --level {self.geography}` "
                "to populate, then re-run."
            )

        # Process each geography
        aggregate_records = []
        processed_geos = 0
        skipped_geos = 0

        for geo_id in agg_df.index:
            # Fast dictionary lookup instead of database query
            db_geo_id = geo_id_map.get(str(geo_id))
            if db_geo_id is None:
                skipped_geos += 1
                continue

            # Extract aggregate data
            row = agg_df.loc[geo_id]

            # Build record
            record = {
                "geography_id": db_geo_id,
                "year": year,
            }

            # Add all available fields
            if "cria_p" in row:
                record["percentile"] = float(row["cria_p"]) if pd.notna(row["cria_p"]) else None
            if "cria_z" in row:
                record["z_score"] = float(row["cria_z"]) if pd.notna(row["cria_z"]) else None
            if "cria_score" in row:
                record["aggregate_score"] = float(row["cria_score"]) if pd.notna(row["cria_score"]) else None
            if "cria_bin" in row:
                record["bin_class"] = int(row["cria_bin"]) if pd.notna(row["cria_bin"]) else None

            # Optional: Add sub-scores if they exist
            if "economic_score" in row:
                record["economic_score"] = float(row["economic_score"]) if pd.notna(row["economic_score"]) else None
            if "social_score" in row:
                record["social_score"] = float(row["social_score"]) if pd.notna(row["social_score"]) else None
            if "infrastructure_score" in row:
                record["infrastructure_score"] = float(row["infrastructure_score"]) if pd.notna(row["infrastructure_score"]) else None

            # Add metadata about indicators
            if "num_indicators" in row:
                record["num_indicators_used"] = int(row["num_indicators"]) if pd.notna(row["num_indicators"]) else None

            aggregate_records.append(record)
            processed_geos += 1

            # Log progress every 10000 geographies for large datasets
            if processed_geos % 10000 == 0:
                logger.info(f"  Processed {processed_geos} geographies...")

        # Bulk insert aggregates using SQLAlchemy Core (fast!)
        if aggregate_records:
            logger.info(f"Bulk inserting {len(aggregate_records)} aggregate records...")
            num_inserted = agg_repo.bulk_create(aggregate_records)
            db.commit()

            logger.info(f"✓ Saved {len(aggregate_records)} aggregate records")
        else:
            logger.warning("No aggregate records to save")

        if skipped_geos > 0:
            logger.warning(f"Skipped {skipped_geos} geographies not found in database")

    def save_to_excel(
        self,
        results: Dict[str, pd.DataFrame],
        file_path: str,
        include_geo: bool = True,
        geo_reference: Optional[pd.DataFrame] = None,
        reference: Optional[pd.DataFrame] = None,
        years: Optional[Dict[str, int]] = None
    ):
        """
        Save aggregate results to Excel file.

        Args:
            results: Output from create_aggregate()
            file_path: Path to save Excel file
            include_geo: Include geography reference columns
            geo_reference: Geography reference DataFrame
            reference: Indicator reference DataFrame (for ref tab)
            years: Year configuration dict (for years tab)

        Example:
            >>> results = aggregator.create_aggregate(indicators, reference)
            >>> aggregator.save_to_excel(results, "output/cria_results_county.xlsx",
            ...     reference=calculator.reference, years=calculator.years)
        """
        from pathlib import Path

        file_path = Path(file_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # If geography reference provided, merge it
        if include_geo and geo_reference is not None:
            for key, df in results.items():
                if isinstance(df, pd.DataFrame) and df.index.name == "GEO_ID":
                    results[key] = df.merge(
                        geo_reference,
                        left_index=True,
                        right_index=True,
                        how="left"
                    )

        # Build ref DataFrame with year enrichment
        ref_df = None
        if reference is not None:
            ref_df = reference.copy()
            if years is not None and "Source" in ref_df.columns:
                source_year_map = {
                    "ACS": years.get("acs"),
                    "CBP": years.get("cbp"),
                    "EAVS": None,
                    "ARDA": None,
                    "POP": years.get("pop"),
                }
                ref_df["year"] = ref_df["Source"].map(source_year_map)

        # Build years DataFrame
        years_df = None
        if years is not None:
            years_df = pd.DataFrame(
                list(years.items()),
                columns=["source", "year"]
            )

        # Define explicit sheet ordering (ref and years first)
        ordered_sheets: List[tuple] = []

        if ref_df is not None:
            ordered_sheets.append(("ref", ref_df))
        if years_df is not None:
            ordered_sheets.append(("years", years_df))

        # Add result sheets in standard order
        sheet_order = [
            "indicators", "pos", "scores", "scores_percentiles",
            "lowest_ind", "agg", "bin_labels", "bin_meta",
            "agg_labels", "agg_meta", "corr", "p", "zero", "n"
        ]
        for sheet_name in sheet_order:
            if sheet_name in results:
                df = results[sheet_name]
                if isinstance(df, pd.DataFrame) and not df.empty:
                    ordered_sheets.append((sheet_name, df))

        # Add any remaining sheets not in the standard order
        for sheet_name, df in results.items():
            if sheet_name not in sheet_order:
                if isinstance(df, pd.DataFrame) and not df.empty:
                    ordered_sheets.append((sheet_name, df))

        # Write to Excel
        with pd.ExcelWriter(file_path, engine="xlsxwriter") as writer:
            for sheet_name, df in ordered_sheets:
                # Excel sheet names limited to 31 characters
                df.to_excel(writer, sheet_name=sheet_name[:31])

        logger.info(f"Saved aggregate results to {file_path}")

        # Auto-generate correlation report if correlation data present
        corr_keys = {"corr", "p", "zero", "n"}
        if corr_keys.issubset(results.keys()):
            self._save_correlation_report(results, file_path)

    def _save_correlation_report(
        self,
        results: Dict[str, pd.DataFrame],
        results_path: str,
    ):
        """
        Save formatted correlation report to data/output/reports/.

        Creates an Excel workbook with formatted tables (TableStyleMedium2)
        matching the deprecated output in data/output/reports/Correlation Matrix {GEO}.xlsx.
        Replicates deprecated/old_utils/utils_excel_tools.py:update_excel_workbook.

        Args:
            results: Output dict from create_aggregate() containing corr/p/zero/n
            results_path: Path to main results file (used to derive reports directory)
        """
        import string
        from pathlib import Path

        try:
            from openpyxl import Workbook
            from openpyxl.worksheet.table import Table, TableStyleInfo
            from openpyxl.utils.dataframe import dataframe_to_rows
        except ImportError:
            logger.warning("openpyxl not installed — skipping correlation report")
            return

        # Derive reports path from results file location
        output_dir = Path(results_path).parent
        reports_dir = output_dir / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)

        report_path = reports_dir / f"Correlation Matrix {self.geography.upper()}.xlsx"

        # Sheets to write (correlation data only)
        corr_sheets = {"corr": results["corr"], "p": results["p"],
                       "zero": results["zero"], "n": results["n"]}

        wb = Workbook()
        # Remove default sheet
        wb.remove(wb.active)

        alphabet = list(string.ascii_uppercase)

        for idx, (sheet_name, df) in enumerate(corr_sheets.items()):
            ws = wb.create_sheet(sheet_name)
            df_out = df.reset_index(drop=False)

            for row in dataframe_to_rows(df_out, index=False, header=True):
                ws.append(row)

            max_row, max_col = df_out.shape
            # Convert column number to Excel letter(s)
            col_num = max_col
            col_letters = []
            while col_num:
                col_num, rem = divmod(col_num - 1, 26)
                col_letters[:0] = alphabet[rem]
            final_cell = f"{''.join(col_letters)}{max_row + 1}"

            tab = Table(
                displayName=f"Table{idx + 1}",
                ref=f"A1:{final_cell}",
            )
            style = TableStyleInfo(
                name="TableStyleMedium2",
                showFirstColumn=False,
                showLastColumn=False,
                showRowStripes=True,
                showColumnStripes=False,
            )
            tab.tableStyleInfo = style

            # Auto-width first column
            col_a_width = max(len(str(cell.value)) for cell in ws["A"])
            ws.column_dimensions["A"].width = col_a_width + 2

            ws.add_table(tab)

        wb.save(str(report_path))
        logger.info(f"Saved correlation report to {report_path}")
