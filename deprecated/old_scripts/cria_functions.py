# -*- coding: utf-8 -*-
"""
Created on Tue Feb 25 14:50:41 2020
Modified on Fri 07 Aug
Modified heavily on Wed 09 Mar 2022

@author: jhutchison

Looking for: ['pandas', 'numpy', 'ipykernel', 'mapclassify', 'pyomo',
    'matplotlib', 'seaborn', 'geopandas', 'pathlib', 'geopy', 'cartopy',
    'line_profiler', 'tqdm', 'openpyxl', 'xlsxwriter']


Chloropleth notes: https://gistbok.ucgis.org/bok-topics/
statistical-mapping-enumeration-normalization-classification

Mapclassify notes: https://pysal.org/mapclassify/tutorial.html

### Common `ipdb` Debugging Commands

- **`n` (next)**: Step to the next line in the current function.
- **`s` (step)**: Step into a function to debug it line-by-line.
- **`c` (continue)**: Continue execution until the next breakpoint.
- **`q` (quit)**: Quit the debugger.
- **`l` (list)**: Display the surrounding lines of code for context.
- **`p` (print)**: Print the value of a variable or expression (e.g., `p variable_name`).
- **`w` (where)**: Show the current position in the call stack.
- **`u` (up)**: Move up one frame in the call stack.
- **`d` (down)**: Move down one frame in the call stack.
- **`h` (help)**: Show help for available commands or a specific command (e.g., `help step`).
- **`!` (bang)**: Execute Python commands directly (e.g., `!print("Debugging")`).
- **`a` (args)**: Print the arguments of the current function.
- **`bt` (backtrace)**: Show the call stack.
- **`retval`**: Show the return value of the last function.
- **`display variable`**: Display the value of `variable` each time the debugger stops.

### Example Usage in Debugging
```python
import ipdb
ipdb.set_trace()  # Add this line to set a breakpoint
```

"""

# %% Packages

# import logging

# import matplotlib.pyplot as plt
import mapclassify as mc
import numpy as np

# import os
import pandas as pd

# import pyomo.environ as pyo
# import random
# import scipy.stats as sci
import time

# from geopy.distance import geodesic
from scipy.stats import pearsonr, norm

# from sklearn.cluster import KMeans

# Local Import
from utils.utils_logger import logger


# %% Functions
""" Define functions """


def mult_round(x, base=5):
    return base * round(x / base)


def center_scale(ser):
    out = ser - ser.mean(axis=0)
    out = out / ser.std(axis=0)
    return out


def clean_series(series, impute=False):
    ser = series.copy(deep=True)
    # remove strings from data, convert all data to float, remove null data
    ser.loc[ser == "#DIV/0!"] = None
    ser.loc[ser == "#VALUE!"] = None
    ser.loc[ser == "<Null>"] = None
    ser.loc[ser == "null"] = None
    ser.loc[ser == "-"] = None
    ser.loc[ser == "-666666666"] = None
    ser.loc[ser == "250,000+"] = 250000
    ser.loc[ser == "2,500-"] = 2500
    ser = ser.astype(float)
    if impute == True:
        ser.loc[pd.isna(ser) == True] = ser.mean()
    return ser


def clean_data(file, source, issues, level="county", sheet=0):
    data = pd.read_excel(file, sheet)
    data = data[pd.isna(data["GEOID"]) == False]  # clear blank entries
    if level == "county":
        data["Geo"] = data["Geography"].str.split(",", 2)
        data[["County", "State"]] = pd.DataFrame(
            data["Geo"].values.tolist(), index=data.index
        )
        data["County"] = data["County"].str.strip()
        data["State"] = data["State"].str.strip()
        columns = ["County", "State", "Geography"]
    elif level == "tract":
        data["Geo"] = data["Geography"].str.split(",", 2)
        data[["Tract", "County", "State"]] = pd.DataFrame(
            data["Geo"].values.tolist(), index=data.index
        )
        data["Tract"] = data["County"].str.strip()
        data["County"] = data["County"].str.strip()
        data["State"] = data["State"].str.strip()
        columns = ["Tract", "County", "State"]
    elif level == "territory":
        data["Geography"] = data["Geography"].str.split(", ")
        data["States"] = data["Geography"].str[-1]
        data["States"] = data["States"].str.split("--")
        data["Territory"] = data["Geography"].str[:1].str.join(", ")
        columns = ["Territory", "States"]

    data.index = data["GEOID"]
    keys = [key for key in list(source.keys()) if key not in issues]
    for key in keys:
        temp = clean_series(data[key], impute=False)
        data.loc[temp.index, key] = temp
        columns.append(key)
    data = data[columns]
    return data


