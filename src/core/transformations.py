"""
Data transformation utilities for CRIA.

Functions for:
- Data cleaning (remove invalid values, impute missing)
- Standardization (z-scores, center-scale)
- Statistical calculations (correlations, etc.)

Replaces utility functions from cria_functions.py.
"""

import pandas as pd
import numpy as np
import logging
from typing import Optional, Tuple, Union, List
from scipy.stats import pearsonr, norm

logger = logging.getLogger(__name__)


def clean_series(
    series: pd.Series,
    impute: bool = False,
    impute_value: Optional[float] = None,
) -> pd.Series:
    """
    Clean a data series by removing invalid values.

    Removes:
    - Excel error strings ("#DIV/0!", "#VALUE!", etc.)
    - Null representations ("null", "<Null>", "-")
    - Census missing codes ("-666666666")
    - Special CBP codes ("250,000+", "2,500-")

    Args:
        series: Series to clean
        impute: Whether to impute missing values (default: False)
        impute_value: Value to use for imputation (default: mean)

    Returns:
        Cleaned series

    Example:
        >>> ser = pd.Series([100, "#DIV/0!", 200, "-666666666", "null"])
        >>> clean = clean_series(ser, impute=True)
        >>> print(clean)
        0    100.0
        1    150.0  # imputed
        2    200.0
        3    150.0  # imputed
        4    150.0  # imputed
    """
    ser = series.copy(deep=True)

    # Replace invalid string values with None
    replacements = {
        "#DIV/0!": None,
        "#VALUE!": None,
        "<Null>": None,
        "null": None,
        "-": None,
        "-666666666": None,
        "250,000+": 250000,  # CBP top-coding
        "2,500-": 2500,  # CBP bottom-coding
    }

    for old_val, new_val in replacements.items():
        ser.loc[ser == old_val] = new_val

    # Convert to float
    ser = ser.astype(float)

    # Impute missing values
    if impute:
        if impute_value is None:
            impute_value = ser.mean()

        n_missing = ser.isna().sum()
        if n_missing > 0:
            logger.debug(f"  Imputing {n_missing} missing values with {impute_value:.2f}")
            ser.loc[ser.isna()] = impute_value

    return ser


def calc_z_scores(data: Union[pd.Series, pd.DataFrame], sub_index: List = None) -> Union[pd.Series, pd.DataFrame]:
    """
    Calculate z-scores (standardized values).

    z = (x - mean) / std

    Special handling for "Population Change" column - only divide by std, don't center.

    Args:
        data: Series or DataFrame to standardize
        sub_index: Optional subset of indices to calculate mean/std from

    Returns:
        Series or DataFrame of z-scores

    Example:
        >>> ser = pd.Series([100, 200, 300, 400, 500])
        >>> z = calc_z_scores(ser)
        >>> print(z.mean(), z.std())  # mean≈0, std≈1
    """
    if isinstance(data, pd.Series):
        # Single series
        mean = data.mean()
        std = data.std()

        if std == 0:
            logger.warning("Standard deviation is 0, returning zeros")
            return pd.Series(0, index=data.index)

        z_scores = (data - mean) / std
        return z_scores

    elif isinstance(data, pd.DataFrame):
        # DataFrame - standardize each column
        scores = data.copy(deep=True)
        features = list(scores.columns)

        # Special handling for Population Change
        has_pop_change = "Population Change" in features
        if has_pop_change:
            features.remove("Population Change")

        # Calculate means and stds (optionally on subset)
        if sub_index is not None and len(sub_index) > 0:
            means = scores.loc[sub_index, :].mean(axis=0)
            stds = scores.loc[sub_index, :].std(axis=0)
        else:
            means = scores.mean(axis=0)
            stds = scores.std(axis=0)

        # Standardize regular features (center and scale)
        for indicator in features:
            scores[indicator] = (scores[indicator] - means[indicator]) / stds[indicator]

        # Population Change: only scale, don't center
        if has_pop_change:
            scores["Population Change"] = scores["Population Change"] / stds["Population Change"]

        return scores

    else:
        raise TypeError(f"Expected Series or DataFrame, got {type(data)}")


def center_scale(series: pd.Series) -> pd.Series:
    """
    Center and scale a series (same as z-scores).

    Args:
        series: Series to transform

    Returns:
        Centered and scaled series
    """
    return calc_z_scores(series)


