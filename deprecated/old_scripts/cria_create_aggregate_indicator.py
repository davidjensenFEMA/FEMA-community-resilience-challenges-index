# -*- coding: utf-8 -*-
"""
Created on Fri Feb  4 13:57:18 2022

@author: jhutchison

conda env list
conda create --name conda_cria
conda activate conda_cria
conda install mamba
mamba install -c conda-forge mapclassify=2.4
mamba install pandas numpy pathlib requests
mamba install notebook
mamba install openpyxl=3.1.0
# mamba install numba  # requires an earlier version of numpy
mamba install xlsxwriter
mamba install pip
# cd to conda_cria packages/pip.exe
# cd Anaconda3\envs\conda_cria\Scripts
# pip.exe install numba
# still doesn't work, requies python < 3.11
mamba install python=3.10
mamba install numba
mamba update conda
mamba update --all
mamba install openpyxl=3.1.0
"""

# %% Packages
""" Third party and local imports """

# import json
import numpy as np
import pandas as pd
import pathlib
import string

# import requests

# Local Import
from utils.utils_logger import logger
from cria_create_indicators import ser_ref, create_indicators

from cria_functions import clean_series, calc_z_scores, fit_data, calc_corr_matrix
from utils.utils_excel_tools import update_excel_workbook, save_excel_table


# %% Functions
""" Define functions """