def fit_manual(key, df_manual, groups=5):
    label_bins = "bins"

    # list_bins_cria_5 = [-1, -0.5, 0, 1]  # 2020 and prev
    # list_bins_cria_7 = [-1.5, -1, -0.5, 0, 1, 1.5]  # 2020 and prev
    list_bins_income_5 = [25, 50, 75, 100]
    list_bins_income_7 = [20, 40, 60, 80, 100, 120]
    # list_bins_popchange_5 = [0.5, 1, 2, 3]
    # list_bins_popchange_7 = [0.5, 1, 2, 3, 4, 5]
    list_bins_popchange_5 = [0.1, 0.25, 0.85, 1.5]
    list_bins_popchange_7 = [0.05, 0.15, 0.3, 0.9, 1.3, 2.25]
    list_bins_cria_7 = [-1.25, -0.75, -0.25, 0.25, 0.75, 1.25]  # proposed
    list_bins_cria_5 = [-0.75, -0.25, 0.25, 0.75]  # proposed
    list_bins_cria_p_7 = [0.05, 0.15, 0.3, 0.7, 0.85, 0.95]
    list_bins_cria_p_5 = [0.1, 0.3, 0.7, 0.9]

    d_bin_scale = {"Median Income": 1000}

    list_add_bounds = [
        list_bins_cria_5,
        list_bins_cria_7,
        list_bins_income_5,
        list_bins_income_7,
        list_bins_popchange_5,
        list_bins_popchange_7,
        list_bins_cria_p_5,
        list_bins_cria_p_7,
    ]

    for item in list_add_bounds:
        item.insert(0, -np.inf)
        item.append(np.inf)

    col_cut = key
    col_bins = f"{col_cut}_{label_bins}"

    if key == "Median Income":
        if groups == 5:
            list_bins = [item * d_bin_scale[key] for item in list_bins_income_5]

            df_manual[col_bins] = pd.cut(
                df_manual[col_cut],
                bins=list_bins,
                # labels=range(len(list_bins) - 1)[::-1],  # 0 index
                # 1 index, reverse labels (lower group, higher resilience)
                # labels=range(1, len(list_bins))[::-1],  # 1 index
                # 1 index, reverse labels (lower group, lower resilience, hi challenge)
                labels=range(1, len(list_bins)),  # 1 index
            )

        elif groups == 7:
            list_bins = [item * d_bin_scale[key] for item in list_bins_income_7]

            df_manual[col_bins] = pd.cut(
                df_manual[col_cut],
                bins=list_bins,
                # 1 index, reverse labels (lower group, higher resilience)
                # labels=range(1, len(list_bins))[::-1],  # 1 index
                # 1 index, reverse labels (lower group, lower resilience)
                labels=range(1, len(list_bins)),  # 1 index
            )

    elif (key == "agg") or (key == "drop_le"):
        if groups == 5:
            list_bins = list_bins_cria_5

            # 1 index, reverse labels (lower group, higher resilience)
            df_manual[col_bins] = pd.cut(
                df_manual[col_cut],
                bins=list_bins,
                labels=range(1, len(list_bins))[::-1],  # 1 index
            )

        elif groups == 7:
            list_bins = list_bins_cria_7

            # 1 index, reverse labels (lower group, higher resilience)
            df_manual[col_bins] = pd.cut(
                df_manual[col_cut],
                bins=list_bins,
                labels=range(1, len(list_bins))[::-1],  # 1 index
            )

    elif key in ["pop_p"]:
        if groups == 5:
            list_bins = list_bins_cria_p_5

            # 1 index, reverse labels (lower group, higher resilience)
            df_manual[col_bins] = pd.cut(
                df_manual[col_cut],
                bins=list_bins,
                labels=range(1, len(list_bins))[::-1],  # 1 index
            )

        elif groups == 7:
            list_bins = list_bins_cria_p_7

            # 1 index, reverse labels (lower group, higher resilience)
            df_manual[col_bins] = pd.cut(
                df_manual[col_cut],
                bins=list_bins,
                labels=range(1, len(list_bins))[::-1],  # 1 index
            )

    elif key in ["cria_p", "cri"]:
        # for both census tract and county the cria_p value and
        # bins should be
        # the higher the value = the higher challenge to resistance
        # (dark blue on color scale)

        if groups == 5:
            list_bins = list_bins_cria_p_5

            # 1 index, labels (higher group, higher challenge)
            df_manual[col_bins] = pd.cut(
                df_manual[col_cut],
                bins=list_bins,
                labels=range(1, len(list_bins)),  # 1 index
            )

        elif groups == 7:
            list_bins = list_bins_cria_p_7

            # 1 index, labels (higher group, higher challenge)
            df_manual[col_bins] = pd.cut(
                df_manual[col_cut],
                bins=list_bins,
                labels=range(1, len(list_bins)),  # 1 index
            )

    elif key == "pop change":
        if groups == 5:
            list_bins = list_bins_popchange_5
            # list_bins = list_bins_cria_p_5

            # 1 index, reverse labels (lower group, higher resilience)
            df_manual[col_bins] = pd.cut(
                df_manual[col_cut],
                bins=list_bins,
                labels=range(1, len(list_bins))[::-1],  # 1 index
            )

        elif groups == 7:
            list_bins = list_bins_popchange_7
            # list_bins = list_bins_cria_p_7

            # 1 index, reverse labels (lower group, higher resilience)
            df_manual[col_bins] = pd.cut(
                df_manual[col_cut],
                bins=list_bins,
                labels=range(1, len(list_bins))[::-1],  # 1 index
            )

    return df_manual


