"""
Binning Engine for CRIA indicators.

This module provides a clean OOP wrapper around mapclassify for consistent
binning of indicators into classes (typically 5 or 7 bins).
"""

from typing import Dict, List, Optional, Union
import numpy as np
import pandas as pd
import mapclassify as mc
from src.utils.logger import logger


# Manual bin boundaries from deprecated cria_functions.py:fit_manual().
# These encode domain knowledge about how specific columns should be binned,
# bypassing auto-select. Keys are column names as they appear in indicator
# DataFrames (indicator-level) or aggregate DataFrames (aggregate-level).
# Source: deprecated/old_scripts/cria_functions.py lines 138-291
MANUAL_BINS = {
    # Indicator-level
    "Median Income": {
        5: {"boundaries": [25000, 50000, 75000, 100000], "reverse": False},
        7: {"boundaries": [20000, 40000, 60000, 80000, 100000, 120000], "reverse": False},
    },
    # Aggregate-level
    "agg": {
        5: {"boundaries": [-0.75, -0.25, 0.25, 0.75], "reverse": True},
        7: {"boundaries": [-1.25, -0.75, -0.25, 0.25, 0.75, 1.25], "reverse": True},
    },
    "cri": {
        5: {"boundaries": [0.1, 0.3, 0.7, 0.9], "reverse": False},
        7: {"boundaries": [0.05, 0.15, 0.3, 0.7, 0.85, 0.95], "reverse": False},
    },
    "cria_p": {
        5: {"boundaries": [0.1, 0.3, 0.7, 0.9], "reverse": False},
        7: {"boundaries": [0.05, 0.15, 0.3, 0.7, 0.85, 0.95], "reverse": False},
    },
    "pop change": {
        5: {"boundaries": [0.1, 0.25, 0.85, 1.5], "reverse": False},
        7: {"boundaries": [0.05, 0.15, 0.3, 0.9, 1.3, 2.25], "reverse": False},
    },
    "pop_p": {
        5: {"boundaries": [0.1, 0.3, 0.7, 0.9], "reverse": False},
        7: {"boundaries": [0.05, 0.15, 0.3, 0.7, 0.85, 0.95], "reverse": False},
    },
}