def create_agg_indicator(
    exceptions,
    ser_ref,
    ser_data=None,
    geography="county",
    lowest_resilience=True,
    bin_indicators=True,
):
    # references
    years = ser_ref["years"]
    ref = ser_ref["ref"]
    geographies = ser_ref["geographies"]

    # data
    if ser_data is not None:
        assert (
            ser_data.index.isin(["data", "df"]).sum() == 2
        ), "require data and indicators (df)"
        data = ser_data["data"].copy(deep=True)
        df = ser_data["df"].copy(deep=True)
    else:
        df, data = create_indicators(ser_ref, ser_data=None, geography=geography)
        logger.debug("indicators ready, beginning aggregate")
    labels = data.loc["labels", :]
    data = data.drop("labels", axis=0).apply(pd.to_numeric)

    # *** Modify here ***
    """ Change CBP values for 2022 CT from 0 (wrong) to Null """
    if geography == "county":
        geo = geographies["county"]
        idx_geo = geo.loc[geo["state_name"] == "Connecticut", :].index
        list_cbp_cols = list(ref.loc[ref["Source"] == "CBP", "numerator"])
        list_ind_cols = list(ref.loc[ref["Source"] == "CBP", "Indicator"])

        # replace data zero with null
        data.loc[idx_geo, list_cbp_cols] = np.NaN
        # replace df zero with null
        df.loc[idx_geo, list_ind_cols] = np.NaN
    # *** End Update ***

    """Analyze CRIA data"""
    # Prep
    # Bin all features, county and tract
    df_clean = df.apply(clean_series, impute=True)
    if geography in ["state", "county", "tract"]:
        geo_ref = geographies[geography]
        idx_PR = geo_ref.loc[geo_ref["state"] == 72, :].index
        logger.info(f"removing {len(idx_PR)} Lim Eng rows from Puerto Rico clean df")
        df_clean.loc[idx_PR, "Limited English"] = [np.nan] * len(idx_PR)

    df_reshape = pd.DataFrame(
        data=df_clean, index=geographies[geography].index, columns=df_clean.columns
    )
    logger.debug("indicators cleaned")

    # Rescale inputs, record as df_scale
    # with few exceptions, want inputs scaled 0 to 100 rather than 0 to 1
    rescale = ref.loc[ref["Units"].isin(["index", "fraction"]), "Indicator"]
    logger.debug(f"rescaling {len(rescale)} columns")
    df_scale = df_reshape.copy(deep=True)
    df_scale[rescale] = 100 * df_scale[rescale]

    # Bin indicators
    # import ipdb

    # ipdb.set_trace()
    if bin_indicators:
        bin_results = fit_data(
            df_fit=df_scale,
            list_exceptions=exceptions[geography],
            groups=bins[geography],
        )
    else:
        bin_results = pd.Series(
            {
                "meta": pd.Series({0: None}).to_frame(),
                "bins": pd.Series({0: None}).to_frame(),
            }
        )

    # Reverse indicators, record as df_pos
    reverse = ref.loc[ref["Augment"] == "reverse", "Indicator"]
    logger.debug(f"orienting {len(reverse)} columns, " + "pos indicators of resilience")
    df_pos = df_scale.copy(deep=True)
    df_pos[reverse] = 100 - df_pos[reverse]

    # Calculate standarized scores (z scores)
    df_scores = calc_z_scores(df_pos)
    n_cols_large = 3
    # lowest resilience (use df_scores)
    # highest resilience (use -df_scores)
    if lowest_resilience == True:
        idx_filter = np.argsort(df_scores.values, axis=1)[:, :n_cols_large]
        label_lowest = "lowest"
    else:
        idx_filter = np.argsort(-df_scores.values, axis=1)[:, :n_cols_large]
        label_lowest = "highest"
    df_large = pd.DataFrame(
        data=df_scores.columns.values[idx_filter],
        index=df_scores.index,
        columns=["ind_1", "ind_2", "ind_3"],
    )
    df_scores_p = df_scores.rank(axis=0, pct=True)
    list_ser = []
    for row, idx in enumerate(df_scores.index):
        ser = df_scores.loc[idx, df_scores.columns[idx_filter[row]]]
        list_labels = list(ser.index)
        ser.index = ["ind_1_perc", "ind_2_perc", "ind_3_perc"]
        ser["list_labels"] = list_labels
        df_small = ser.to_frame().T
        list_ser.append(df_small)
    df_large_perc = pd.concat(list_ser, axis=0)
    df_large_final = pd.concat([df_large, df_large_perc], axis=1)
    list_cols = sorted(list(df_large_final.columns))
    df_large_final = df_large_final[list_cols]
    df_large_final.index.name = df_scores.index.name

    # Calculate aggregate indicator
    logger.info(
        "converting standardized population change"
        + "(mean net mig) to neg abs val of standardized scores"
    )
    df_scores["Population Change"] = -abs(df_scores["Population Change"])
    df_agg = pd.DataFrame(index=df_scores.index)
    list_indicators = ref["Indicator"].to_list()
    df_agg["agg"] = df_scores[list_indicators].mean(axis="columns")
    df_agg["cri"] = -df_agg["agg"]
    df_agg["cria_p"] = df_agg["cri"].rank(axis=0, pct=True)
    # df_agg["pop change"] = df_scores["Population Change"]
    df_agg["pop change"] = abs(df_scores["Population Change"])
    df_agg["pop_p"] = df_agg["pop change"].rank(axis=0, pct=True)

    # if bin_indicators:
    # bin_agg = fit_data(
    #     df_fit=df_agg, list_exceptions=exceptions[geography], groups=bins[geography]
    # )
    # else:
    #     bin_agg = pd.Series(
    #         {
    #             "meta": pd.Series({0: None}).to_frame(),
    #             "bins": pd.Series({0: None}).to_frame(),
    #         }
    #     )
    bin_agg = fit_data(
        df_fit=df_agg, list_exceptions=exceptions[geography], groups=bins[geography]
    )

    # Calculate Correlation
    df_clean = df.apply(clean_series, impute=True)
    df_corr = df_clean.copy(deep=True)
    update_labels = dict(zip(ref["Indicator"].values, ref["Label_Correlation"].values))
    df_corr = df_corr.rename(update_labels, axis=1)
    update_order = ref.sort_values("Order_Correlation", axis=0)["Label_Correlation"]
    df_corr = df_corr[update_order].copy(deep=True)
    corr, p, zero, n = calc_corr_matrix(df_corr)

    # Add labels back to data
    data = pd.concat([labels.to_frame().T, data], axis=0)
    # data.insert(loc=0, column="NAME", value=geographies[geography]["NAME"])
    data.index.name = "GEO_ID"

    # Write
    out = {
        "ref": ref,
        "years": pd.Series(years).to_frame(),
        "bin_meta": bin_results["meta"],
        "bin_labels": bin_results["bins"],
        "agg_meta": bin_agg["meta"],
        "agg_labels": bin_agg["bins"],
        "data": data,
        "indicators": df,
        "pos": df_pos,
        "scores": df_scores,
        f"{label_lowest}_ind": df_large_final,
        "scores_percentiles": df_scores_p,
        "corr": corr,
        "p": p,
        "zero": zero,
        "n": n,
    }

    # Add State Abbreviations with GEO_ID
    for key, var in out.items():
        # print(key, var.index.name)
        if var.index.name == "GEO_ID":
            # out[key] = geographies[geography].copy().merge(var,left_index=True, right_index=True)
            out[key] = var.merge(
                geographies[geography], left_index=True, right_index=True, how="left"
            )

    logger.info("aggregate ready")
    return out


# %% Variables
""" Set local variables """

path_data = pathlib.Path("data/")
path_out = pathlib.Path("output/")
path_reports = pathlib.Path(path_out / "reports/")

run_new_data = True

lowest_resilience = True

ref = ser_ref["ref"]
years = ser_ref["years"]
geographies = ser_ref["geographies"]


# %% Binning support
""" Set binning properties (script specific local variables) """

bins = {"county": 5, "tract": 7, "tribal": 5, "state": 5}

# issues = {"county": [], "tract": [], "tribal": []}

# jenks caspall struggles with some inputs;
# save calculation time by skipping these indicators