def fit_by_method(ser, groups=5, issues=[]):
    methods = {
        "Equal Interval": mc.EqualInterval,
        "Fisher Jenks": mc.FisherJenks,
        "HeadTail Breaks": mc.HeadTailBreaks,
        "Jenks Caspall": mc.JenksCaspall,
        "Maximum Breaks": mc.MaximumBreaks,
        "Natural Breaks": mc.NaturalBreaks,
        "Quantiles": mc.Quantiles,
        "Percentiles": mc.Percentiles,
        "Std Mean": mc.StdMean,
    }
    fits = ["ADCM", "GADF", "TSS"]
    methods_k = [
        "Equal Interval",
        "Fisher Jenks",
        "Jenks Caspall",
        "Maximum Breaks",
        "Natural Breaks",
        "Quantiles",
    ]

    fit_df = pd.DataFrame(0, index=fits, columns=methods.keys())
    fit_bins = dict(zip(methods.keys(), [0] * len(methods.keys())))
    fit_yb = pd.DataFrame(0, index=ser.index, columns=methods.keys())
    fit_counts = dict(zip(methods.keys(), [0] * len(methods.keys())))

    method_list = [method for method in methods.keys() if method not in issues]

    for method in method_list:
        # break
        logger.debug(f"fitting {method}")
        if method in methods_k:
            test = methods[method](ser, k=groups)
        else:
            test = methods[method](y=ser)
        fit_df.loc[:, method] = [test.adcm, test.gadf, test.tss]
        fit_bins[method] = test.bins
        fit_yb.loc[ser.index, method] = test.yb
        fit_counts[method] = test.counts
    logger.info(f"{ser.name} fitting complete")
    ser_fit = pd.Series(
        index=["fit_df", "fit_bins", "fit_yb", "fit_counts"],
        data=[fit_df, fit_bins, fit_yb, fit_counts],
    )
    return ser_fit