class BinningEngine:
    """
    Wrapper around mapclassify for consistent binning of CRIA indicators.

    Supports multiple binning strategies with automatic handling of edge cases
    like HeadTail Breaks producing too many bins.
    """

    def __init__(self, strategy: str = "quantiles", k: int = 5):
        """
        Initialize BinningEngine.

        Args:
            strategy: Binning strategy to use. Options:
                - "quantiles": Equal count bins (default)
                - "equal_interval": Equal width bins
                - "natural_breaks": Jenks natural breaks
                - "fisher_jenks": Fisher-Jenks algorithm
                - "maximum_breaks": Maximum breaks
                - "std_mean": Standard deviation mean
                - "auto": Automatically select best method
            k: Number of bins to create (default: 5)
        """
        self.strategy = strategy
        self.k = k

        # Store method selection metadata keyed by series name
        self._last_fit_results: Dict[str, Dict] = {}

        # Map strategy names to mapclassify methods
        self._strategy_map = {
            "quantiles": mc.Quantiles,
            "equal_interval": mc.EqualInterval,
            "natural_breaks": mc.NaturalBreaks,
            "fisher_jenks": mc.FisherJenks,
            "jenks_caspall": mc.JenksCaspall,
            "maximum_breaks": mc.MaximumBreaks,
            "std_mean": mc.StdMean,
            "headtail_breaks": mc.HeadTailBreaks,
        }

        # Methods that accept k parameter
        self._methods_with_k = [
            "quantiles", "equal_interval", "fisher_jenks",
            "jenks_caspall", "maximum_breaks", "natural_breaks"
        ]

    def bin_series(
        self,
        series: pd.Series,
        strategy: Optional[str] = None,
        k: Optional[int] = None,
        exceptions: Optional[List[str]] = None
    ) -> pd.Series:
        """
        Bin a single series into k classes.

        Args:
            series: Series to bin (numeric values)
            strategy: Override default strategy (optional)
            k: Override default k (optional)
            exceptions: List of methods to exclude (e.g., ["jenks_caspall"])

        Returns:
            Series with integer bin assignments (1-indexed: 1, 2, 3, ..., k)

        Example:
            >>> engine = BinningEngine(strategy="quantiles", k=5)
            >>> series = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
            >>> bins = engine.bin_series(series)
            >>> bins
            0    1
            1    1
            2    2
            ...
        """
        strategy = strategy or self.strategy
        k = k or self.k
        exceptions = exceptions or []

        # Clean series - remove NaN values for binning
        clean_ser = series.dropna()

        if len(clean_ser) == 0:
            logger.warning(f"Series '{series.name}' has no valid values")
            return pd.Series(np.nan, index=series.index, dtype=float)

        if len(clean_ser) < k:
            logger.warning(
                f"Series '{series.name}' has fewer values ({len(clean_ser)}) "
                f"than bins ({k}). Using {len(clean_ser)} bins instead."
            )
            k = len(clean_ser)

        # Check for manual bin configuration before auto-select
        manual_config = MANUAL_BINS.get(series.name)
        if manual_config and k in manual_config:
            result = self._apply_manual_bins(series, clean_ser, k, manual_config[k])
            return result

        # Auto-select best method if strategy is "auto"
        if strategy == "auto":
            binned = self._auto_select_method(clean_ser, k, exceptions)
        else:
            # Use specified method
            binned = self._apply_method(clean_ser, strategy, k)

            # Record method info for non-auto strategies
            self._last_fit_results[series.name] = {
                "selected_method": strategy,
                "selection_type": "direct",
                "selected_score": np.nan,
                "all_scores": {},
            }

        # Handle HeadTail Breaks producing too many bins
        # Check both direct strategy and auto-selected method
        selected = self._last_fit_results.get(series.name, {}).get("selected_method")
        if selected == "headtail_breaks" or strategy == "headtail_breaks":
            binned = np.where(binned >= k, k - 1, binned)

        # Create result series with same index as original (NaN where missing)
        result = pd.Series(np.nan, index=series.index, dtype=float)
        result.loc[clean_ser.index] = binned + 1  # Convert to 1-indexed

        return result

    def bin_dataframe(
        self,
        df: pd.DataFrame,
        strategy: Optional[str] = None,
        k: Optional[int] = None,
        exceptions_dict: Optional[Dict[str, List[str]]] = None,
        suffix: str = "_bins"
    ) -> pd.DataFrame:
        """
        Bin all columns in a DataFrame.

        Args:
            df: DataFrame with numeric columns to bin
            strategy: Override default strategy (optional)
            k: Override default k (optional)
            exceptions_dict: Dict mapping column names to excluded methods
                Example: {"Civil Org": ["jenks_caspall"], "Hospitals": ["jenks_caspall"]}
            suffix: Suffix to add to binned column names (default: "_bins")

        Returns:
            DataFrame with binned columns (original columns + binned columns)

        Example:
            >>> df = pd.DataFrame({"poverty": [0.1, 0.2, 0.3], "gini": [0.4, 0.5, 0.6]})
            >>> binned_df = engine.bin_dataframe(df)
            >>> binned_df.columns
            Index(['poverty', 'gini', 'poverty_bins', 'gini_bins'])
        """
        strategy = strategy or self.strategy
        k = k or self.k
        exceptions_dict = exceptions_dict or {}

        # Clear stale metadata from previous runs
        self._last_fit_results = {}

        result = df.copy()

        for col in df.columns:
            exceptions = exceptions_dict.get(col, [])

            logger.debug(f"Binning column: {col}")
            binned = self.bin_series(
                df[col],
                strategy=strategy,
                k=k,
                exceptions=exceptions
            )
            result[f"{col}{suffix}"] = binned

        return result

    def get_bin_edges(
        self,
        series: pd.Series,
        strategy: Optional[str] = None,
        k: Optional[int] = None
    ) -> List[float]:
        """
        Get bin edge values for a series.

        Args:
            series: Series to bin
            strategy: Override default strategy (optional)
            k: Override default k (optional)

        Returns:
            List of bin edge values

        Example:
            >>> edges = engine.get_bin_edges(series)
            >>> edges
            [0.0, 2.5, 5.0, 7.5, 10.0]
        """
        strategy = strategy or self.strategy
        k = k or self.k

        clean_ser = series.dropna()

        if len(clean_ser) < k:
            k = len(clean_ser)

        classifier = self._apply_method(clean_ser, strategy, k, return_classifier=True)

        return list(classifier.bins)

    def get_bin_counts(
        self,
        series: pd.Series,
        strategy: Optional[str] = None,
        k: Optional[int] = None
    ) -> Dict[int, int]:
        """
        Get count of values in each bin.

        Args:
            series: Series to bin
            strategy: Override default strategy (optional)
            k: Override default k (optional)

        Returns:
            Dictionary mapping bin number to count

        Example:
            >>> counts = engine.get_bin_counts(series)
            >>> counts
            {1: 20, 2: 18, 3: 22, 4: 19, 5: 21}
        """
        binned = self.bin_series(series, strategy, k)
        counts = binned.value_counts().sort_index()
        return counts.to_dict()

    def _apply_method(
        self,
        series: pd.Series,
        strategy: str,
        k: int,
        return_classifier: bool = False
    ) -> Union[np.ndarray, mc.Quantiles]:
        """
        Apply a specific binning method.

        Args:
            series: Series to bin
            strategy: Binning strategy
            k: Number of bins
            return_classifier: If True, return classifier object instead of bins

        Returns:
            Array of bin assignments or classifier object
        """
        if strategy not in self._strategy_map:
            logger.warning(
                f"Unknown strategy '{strategy}', falling back to 'quantiles'"
            )
            strategy = "quantiles"

        method_class = self._strategy_map[strategy]

        try:
            if strategy in self._methods_with_k:
                classifier = method_class(series.values, k=k)
            else:
                classifier = method_class(y=series.values)

            if return_classifier:
                return classifier
            else:
                return classifier.yb

        except Exception as e:
            logger.error(f"Error applying {strategy}: {e}")
            logger.info("Falling back to quantiles")
            classifier = mc.Quantiles(series.values, k=k)

            if return_classifier:
                return classifier
            else:
                return classifier.yb

    def _apply_manual_bins(
        self,
        series: pd.Series,
        clean_ser: pd.Series,
        k: int,
        config: Dict,
    ) -> pd.Series:
        """
        Apply manual bin boundaries using pd.cut().

        Replicates deprecated/old_scripts/cria_functions.py:fit_manual().
        These boundaries encode domain knowledge about specific columns
        that should not use statistical auto-selection.

        Args:
            series: Original series (with NaN values)
            clean_ser: Series with NaN removed
            k: Number of bins
            config: Dict with "boundaries" (list of inner edges) and
                "reverse" (bool for label reversal)

        Returns:
            Series with 1-indexed bin assignments
        """
        boundaries = [-np.inf] + list(config["boundaries"]) + [np.inf]
        reverse = config["reverse"]

        if reverse:
            labels = list(range(1, k + 1))[::-1]
        else:
            labels = list(range(1, k + 1))

        # pd.cut returns Categorical; convert to float for consistency
        cut_result = pd.cut(
            clean_ser, bins=boundaries, labels=labels
        ).astype(float)

        # Build result with NaN preserved at original positions
        result = pd.Series(np.nan, index=series.index, dtype=float)
        result.loc[clean_ser.index] = cut_result.values

        # Record metadata
        self._last_fit_results[series.name] = {
            "selected_method": "manual",
            "selection_type": "manual",
            "selected_score": np.nan,
            "all_scores": {},
        }

        logger.debug(
            f"Applied manual bins for '{series.name}': "
            f"boundaries={config['boundaries']}, reverse={reverse}"
        )

        return result

    def _auto_select_method(
        self,
        series: pd.Series,
        k: int,
        exceptions: List[str]
    ) -> np.ndarray:
        """
        Automatically select best binning method based on goodness-of-fit.

        Replicates the original fit_data() scoring approach:
        1. Try all candidate methods, collect ADCM and TSS for each
        2. Center-scale (z-score) ADCM and TSS across methods
        3. Combine: score = (z_ADCM + z_TSS) / 2 (lower is better)
        4. Pick the method with the lowest combined z-score

        This center-scaling is critical — it normalizes each metric relative
        to how all methods performed, preventing any single method from
        dominating purely due to raw score magnitude.

        Args:
            series: Series to bin
            k: Number of bins
            exceptions: Methods to exclude

        Returns:
            Array of bin assignments
        """
        # Methods to try for auto-selection — matches original fit_by_method()
        # NOTE: jenks_caspall excluded (can hang on data with many duplicates)
        # NOTE: natural_breaks excluded (non-deterministic)
        # NOTE: percentiles excluded (always zero scores in original code)
        methods_to_try = [
            "equal_interval", "fisher_jenks", "headtail_breaks",
            "maximum_breaks", "quantiles", "std_mean"
        ]

        # Remove user-specified excluded methods
        methods_to_try = [m for m in methods_to_try if m not in exceptions]

        fit_results = {}

        for method in methods_to_try:
            try:
                classifier = self._apply_method(
                    series, method, k, return_classifier=True
                )

                fit_results[method] = {
                    "adcm": classifier.adcm,
                    "tss": classifier.tss,
                    "classifier": classifier
                }

            except Exception as e:
                logger.debug(f"Method {method} failed: {e}")
                continue

        if not fit_results:
            logger.warning("All methods failed, using quantiles")
            self._last_fit_results[series.name] = {
                "selected_method": "quantiles",
                "selection_type": "fallback",
                "selected_score": np.nan,
                "all_scores": {},
            }
            return self._apply_method(series, "quantiles", k)

        # Center-scale ADCM and TSS across methods (replicates old center_scale)
        methods = list(fit_results.keys())
        adcm_vals = np.array([fit_results[m]["adcm"] for m in methods])
        tss_vals = np.array([fit_results[m]["tss"] for m in methods])

        adcm_z = self._center_scale(adcm_vals)
        tss_z = self._center_scale(tss_vals)

        # Combined score: lower is better (same as old code)
        combined_scores = (adcm_z + tss_z) / 2

        # Exclude methods that had near-zero raw scores (failed fits)
        # Original code: exclude where sum of ADCM+GADF+TSS <= 0.005
        for i, method in enumerate(methods):
            raw_sum = (fit_results[method]["adcm"]
                       + fit_results[method]["tss"])
            if raw_sum <= 0.005:
                combined_scores[i] = np.inf

        # Find best method (lowest combined z-score)
        best_idx = np.argmin(combined_scores)
        best_method = methods[best_idx]
        best_score = combined_scores[best_idx]

        # Build all_scores dict for metadata
        all_scores = {
            methods[i]: float(combined_scores[i])
            for i in range(len(methods))
        }

        # Store fit results for later retrieval
        self._last_fit_results[series.name] = {
            "selected_method": best_method,
            "selection_type": "auto",
            "selected_score": float(best_score),
            "all_scores": all_scores,
        }

        logger.debug(f"Auto-selected method: {best_method} (score: {best_score:.4f})")
        return fit_results[best_method]["classifier"].yb

    @staticmethod
    def _center_scale(values: np.ndarray) -> np.ndarray:
        """
        Center-scale (z-score) an array of values.

        Replicates the original center_scale() function:
            out = ser - ser.mean(axis=0)
            out = out / ser.std(axis=0)

        Note: Uses ddof=0 (population std) to match the original pandas
        Series.std(axis=0) behavior when called on a DataFrame column.

        Args:
            values: Array of numeric values

        Returns:
            Z-scored array (mean=0, std=1). Returns zeros if std is 0.
        """
        mean = np.mean(values)
        std = np.std(values, ddof=0)
        if std == 0:
            return np.zeros_like(values)
        return (values - mean) / std

    def get_selection_metadata(self, column_name: str) -> Optional[Dict]:
        """
        Get stored method selection metadata for a given column.

        Args:
            column_name: Name of the column/series that was binned

        Returns:
            Dictionary with keys:
                - selected_method: Name of the method used
                - selection_type: "auto", "direct", "manual", or "fallback"
                - selected_score: Combined ADCM+TSS score (NaN for non-auto)
                - all_scores: Dict of method -> score (empty for non-auto)
            Returns None if no metadata stored for the column.
        """
        return self._last_fit_results.get(column_name)

    def get_metadata(
        self,
        series: pd.Series,
        strategy: Optional[str] = None,
        k: Optional[int] = None
    ) -> pd.DataFrame:
        """
        Get detailed metadata about binning results.

        Args:
            series: Series to bin
            strategy: Override default strategy (optional)
            k: Override default k (optional)

        Returns:
            DataFrame with metadata:
                - bin edges
                - bin counts
                - bin means
                - bin medians
        """
        strategy = strategy or self.strategy
        k = k or self.k

        binned = self.bin_series(series, strategy, k)
        clean_ser = series.dropna()

        metadata = []

        for bin_num in sorted(binned.unique()):
            if pd.isna(bin_num):
                continue

            bin_values = clean_ser[binned == bin_num]

            metadata.append({
                "bin": int(bin_num),
                "count": len(bin_values),
                "min": bin_values.min(),
                "max": bin_values.max(),
                "mean": bin_values.mean(),
                "median": bin_values.median()
            })

        meta_df = pd.DataFrame(metadata)

        # Enrich with method selection metadata if available
        selection = self._last_fit_results.get(series.name)
        if selection:
            meta_df["selected_method"] = selection["selected_method"]
            meta_df["selected_score"] = selection["selected_score"]
        else:
            meta_df["selected_method"] = np.nan
            meta_df["selected_score"] = np.nan

        return meta_df