# exceptions = {
#     "county": {
#         "Civil Org": ["Jenks Caspall"],
#         "Hospitals": ["Jenks Caspall"],
#         "Medical": ["Jenks Caspall"],
#     },
#     "tract": {
#         "Mobile Homes": ["Jenks Caspall", "Fisher Jenks"],
#         "Limited English": ["Jenks Caspall", "Fisher Jenks"],
#         "Poverty": ["Jenks Caspall", "Fisher Jenks"],
#         "Hospitals": ["Jenks Caspall", "Fisher Jenks"],
#     },
#     "tribal": {
#         "Limited English": ["Jenks Caspall"],
#     },
#     "state": {},
# }

exceptions = {
    "county": {
        "Civil Org": ["Jenks Caspall"],
        "Hospitals": ["Jenks Caspall"],
        "Medical": ["Jenks Caspall"],
    },
    "tract": {
        "Mobile Homes": ["Jenks Caspall", "Fisher Jenks"],
        "Limited English": ["Jenks Caspall", "Fisher Jenks"],
        "Poverty": [],
        "Hospitals": ["Jenks Caspall", "Fisher Jenks"],
    },
    "tribal": {
        "Limited English": ["Jenks Caspall"],
    },
    "state": {},
}


# %% Main
""" Retrieve data, calc indicators, aggregate, save """

if __name__ == "__main__":
    geography = "county"

    if run_new_data:
        d_out = create_agg_indicator(
            exceptions,
            ser_ref,
            ser_data=None,
            geography=geography,
            lowest_resilience=True,
            bin_indicators=True,
        )
        logger.info(
            f'cria results ready for {geography} during {ser_ref["years"]["acs"]}'
        )

        #### Modify County Code here
        data_county = d_out["data"]
        d = d_out
        #### End Modify County

        #### Modify empty vote data here
        votes_by_state = (
            data_county[["A1a", "A1c", "state_abbr"]].groupby("state_abbr").sum()
        )
        votes_by_state["prod"] = votes_by_state["A1a"] * votes_by_state["A1c"]

        votes_by_state = pd.merge(
            left=votes_by_state,
            right=geographies["state"][["state", "state_abbr"]],
            left_index=True,
            right_on="state_abbr",
        ).sort_index()

        zero_votes = votes_by_state.loc[votes_by_state["prod"] == 0]

        df_bin_labels = d["bin_labels"].copy(deep=True)
        df_bin_labels[["Inactive Voter_bins", "state_abbr"]].head()

        states_with_zero = set(zero_votes["state_abbr"])

        # Replace imputed values with np.nan where state_abbr is in the zero_votes list.
        df_bin_labels.loc[
            df_bin_labels["state_abbr"].isin(states_with_zero), "Inactive Voter_bins"
        ] = np.nan

        d["bin_labels"] = df_bin_labels
        #### End Modify empty vote data

        # Excel
        file_name = f'cria_results_{geography}_{ser_ref["years"]["acs"]}'
        save_excel_table(d_out, path_out / f"{file_name}.xlsx", keep_index=True)
        # Pickle
        ser_data = pd.Series(d_out)
        ser_data.to_pickle(path_out / f"{file_name}.pkl")
    else:
        logger.info(f"loading {geography} data")
        if geography == "county":
            file_name = f'cria_results_{geography}_{ser_ref["years"]["acs"]}'
        elif geography == "tract":
            method = "match_county"
            file_name = f"impute_tract_data_{method}_{years['acs']}"
        ser_data = pd.read_pickle(path_out / f"{file_name}.pkl")

    file_name = f"Correlation Matrix {geography.upper()}"

    list_ignore_sheet_names = ["Correlation Matrix", "Data"]
    update_excel_workbook(
        file_name=f"{path_reports / file_name}.xlsx",
        ser_data=ser_data,
        list_ignore_sheet_names=list_ignore_sheet_names,
    )


# # %% Lowest Indicator Exploration
# """ Check lowest indicator """

# from itertools import combinations
# from math import factorial

# ref = ser_data["ref"]
# list_ind = ref["Indicator"].tolist()
# n = len(list_ind)
# r = 2

# list_comb = list(
#     combinations(
#         list_ind,
#         r=r,
#     )
# )

# list_comb_str = [item.join(",").replace(",", "_") for item in list_comb]

# C = factorial(n) / (factorial(r) * factorial(n - r))
# logger.info(f"list total combinations {C} from {n} choose {r}")

# df_low = ser_data["lowest_ind"].copy()
# df_low["list_labels"] = (
#     df_low[["ind_1", "ind_2", "ind_3"]].values.tolist().str.join(",", "_")
# )

# df_comb = pd.DataFrame(
#     data=0,
#     index=df_low.index,
#     columns=list_comb,
# )

# for idx_county, list_val in df_low["list_labels"].items():

#     list_comb_county = list(
#         combinations(
#             list_val,
#             r=r,
#         )
#     )
#     df_comb.loc[idx_county, list_comb_county[0]] = 1