def adjust_groups(
    fit_bins, fit_counts, best, groups, label_group, col_bins, col_counts
):
    """
    Adjusts the groups to ensure they fit the required number,
    consolidating extra groups into the top group if necessary.

    Parameters:
    - fit_bins: dict, the bin boundaries for each method
    - fit_counts: dict, the counts for each bin
    - best: str, the key to access the selected method's bins and counts
    - groups: int, the required number of groups
    - label_group: str, the label prefix for groups
    - col_bins: str, the column name for bins
    - col_counts: str, the column name for counts

    Returns:
    - pd.DataFrame: DataFrame with adjusted groups and counts
    """
    # Combine bins and counts for ease of processing
    bins_and_counts = list(zip(fit_bins[best], fit_counts[best]))

    # Apply the "stronghand" adjustment if the number of groups exceeds the limit
    if len(bins_and_counts) > groups:
        # ipdb.set_trace()  # Debugging entry point
        # Merge smaller groups into the top group
        remaining_bins = bins_and_counts[: groups - 1]
        top_group = bins_and_counts[groups - 1 :]  # Merge all excess groups

        # Calculate merged bin (e.g., average) and count
        top_bin = sum(float(bin) for bin, _ in top_group) / len(
            top_group
        )  # Example: average bin
        top_count = sum(int(count) for _, count in top_group)
        remaining_bins.append((top_bin, top_count))
    else:
        remaining_bins = bins_and_counts

    # Create the DataFrame
    temp = pd.DataFrame(remaining_bins, columns=[col_bins, col_counts])
    temp.index = [f"{label_group} {i+1}" for i in range(len(temp))]

    return temp