def normalize_to_range(
    series: pd.Series,
    min_val: float = 0.0,
    max_val: float = 1.0,
) -> pd.Series:
    """
    Normalize series to a specific range [min_val, max_val].

    Uses min-max scaling:
    normalized = (x - x_min) / (x_max - x_min) * (max_val - min_val) + min_val

    Args:
        series: Series to normalize
        min_val: Target minimum value (default: 0)
        max_val: Target maximum value (default: 1)

    Returns:
        Normalized series

    Example:
        >>> ser = pd.Series([10, 20, 30, 40, 50])
        >>> norm = normalize_to_range(ser, min_val=0, max_val=100)
        >>> print(norm.min(), norm.max())  # 0.0, 100.0
    """
    ser_min = series.min()
    ser_max = series.max()

    if ser_max == ser_min:
        logger.warning("All values are the same, returning min_val")
        return pd.Series(min_val, index=series.index)

    # Min-max scaling
    normalized = (series - ser_min) / (ser_max - ser_min)

    # Scale to target range
    normalized = normalized * (max_val - min_val) + min_val

    return normalized


def mult_round(x: float, base: int = 5) -> float:
    """
    Round to nearest multiple of base.

    Args:
        x: Value to round
        base: Base to round to (default: 5)

    Returns:
        Rounded value

    Example:
        >>> mult_round(23, base=5)
        25
        >>> mult_round(22, base=5)
        20
    """
    return base * round(x / base)


def calc_corr_matrix(
    df: pd.DataFrame,
    method: str = "pearson",
    min_periods: int = 10,
) -> pd.DataFrame:
    """
    Calculate correlation matrix for DataFrame.

    Args:
        df: DataFrame with numeric columns
        method: Correlation method ('pearson', 'spearman', 'kendall')
        min_periods: Minimum number of observations for valid correlation

    Returns:
        Correlation matrix

    Example:
        >>> df = pd.DataFrame({
        ...     'A': [1, 2, 3, 4, 5],
        ...     'B': [2, 4, 6, 8, 10],
        ...     'C': [5, 4, 3, 2, 1]
        ... })
        >>> corr = calc_corr_matrix(df)
        >>> print(corr.loc['A', 'B'])  # Perfect positive correlation
        1.0
    """
    logger.info(f"Calculating {method} correlation matrix")

    corr = df.corr(method=method, min_periods=min_periods)

    logger.debug(f"  Matrix shape: {corr.shape}")

    return corr


def calc_pairwise_correlation(
    series1: pd.Series,
    series2: pd.Series,
    method: str = "pearson",
) -> Tuple[float, float]:
    """
    Calculate correlation and p-value between two series.

    Args:
        series1: First series
        series2: Second series
        method: Correlation method (currently only 'pearson' supported)

    Returns:
        Tuple of (correlation, p_value)

    Example:
        >>> s1 = pd.Series([1, 2, 3, 4, 5])
        >>> s2 = pd.Series([2, 4, 6, 8, 10])
        >>> corr, p_val = calc_pairwise_correlation(s1, s2)
        >>> print(corr)  # 1.0 (perfect correlation)
    """
    # Remove NaN values (pairwise)
    valid_mask = series1.notna() & series2.notna()
    s1_valid = series1[valid_mask]
    s2_valid = series2[valid_mask]

    if len(s1_valid) < 3:
        logger.warning("Too few valid observations for correlation")
        return np.nan, np.nan

    if method == "pearson":
        corr, p_val = pearsonr(s1_valid, s2_valid)
        return corr, p_val
    else:
        raise NotImplementedError(f"Method {method} not implemented")


def pearsonr_ci(
    x: np.ndarray,
    y: np.ndarray,
    alpha: float = 0.05,
) -> Tuple[float, float, float, float, int]:
    """
    Pearson correlation with confidence interval via Fisher z-transformation.

    Replicates deprecated/old_scripts/cria_functions.py:pearsonr_ci (lines 542-571).
    Fixes deprecated bug: uses valid pair count instead of raw array length.

    Args:
        x: First array of values
        y: Second array of values
        alpha: Significance level (default 0.05 for 95% CI)

    Returns:
        Tuple of (r, p_value, ci_lower, ci_upper, n_valid)
    """
    mask = ~(np.isnan(x) | np.isnan(y))
    x_clean, y_clean = x[mask], y[mask]
    n = len(x_clean)

    if n < 3:
        return np.nan, np.nan, np.nan, np.nan, n

    r, p = pearsonr(x_clean, y_clean)

    # Fisher z-transformation for confidence interval
    r_z = np.arctanh(r)
    se = 1 / np.sqrt(n - 3)
    z = norm.ppf(1 - alpha / 2)
    lo = np.tanh(r_z - z * se)
    hi = np.tanh(r_z + z * se)

    return r, p, lo, hi, n