def fit_data(
    df_fit, list_exceptions, groups=5, drop_na_val=False, incl_natl_breaks=False
):
    df_meta = pd.DataFrame()
    df_labels = pd.DataFrame(index=df_fit.index)
    manual_list = [
        "Median Income",
        "agg",
        "pop change",
        "drop_le",
        "cria_p",
        "pop_p",
        "cri",
    ]
    label_bins = "bins"
    label_failed = "failed"
    label_select = "choose"
    label_selected = "selected"
    label_manual = "manual"
    label_group = "group"
    col_bins = "bins"
    col_counts = "counts"
    col_final = "final"

    for key in df_fit.columns:
        # break
        logger.debug(f"Processing {key}")
        ser = df_fit[key].copy()
        if drop_na_val:
            ser = ser.dropna()
        ser = ser.dropna()
        logger.debug(f"{key} with {len(ser)} entries")
        df_labels[key] = ser
        col_bins = f"{key}_{label_bins}"
        if key in manual_list:
            df_labels = fit_manual(key, df_labels, groups)
            df_meta.loc[label_select, col_bins] = label_manual
            agg_df = df_labels.groupby([col_bins])[col_bins].count()
            for group in agg_df.index:
                group_name = f"{label_group} {group}"
                df_meta.loc[group_name, col_bins] = agg_df[group]

        else:

            if key in list_exceptions.keys():
                issues = list_exceptions[key]
            else:
                issues = []
            fit_ser = fit_by_method(ser, groups=groups, issues=issues)

            fit_df = fit_ser["fit_df"].copy()
            fit_bins = fit_ser["fit_bins"].copy()
            fit_yb = fit_ser["fit_yb"].copy()
            fit_counts = fit_ser["fit_counts"].copy()
            # ensure best fit signals the process failed (fit_df == 0)
            fit_df = fit_df.T
            exclude = fit_df.sum(axis=1)
            exclude["Percentiles"] = 0
            exclude = exclude[exclude <= 0.005]
            fit_cs = fit_df.copy(deep=True)
            for fit in fit_df:
                fit_cs[fit] = center_scale(fit_df[fit])
            fit_cs[col_final] = (fit_cs["ADCM"] + fit_cs["TSS"]) / 2
            fit_cs = fit_cs.sort_values(by=col_final)

            # Develop Metadata for bin selection
            df_temp = pd.DataFrame(fit_cs[col_final])
            df_temp[col_bins] = list(fit_cs.index)
            df_temp = df_temp[[col_bins, col_final]]
            df_temp.columns = [col_bins, col_counts]
            df_temp.loc[list(exclude.index), col_counts] = label_failed
            df_temp.index = range(len(df_temp))

            # Assign best fit bins to DataFrame col_bins
            # drop natural breaks due to random nature of process
            if incl_natl_breaks is False:
                fit_cs = fit_cs.drop("Natural Breaks")
            best = [text for text in fit_cs.index if text not in exclude.index][0]

            # Adjust Head_Tail Breaks,
            # fit all bins greater than limit to top bin
            zero_index = False
            # shift groups if index begins with zero
            fit_yb.loc[fit_yb["HeadTail Breaks"] >= groups, "HeadTail Breaks"] = (
                groups - 1
            )  # zero index
            df_labels[col_bins] = fit_yb[best] + (1 - zero_index)
            select = pd.DataFrame(
                [[label_selected, best]],
                index=[label_select],
                columns=[col_bins, col_counts],
            )

            temp = adjust_groups(
                fit_bins, fit_counts, best, groups, label_group, col_bins, col_counts
            )
            # # Assign bin counts to Meta
            # temp = pd.DataFrame(0, index=range(groups), columns=[col_bins, col_counts])
            # # Accept only first a number of bins limited by groups (5 or 7)
            # if len(fit_bins[best]) > groups:
            #     # Head tail breaks may be more
            #     temp[col_bins] = [float(text) for text in fit_bins[best]][:groups]
            #     temp[col_counts] = [int(text) for text in fit_counts[best]][:groups]
            # else:
            #     # Quantiles, other groups may be less
            #     temp[col_bins] = [float(text) for text in fit_bins[best]]
            #     temp[col_counts] = [int(text) for text in fit_counts[best]]
            # # Adjust index
            # # f string and shift index to 1-index
            # temp.index = [f"{label_group} {count+1}" for count in range(groups)]
            df_temp = pd.concat([select, df_temp, temp], axis=0, sort=False)
            df_temp.columns = [key, col_bins]
            df_meta[[key, col_bins]] = df_temp[[key, col_bins]]
            # if key == "No Vehicle":
            #     import ipdb

            #     ipdb.set_trace()
            if key == "Hospitals":
                df_labels.loc[df_labels["Hospitals"] == 0, "Hospitals_bins"] = 1
                df_labels.loc[
                    (df_labels["Hospitals"] > 0) & (df_labels["Hospitals_bins"] == 1),
                    "Hospitals_bins",
                ] = 2

                bin_counts = df_labels.groupby("Hospitals_bins")["Hospitals"].count()
                bin_maxes = df_labels.groupby("Hospitals_bins")["Hospitals"].max()

                for i, (max_value, count) in enumerate(
                    zip(bin_maxes, bin_counts), start=1
                ):
                    df_meta.loc[f"group {i}", "Hospitals"] = max_value
                    df_meta.loc[f"group {i}", "Hospitals_bins"] = count

    results = pd.Series({"bins": df_labels, "meta": df_meta}, index=["bins", "meta"])
    return results


def calc_z_scores(Pos, sub_index=[]):
    Scores = Pos.copy(deep=True)
    features = list(Scores.columns)
    features.remove("Population Change")
    if sub_index != []:
        means = Scores.loc[sub_index, :].mean(axis="rows")
        devs = Scores.loc[sub_index, :].std(axis="rows")
    else:
        means = Scores.mean(axis="rows")
        devs = Scores.std(axis="rows")
    for indicator in features:
        Scores[indicator] = (Scores[indicator] - means[indicator]) / devs[indicator]
    Scores["Population Change"] = (
        Scores["Population Change"] / devs["Population Change"]
    )
    return Scores


def pearsonr_ci(x, y, alpha=0.05):
    """calculate Pearson correlation along with
    the confidence interval using scipy and numpy
    Parameters
    ----------
    x, y : iterable object such as a list or np.array
      Input for correlation calculation
    alpha : float
      Significance level. 0.05 by default
    Returns
    -------
    r : float
      Pearson's correlation coefficient
    pval : float
      The corresponding p value
    lo, hi : float
      The lower and upper bound of confidence intervals
    """
    # x_idx = x[pd.isna(x) == False].index
    # y_idx = y[pd.isna(y) == False].index
    # idx_list = set(x_idx) & set(y_idx)
    # idx = set(idx_list)
    # r, p = pearsonr(x[idx], y[idx])
    r, p = pearsonr(x, y)
    r_z = np.arctanh(r)
    se = 1 / np.sqrt(x.size - 3)
    z = norm.ppf(1 - alpha / 2)
    lo_z, hi_z = r_z - z * se, r_z + z * se
    lo, hi = np.tanh((lo_z, hi_z))
    return r, p, lo, hi, len(x)


def calc_corr_matrix(Data):
    """
    # Reorder and relabel with stored dictionary
    # Relabel (now taken care of with Labels DataFrame)
    columns = {'Age':'Age',
               'Education':'Educational Attainment',
               'Disability':'Disability',
               'Limited English':'English Language Proficiency',
               'Health Insurance': 'Health Insurance',
               'No Vehicle':'Mobility',
               'Employment':'Unemployment Rate',
               'Median Income':'Household Income',
               'GINI':'Income Inequality',
               'Owner Occupied':'Home Ownership',
               'Single Parent':'Single-Parent Household',
               'Mobile Homes':'Presence of Mobile Homes',
               'Schools':'Public School Capacity',
               'Diagnostics':'Medical Professional Capacity',
               'Hospitals':'Hospital Capacity',
               'Hotels':'Hotel/Motel Capacity',
               'Vacant Rentals':'Rental Property Capacity',
               'Religion': 'Affiliation with a Religion',
               'Organizations':'Connection to Civic and Social Organizations',
               'Population':'Population Change'}
    columns = {k:v for k,v in columns.items() if k in Data.columns}
    data = Data[columns.keys()].copy(deep = True)
    data.columns = columns.values()

    data = data.corr()
    """
    corr = Data.corr()

    # check correlation, grab CI - p, LB, and UB
    corr_df_r = pd.DataFrame(0, index=Data.columns, columns=Data.columns)
    corr_df_p = pd.DataFrame(0, index=Data.columns, columns=Data.columns)
    corr_df_lb = pd.DataFrame(0, index=Data.columns, columns=Data.columns)
    corr_df_ub = pd.DataFrame(0, index=Data.columns, columns=Data.columns)
    corr_df_zero = pd.DataFrame(1, index=Data.columns, columns=Data.columns)
    corr_df_n = pd.DataFrame(0, index=Data.columns, columns=Data.columns)
    corr_df_check = pd.DataFrame(0, index=corr.columns, columns=corr.columns)

    for i in Data.columns:
        for j in Data.columns:
            x = Data[i].values
            y = Data[j].values
            r, p, lo, hi, n = pearsonr_ci(x, y, alpha=0.05)
            corr_df_r.loc[i, j] = r
            corr_df_p.loc[i, j] = p
            corr_df_lb.loc[i, j] = lo
            corr_df_ub.loc[i, j] = hi
            if lo < 0 and 0 < hi:
                corr_df_zero.loc[i, j] = 0
            corr_df_n.loc[i, j] = n
    return (corr_df_r, corr_df_p, corr_df_zero, corr_df_n)


# %% Variables
""" Set local variables """


# %% Main
""" Display task data """

if __name__ == "__main__":
    logger.info("functions ready")