def calc_full_corr_matrix(
    data: pd.DataFrame,
    alpha: float = 0.05,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Full pairwise correlation with p-values, significance, and sample sizes.

    Replicates deprecated/old_scripts/cria_functions.py:calc_corr_matrix (lines 574-627).

    Args:
        data: DataFrame with numeric columns (indicators)
        alpha: Significance level for confidence intervals

    Returns:
        Tuple of 4 DataFrames (all indicator x indicator):
            - corr_r: Pearson correlation coefficients
            - corr_p: p-values
            - corr_zero: Significance flag (1=CI does NOT contain zero, 0=contains zero)
            - corr_n: Pairwise valid sample sizes
    """
    cols = data.columns
    n_cols = len(cols)

    corr_r = pd.DataFrame(0.0, index=cols, columns=cols)
    corr_p = pd.DataFrame(0.0, index=cols, columns=cols)
    corr_zero = pd.DataFrame(1, index=cols, columns=cols)
    corr_n = pd.DataFrame(0, index=cols, columns=cols)

    for i in range(n_cols):
        for j in range(n_cols):
            r, p, lo, hi, n = pearsonr_ci(
                data.iloc[:, i].values,
                data.iloc[:, j].values,
                alpha,
            )
            corr_r.iloc[i, j] = r
            corr_p.iloc[i, j] = p
            corr_n.iloc[i, j] = n

            # NaN correlation → not significant
            if np.isnan(r):
                corr_zero.iloc[i, j] = 0
            # CI contains zero → not significant → mark 0
            elif lo < 0 < hi:
                corr_zero.iloc[i, j] = 0

    logger.info(
        f"Computed full correlation matrix: {n_cols}x{n_cols}, "
        f"alpha={alpha}"
    )
    return corr_r, corr_p, corr_zero, corr_n


def winsorize(
    series: pd.Series,
    lower: float = 0.01,
    upper: float = 0.99,
) -> pd.Series:
    """
    Winsorize series (cap extreme values at percentiles).

    Replaces values below lower percentile with lower percentile value,
    and values above upper percentile with upper percentile value.

    Args:
        series: Series to winsorize
        lower: Lower percentile (0-1)
        upper: Upper percentile (0-1)

    Returns:
        Winsorized series

    Example:
        >>> ser = pd.Series([1, 2, 3, 4, 5, 100])  # 100 is outlier
        >>> wins = winsorize(ser, lower=0.05, upper=0.95)
        >>> print(wins.max())  # 5 (capped at 95th percentile)
    """
    lower_val = series.quantile(lower)
    upper_val = series.quantile(upper)

    ser_wins = series.copy()
    ser_wins = ser_wins.clip(lower=lower_val, upper=upper_val)

    n_capped = ((series < lower_val) | (series > upper_val)).sum()
    if n_capped > 0:
        logger.debug(f"  Winsorized {n_capped} values")

    return ser_wins


def fit_data(
    series: pd.Series,
    reorient: bool = False,
    standardize: bool = False,
    winsorize_pct: Optional[Tuple[float, float]] = None,
) -> pd.Series:
    """
    Fit data with multiple transformations.

    Pipeline:
    1. Optional: Reorient (reverse polarity: higher value = lower resilience)
    2. Optional: Winsorize (cap extreme values)
    3. Optional: Standardize (z-scores)

    Args:
        series: Series to transform
        reorient: Reverse polarity (multiply by -1)
        standardize: Calculate z-scores
        winsorize_pct: Tuple of (lower, upper) percentiles for winsorization

    Returns:
        Transformed series

    Example:
        >>> ser = pd.Series([1, 2, 3, 100, 5])  # 100 is outlier
        >>> fitted = fit_data(
        ...     ser,
        ...     reorient=True,
        ...     standardize=True,
        ...     winsorize_pct=(0.05, 0.95)
        ... )
    """
    result = series.copy()

    # Step 1: Reorient (reverse polarity)
    if reorient:
        result = result * -1

    # Step 2: Winsorize
    if winsorize_pct is not None:
        lower, upper = winsorize_pct
        result = winsorize(result, lower=lower, upper=upper)

    # Step 3: Standardize
    if standardize:
        result = calc_z_scores(result)

    return result


def rank_series(
    series: pd.Series,
    method: str = "average",
    ascending: bool = True,
) -> pd.Series:
    """
    Rank values in a series.

    Args:
        series: Series to rank
        method: Ranking method ('average', 'min', 'max', 'first', 'dense')
        ascending: Rank in ascending order (True) or descending (False)

    Returns:
        Series of ranks

    Example:
        >>> ser = pd.Series([10, 20, 30, 40, 50])
        >>> ranks = rank_series(ser, ascending=True)
        >>> print(ranks)  # 1, 2, 3, 4, 5
    """
    return series.rank(method=method, ascending=ascending)


def percentile_rank(series: pd.Series) -> pd.Series:
    """
    Calculate percentile rank (0-100).

    Args:
        series: Series to rank

    Returns:
        Series of percentile ranks (0-100)

    Example:
        >>> ser = pd.Series([10, 20, 30, 40, 50])
        >>> pct = percentile_rank(ser)
        >>> print(pct)  # 20, 40, 60, 80, 100
    """
    ranks = rank_series(series, method="average", ascending=True)
    n = series.notna().sum()

    percentiles = (ranks / n) * 100

    return percentiles
